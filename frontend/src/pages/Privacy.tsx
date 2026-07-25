/** Privacy and deletion — §22. */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { api, activeAnalysisId } from '../api/client';
import { ConfirmDialog, ErrorState, SectionHead } from '../components/common';
import { Icon } from '../components/Icon';
import { useMutation } from '../hooks/useResource';
import { AppShell } from '../components/AppShell';
import { useI18n } from '../i18n/I18nProvider';

const PROMISES = [
  'Your statement is analysed to calculate figures — it is never sold or shared.',
  'Account numbers are masked and never stored.',
  'Uploaded files can be deleted automatically once processing finishes.',
  'AI providers receive only a minimal summary, never your full statement.',
  'No API key is ever present in this page.',
  'SafeSpare never executes an investment, transfer or cancellation.',
];

export default function Privacy() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);
  const [done, setDone] = useState(false);
  const hasAnalysis = Boolean(activeAnalysisId());

  const remove = useMutation(async () => {
    const out = await api.deleteAllData();
    setDone(true);
    return out;
  });

  return (
    <AppShell title={t('page.privacy')}>
      <SectionHead eyebrow="Privacy" title={t('page.privacy')} />

      <div className="card">
        <ul className="stack stack--sm" style={{ listStyle: 'none', padding: 0 }}>
          {PROMISES.map((line) => (
            <li key={line} className="checkline"><Icon.check size={15} className="t-accent" /> {line}</li>
          ))}
        </ul>
      </div>

      <div className="card" style={{ marginTop: 24 }}>
        <h2 className="display-4">Delete everything</h2>
        <p className="prose t-muted">
          Removes your uploaded statements and every figure derived from them. This cannot be undone.
        </p>
        {done ? (
          <p className="notice notice--positive" role="status">
            Your data has been deleted.{' '}
            <button className="btn btn--sm btn--ghost" type="button" onClick={() => navigate('/')}>
              Back to start
            </button>
          </p>
        ) : (
          <button className="btn btn--danger" type="button"
                  onClick={() => setConfirming(true)} disabled={!hasAnalysis || remove.pending}>
            {hasAnalysis ? 'Delete my data' : 'Nothing to delete'}
          </button>
        )}
        {remove.error ? <ErrorState error={remove.error} /> : null}
      </div>

      <ConfirmDialog
        open={confirming}
        title="Delete all your data?"
        danger
        confirmLabel="Delete permanently"
        body={<p>Your statements and every calculated figure will be removed. This cannot be undone.</p>}
        onCancel={() => setConfirming(false)}
        onConfirm={() => { setConfirming(false); void remove.run(); }}
      />
    </AppShell>
  );
}
