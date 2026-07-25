"""Repository interfaces — spec §20.

The API layer depends only on these abstract classes, never on the in-memory
implementation. A DynamoDB implementation slots in by subclassing the same
interfaces and swapping the bundle built in `app.dependencies`; no route changes
are required.

Method signatures deliberately avoid returning mutable internal state by
reference in the storage contract — the in-memory implementation deep-copies on
read where mutation would otherwise leak across requests, which is also what a
real database would do.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, Optional, TypeVar

from ..models.entities import (
    AIInsight,
    AnalysisSession,
    AuditRecord,
    FinancialGoal,
    LeakFindingRecord,
    PriceChangeRecord,
    RecurrencePatternRecord,
    RoundUpCalculation,
    RoundUpRuleRecord,
    SafeSpareSnapshot,
    Simulation,
    UploadedDocument,
    UploadTicket,
    User,
    VoiceAsset,
)
from ..models.transaction import Transaction

T = TypeVar("T")


class Repository(Generic[T], ABC):
    """Minimal CRUD contract shared by every entity store."""

    @abstractmethod
    def put(self, item: T) -> T:
        ...

    @abstractmethod
    def get(self, item_id: str) -> Optional[T]:
        ...

    @abstractmethod
    def delete(self, item_id: str) -> bool:
        ...

    @abstractmethod
    def list_all(self) -> List[T]:
        ...


class UserRepository(Repository[User], ABC):
    @abstractmethod
    def get_or_create_by_session_key(self, session_key: str) -> User:
        ...


class AnalysisRepository(Repository[AnalysisSession], ABC):
    @abstractmethod
    def list_for_user(self, user_id: str) -> List[AnalysisSession]:
        ...

    @abstractmethod
    def find_by_idempotency_key(self, user_id: str, key: str) -> Optional[str]:
        """Return an existing analysis ID for this key, if one was recorded (§19)."""

    @abstractmethod
    def remember_idempotency_key(self, user_id: str, key: str, analysis_id: str) -> None:
        ...


class DocumentRepository(Repository[UploadedDocument], ABC):
    """Metadata plus the raw bytes. Bytes are purged on delete (§22)."""

    @abstractmethod
    def put_content(self, document_id: str, data: bytes) -> None:
        ...

    @abstractmethod
    def get_content(self, document_id: str) -> Optional[bytes]:
        ...

    @abstractmethod
    def purge_content(self, document_id: str) -> None:
        ...

    @abstractmethod
    def put_ticket(self, ticket: UploadTicket) -> UploadTicket:
        ...

    @abstractmethod
    def get_ticket(self, ticket_id: str) -> Optional[UploadTicket]:
        ...

    @abstractmethod
    def list_for_user(self, user_id: str) -> List[UploadedDocument]:
        ...


class TransactionRepository(ABC):
    """Transactions are always addressed within an analysis."""

    @abstractmethod
    def replace_all(self, analysis_id: str, transactions: List[Transaction]) -> None:
        ...

    @abstractmethod
    def list_for_analysis(self, analysis_id: str) -> List[Transaction]:
        ...

    @abstractmethod
    def get(self, transaction_id: str) -> Optional[Transaction]:
        ...

    @abstractmethod
    def analysis_id_for(self, transaction_id: str) -> Optional[str]:
        ...

    @abstractmethod
    def save(self, analysis_id: str, transaction: Transaction) -> None:
        ...

    @abstractmethod
    def delete_for_analysis(self, analysis_id: str) -> None:
        ...


class CalculationRepository(ABC):
    """Store for every calculated record produced by the deterministic engines."""

    @abstractmethod
    def set_patterns(self, analysis_id: str, records: List[RecurrencePatternRecord]) -> None:
        ...

    @abstractmethod
    def get_patterns(self, analysis_id: str) -> List[RecurrencePatternRecord]:
        ...

    @abstractmethod
    def set_price_changes(self, analysis_id: str, records: List[PriceChangeRecord]) -> None:
        ...

    @abstractmethod
    def get_price_changes(self, analysis_id: str) -> List[PriceChangeRecord]:
        ...

    @abstractmethod
    def set_leaks(self, analysis_id: str, records: List[LeakFindingRecord]) -> None:
        ...

    @abstractmethod
    def get_leaks(self, analysis_id: str) -> List[LeakFindingRecord]:
        ...

    @abstractmethod
    def get_leak(self, leak_id: str) -> Optional[LeakFindingRecord]:
        ...

    @abstractmethod
    def set_safe_spare(self, analysis_id: str, snapshot: SafeSpareSnapshot) -> None:
        ...

    @abstractmethod
    def get_safe_spare(self, analysis_id: str) -> Optional[SafeSpareSnapshot]:
        ...

    @abstractmethod
    def set_roundups(self, analysis_id: str, record: RoundUpCalculation) -> None:
        ...

    @abstractmethod
    def get_roundups(self, analysis_id: str) -> Optional[RoundUpCalculation]:
        ...

    @abstractmethod
    def set_state(self, analysis_id: str, key: str, value: Any) -> None:
        """Free-form per-analysis state: settings, rules, usage statuses, decisions."""

    @abstractmethod
    def get_state(self, analysis_id: str, key: str, default: Any = None) -> Any:
        ...

    @abstractmethod
    def delete_for_analysis(self, analysis_id: str) -> None:
        ...


class GoalRepository(Repository[FinancialGoal], ABC):
    @abstractmethod
    def list_for_analysis(self, analysis_id: str) -> List[FinancialGoal]:
        ...

    @abstractmethod
    def put_simulation(self, simulation: Simulation) -> Simulation:
        ...

    @abstractmethod
    def latest_simulation(self, goal_id: str) -> Optional[Simulation]:
        ...

    @abstractmethod
    def delete_for_analysis(self, analysis_id: str) -> None:
        ...


class InsightRepository(ABC):
    @abstractmethod
    def set_insights(self, analysis_id: str, insights: List[AIInsight]) -> None:
        ...

    @abstractmethod
    def list_insights(self, analysis_id: str) -> List[AIInsight]:
        ...

    @abstractmethod
    def put_voice(self, asset: VoiceAsset) -> VoiceAsset:
        ...

    @abstractmethod
    def latest_voice(self, analysis_id: str) -> Optional[VoiceAsset]:
        ...

    @abstractmethod
    def delete_for_analysis(self, analysis_id: str) -> None:
        ...


class AuditRepository(ABC):
    """Append-only. §6.3 requires an audit record for every user correction."""

    @abstractmethod
    def append(self, record: AuditRecord) -> AuditRecord:
        ...

    @abstractmethod
    def list_for_analysis(self, analysis_id: str) -> List[AuditRecord]:
        ...

    @abstractmethod
    def delete_for_analysis(self, analysis_id: str) -> None:
        ...


class Repositories:
    """Bundle handed to routes by `app.dependencies`.

    Swapping every store for a DynamoDB-backed one is a change to the single
    construction site, not to any route.
    """

    def __init__(
        self,
        users: UserRepository,
        analyses: AnalysisRepository,
        documents: DocumentRepository,
        transactions: TransactionRepository,
        calculations: CalculationRepository,
        goals: GoalRepository,
        insights: InsightRepository,
        audit: AuditRepository,
    ) -> None:
        self.users = users
        self.analyses = analyses
        self.documents = documents
        self.transactions = transactions
        self.calculations = calculations
        self.goals = goals
        self.insights = insights
        self.audit = audit

    def purge_analysis(self, analysis_id: str) -> Dict[str, Any]:
        """Delete an analysis and every record derived from it (§18 DELETE, §22)."""
        session = self.analyses.get(analysis_id)
        deleted = {
            "analysis_id": analysis_id,
            "existed": session is not None,
            "document_purged": False,
        }
        if session is not None and session.document_id:
            self.documents.purge_content(session.document_id)
            self.documents.delete(session.document_id)
            deleted["document_purged"] = True
        self.transactions.delete_for_analysis(analysis_id)
        self.calculations.delete_for_analysis(analysis_id)
        self.goals.delete_for_analysis(analysis_id)
        self.insights.delete_for_analysis(analysis_id)
        self.audit.delete_for_analysis(analysis_id)
        self.analyses.delete(analysis_id)
        return deleted

    def purge_user(self, user_id: str) -> Dict[str, Any]:
        """§18 `POST /api/privacy/delete-data` — everything the user ever uploaded."""
        analyses = [s.id for s in self.analyses.list_for_user(user_id)]
        for analysis_id in analyses:
            self.purge_analysis(analysis_id)
        documents = self.documents.list_for_user(user_id)
        for document in documents:
            self.documents.purge_content(document.id)
            self.documents.delete(document.id)
        return {
            "analyses_deleted": len(analyses),
            "documents_deleted": len(documents),
            "user_id": user_id,
        }
