/**
 * Speak your expenses — the entry path for users who cannot upload or read a
 * bank statement.
 *
 * Nothing is stored until the user hears it read back and confirms it.
 */

import { useState } from 'react';

import { API_BASE_URL } from '../api/config';
import { SectionHead } from '../components/common';
import { VoiceExpense, SpokenExpense } from '../components/VoiceExpense';
import { useI18n } from '../i18n/I18nProvider';

interface Entry extends SpokenExpense {
  id: string;
  at: string;
}

export default function Speak() {
  const { t, lang } = useI18n();
  const [entries, setEntries] = useState<Entry[]>([]);

  async function record(expense: SpokenExpense) {
    // The backend re-parses authoritatively; the local parse is only a preview.
    try {
      await fetch(`${API_BASE_URL}/api/voice/parse-expense`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript: expense.transcript, language: lang.code }),
      });
    } catch {
      /* offline is fine — the entry is still shown locally and can be retried */
    }
    setEntries((list) => [
      { ...expense, id: `${Date.now()}`, at: new Date().toLocaleTimeString() },
      ...list,
    ]);
  }

  const total = entries.reduce((sum, e) => sum + (e.amount ?? 0), 0);

  return (
    <div className="wrap section">
      <SectionHead
        eyebrow="Voice entry"
        title={t('voice.title')}
        lede="No statement, no typing. Say what you spent and SafeSpare will read it back before recording it."
      />

      <VoiceExpense onCapture={record} />

      {entries.length ? (
        <div className="card" style={{ marginTop: 24 }}>
          <div className="row row--between row--baseline">
            <h2 className="display-4">Today</h2>
            <span className="figure">₹{total.toFixed(2)}</span>
          </div>
          <ul className="stack stack--sm" style={{ listStyle: 'none', padding: 0 }}>
            {entries.map((entry) => (
              <li key={entry.id} className="row row--between">
                <span>{entry.description}</span>
                <span className="mono">
                  ₹{entry.amount?.toFixed(2) ?? '—'} · {entry.at}
                </span>
              </li>
            ))}
          </ul>
          <p className="micro t-muted">
            Recorded locally for this session. Nothing has been invested or moved.
          </p>
        </div>
      ) : null}
    </div>
  );
}
