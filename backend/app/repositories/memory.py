"""In-memory repositories — spec §20 MVP implementation.

Thread-safe because FastAPI runs sync endpoints in a worker thread pool and
background tasks run on the same loop's executor; two requests touching one
analysis concurrently is normal, not exotic.

Transactions are stored by reference on purpose: the pipeline mutates the same
objects across stages (normalize -> categorize -> ...), and copying between
stages would silently discard classification results. Everything else that
crosses a request boundary is copied.
"""

from __future__ import annotations

import copy
import threading
from typing import Any, Dict, List, Optional

from ..models.entities import (
    AIInsight,
    AnalysisSession,
    AuditRecord,
    FinancialGoal,
    LeakFindingRecord,
    PriceChangeRecord,
    RecurrencePatternRecord,
    RoundUpCalculation,
    SafeSpareSnapshot,
    Simulation,
    UploadedDocument,
    UploadTicket,
    User,
    VoiceAsset,
)
from ..models.transaction import Transaction
from .base import (
    AnalysisRepository,
    AuditRepository,
    CalculationRepository,
    DocumentRepository,
    GoalRepository,
    InsightRepository,
    Repositories,
    TransactionRepository,
    UserRepository,
)


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: Dict[str, User] = {}
        self._by_session: Dict[str, str] = {}

    def put(self, item: User) -> User:
        with self._lock:
            self._items[item.id] = item
            self._by_session[item.session_key] = item.id
            return item

    def get(self, item_id: str) -> Optional[User]:
        with self._lock:
            return self._items.get(item_id)

    def delete(self, item_id: str) -> bool:
        with self._lock:
            user = self._items.pop(item_id, None)
            if user is not None:
                self._by_session.pop(user.session_key, None)
            return user is not None

    def list_all(self) -> List[User]:
        with self._lock:
            return list(self._items.values())

    def get_or_create_by_session_key(self, session_key: str) -> User:
        with self._lock:
            existing_id = self._by_session.get(session_key)
            if existing_id and existing_id in self._items:
                return self._items[existing_id]
            user = User(session_key=session_key)
            self._items[user.id] = user
            self._by_session[session_key] = user.id
            return user


class InMemoryAnalysisRepository(AnalysisRepository):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: Dict[str, AnalysisSession] = {}
        self._idempotency: Dict[str, str] = {}

    def put(self, item: AnalysisSession) -> AnalysisSession:
        with self._lock:
            self._items[item.id] = item
            return item

    def get(self, item_id: str) -> Optional[AnalysisSession]:
        with self._lock:
            return self._items.get(item_id)

    def delete(self, item_id: str) -> bool:
        with self._lock:
            removed = self._items.pop(item_id, None) is not None
            for key, value in list(self._idempotency.items()):
                if value == item_id:
                    del self._idempotency[key]
            return removed

    def list_all(self) -> List[AnalysisSession]:
        with self._lock:
            return list(self._items.values())

    def list_for_user(self, user_id: str) -> List[AnalysisSession]:
        with self._lock:
            return [s for s in self._items.values() if s.user_id == user_id]

    def find_by_idempotency_key(self, user_id: str, key: str) -> Optional[str]:
        with self._lock:
            return self._idempotency.get("%s::%s" % (user_id, key))

    def remember_idempotency_key(self, user_id: str, key: str, analysis_id: str) -> None:
        with self._lock:
            self._idempotency["%s::%s" % (user_id, key)] = analysis_id


class InMemoryDocumentRepository(DocumentRepository):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: Dict[str, UploadedDocument] = {}
        self._content: Dict[str, bytes] = {}
        self._tickets: Dict[str, UploadTicket] = {}

    def put(self, item: UploadedDocument) -> UploadedDocument:
        with self._lock:
            self._items[item.id] = item
            return item

    def get(self, item_id: str) -> Optional[UploadedDocument]:
        with self._lock:
            return self._items.get(item_id)

    def delete(self, item_id: str) -> bool:
        with self._lock:
            self._content.pop(item_id, None)
            return self._items.pop(item_id, None) is not None

    def list_all(self) -> List[UploadedDocument]:
        with self._lock:
            return list(self._items.values())

    def list_for_user(self, user_id: str) -> List[UploadedDocument]:
        with self._lock:
            return [d for d in self._items.values() if d.user_id == user_id]

    def put_content(self, document_id: str, data: bytes) -> None:
        with self._lock:
            self._content[document_id] = data

    def get_content(self, document_id: str) -> Optional[bytes]:
        with self._lock:
            return self._content.get(document_id)

    def purge_content(self, document_id: str) -> None:
        """§22 delete-after-processing. Bytes go first, metadata may survive."""
        with self._lock:
            self._content.pop(document_id, None)

    def put_ticket(self, ticket: UploadTicket) -> UploadTicket:
        with self._lock:
            self._tickets[ticket.id] = ticket
            return ticket

    def get_ticket(self, ticket_id: str) -> Optional[UploadTicket]:
        with self._lock:
            return self._tickets.get(ticket_id)


class InMemoryTransactionRepository(TransactionRepository):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_analysis: Dict[str, List[Transaction]] = {}
        self._index: Dict[str, str] = {}

    def replace_all(self, analysis_id: str, transactions: List[Transaction]) -> None:
        with self._lock:
            for old in self._by_analysis.get(analysis_id, []):
                self._index.pop(old.id, None)
            self._by_analysis[analysis_id] = list(transactions)
            for t in transactions:
                self._index[t.id] = analysis_id

    def list_for_analysis(self, analysis_id: str) -> List[Transaction]:
        with self._lock:
            return list(self._by_analysis.get(analysis_id, []))

    def get(self, transaction_id: str) -> Optional[Transaction]:
        with self._lock:
            analysis_id = self._index.get(transaction_id)
            if analysis_id is None:
                return None
            for t in self._by_analysis.get(analysis_id, []):
                if t.id == transaction_id:
                    return t
            return None

    def analysis_id_for(self, transaction_id: str) -> Optional[str]:
        with self._lock:
            return self._index.get(transaction_id)

    def save(self, analysis_id: str, transaction: Transaction) -> None:
        with self._lock:
            rows = self._by_analysis.setdefault(analysis_id, [])
            for index, existing in enumerate(rows):
                if existing.id == transaction.id:
                    rows[index] = transaction
                    break
            else:
                rows.append(transaction)
            self._index[transaction.id] = analysis_id

    def delete_for_analysis(self, analysis_id: str) -> None:
        with self._lock:
            for t in self._by_analysis.pop(analysis_id, []):
                self._index.pop(t.id, None)


class InMemoryCalculationRepository(CalculationRepository):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._patterns: Dict[str, List[RecurrencePatternRecord]] = {}
        self._price_changes: Dict[str, List[PriceChangeRecord]] = {}
        self._leaks: Dict[str, List[LeakFindingRecord]] = {}
        self._leak_index: Dict[str, str] = {}
        self._safe_spare: Dict[str, SafeSpareSnapshot] = {}
        self._roundups: Dict[str, RoundUpCalculation] = {}
        self._state: Dict[str, Dict[str, Any]] = {}

    def set_patterns(self, analysis_id: str, records: List[RecurrencePatternRecord]) -> None:
        with self._lock:
            self._patterns[analysis_id] = list(records)

    def get_patterns(self, analysis_id: str) -> List[RecurrencePatternRecord]:
        with self._lock:
            return list(self._patterns.get(analysis_id, []))

    def set_price_changes(self, analysis_id: str, records: List[PriceChangeRecord]) -> None:
        with self._lock:
            self._price_changes[analysis_id] = list(records)

    def get_price_changes(self, analysis_id: str) -> List[PriceChangeRecord]:
        with self._lock:
            return list(self._price_changes.get(analysis_id, []))

    def set_leaks(self, analysis_id: str, records: List[LeakFindingRecord]) -> None:
        with self._lock:
            for old in self._leaks.get(analysis_id, []):
                self._leak_index.pop(old.id, None)
            self._leaks[analysis_id] = list(records)
            for record in records:
                self._leak_index[record.id] = analysis_id

    def get_leaks(self, analysis_id: str) -> List[LeakFindingRecord]:
        with self._lock:
            return list(self._leaks.get(analysis_id, []))

    def get_leak(self, leak_id: str) -> Optional[LeakFindingRecord]:
        with self._lock:
            analysis_id = self._leak_index.get(leak_id)
            if analysis_id is None:
                return None
            for record in self._leaks.get(analysis_id, []):
                if record.id == leak_id:
                    return record
            return None

    def set_safe_spare(self, analysis_id: str, snapshot: SafeSpareSnapshot) -> None:
        with self._lock:
            self._safe_spare[analysis_id] = snapshot

    def get_safe_spare(self, analysis_id: str) -> Optional[SafeSpareSnapshot]:
        with self._lock:
            return self._safe_spare.get(analysis_id)

    def set_roundups(self, analysis_id: str, record: RoundUpCalculation) -> None:
        with self._lock:
            self._roundups[analysis_id] = record

    def get_roundups(self, analysis_id: str) -> Optional[RoundUpCalculation]:
        with self._lock:
            return self._roundups.get(analysis_id)

    def set_state(self, analysis_id: str, key: str, value: Any) -> None:
        with self._lock:
            self._state.setdefault(analysis_id, {})[key] = value

    def get_state(self, analysis_id: str, key: str, default: Any = None) -> Any:
        with self._lock:
            value = self._state.get(analysis_id, {}).get(key, default)
            # Copy mutable state so a caller cannot mutate the store by accident.
            return copy.deepcopy(value) if isinstance(value, (dict, list, set)) else value

    def delete_for_analysis(self, analysis_id: str) -> None:
        with self._lock:
            self._patterns.pop(analysis_id, None)
            self._price_changes.pop(analysis_id, None)
            for old in self._leaks.pop(analysis_id, []):
                self._leak_index.pop(old.id, None)
            self._safe_spare.pop(analysis_id, None)
            self._roundups.pop(analysis_id, None)
            self._state.pop(analysis_id, None)


class InMemoryGoalRepository(GoalRepository):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: Dict[str, FinancialGoal] = {}
        self._simulations: Dict[str, List[Simulation]] = {}

    def put(self, item: FinancialGoal) -> FinancialGoal:
        with self._lock:
            self._items[item.id] = item
            return item

    def get(self, item_id: str) -> Optional[FinancialGoal]:
        with self._lock:
            return self._items.get(item_id)

    def delete(self, item_id: str) -> bool:
        with self._lock:
            self._simulations.pop(item_id, None)
            return self._items.pop(item_id, None) is not None

    def list_all(self) -> List[FinancialGoal]:
        with self._lock:
            return list(self._items.values())

    def list_for_analysis(self, analysis_id: str) -> List[FinancialGoal]:
        with self._lock:
            return [g for g in self._items.values() if g.analysis_id == analysis_id]

    def put_simulation(self, simulation: Simulation) -> Simulation:
        with self._lock:
            self._simulations.setdefault(simulation.goal_id, []).append(simulation)
            return simulation

    def latest_simulation(self, goal_id: str) -> Optional[Simulation]:
        with self._lock:
            runs = self._simulations.get(goal_id)
            return runs[-1] if runs else None

    def delete_for_analysis(self, analysis_id: str) -> None:
        with self._lock:
            for goal_id in [g.id for g in self._items.values() if g.analysis_id == analysis_id]:
                self._items.pop(goal_id, None)
                self._simulations.pop(goal_id, None)


class InMemoryInsightRepository(InsightRepository):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._insights: Dict[str, List[AIInsight]] = {}
        self._voice: Dict[str, List[VoiceAsset]] = {}

    def set_insights(self, analysis_id: str, insights: List[AIInsight]) -> None:
        with self._lock:
            self._insights[analysis_id] = list(insights)

    def list_insights(self, analysis_id: str) -> List[AIInsight]:
        with self._lock:
            return list(self._insights.get(analysis_id, []))

    def put_voice(self, asset: VoiceAsset) -> VoiceAsset:
        with self._lock:
            self._voice.setdefault(asset.analysis_id, []).append(asset)
            return asset

    def latest_voice(self, analysis_id: str) -> Optional[VoiceAsset]:
        with self._lock:
            assets = self._voice.get(analysis_id)
            return assets[-1] if assets else None

    def delete_for_analysis(self, analysis_id: str) -> None:
        with self._lock:
            self._insights.pop(analysis_id, None)
            self._voice.pop(analysis_id, None)


class InMemoryAuditRepository(AuditRepository):
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: Dict[str, List[AuditRecord]] = {}

    def append(self, record: AuditRecord) -> AuditRecord:
        with self._lock:
            self._records.setdefault(record.analysis_id, []).append(record)
            return record

    def list_for_analysis(self, analysis_id: str) -> List[AuditRecord]:
        with self._lock:
            return list(self._records.get(analysis_id, []))

    def delete_for_analysis(self, analysis_id: str) -> None:
        with self._lock:
            self._records.pop(analysis_id, None)


def build_in_memory_repositories() -> Repositories:
    """Construction site for the whole storage layer. Swap here for DynamoDB."""
    return Repositories(
        users=InMemoryUserRepository(),
        analyses=InMemoryAnalysisRepository(),
        documents=InMemoryDocumentRepository(),
        transactions=InMemoryTransactionRepository(),
        calculations=InMemoryCalculationRepository(),
        goals=InMemoryGoalRepository(),
        insights=InMemoryInsightRepository(),
        audit=InMemoryAuditRepository(),
    )
