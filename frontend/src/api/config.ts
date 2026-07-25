/* ============================================================================
   Data-source configuration.

   Three modes:
     live     — the FastAPI backend only. Failures surface as retry states.
     fixtures — bundled demo payloads. No network call is ever made.
     auto     — try live; on connection failure fall back to fixtures and raise
                a persistent, clearly-labelled banner.

   NO SECRETS LIVE HERE. Vite inlines every VITE_* value into the bundle, so a
   provider key placed in .env would ship to every browser (§3.16, §29.17).
   The only configuration read is a base URL and a timeout.
   ========================================================================= */

export type DataMode = 'auto' | 'live' | 'fixtures';

const STORAGE_KEY = 'safespare.dataMode';

function envMode(): DataMode {
  // VITE_USE_FIXTURES=true is a convenience alias for VITE_DATA_MODE=fixtures.
  const alias = (import.meta.env.VITE_USE_FIXTURES ?? '').toString().toLowerCase();
  if (alias === 'true' || alias === '1') return 'fixtures';
  const raw = (import.meta.env.VITE_DATA_MODE ?? 'auto').toString().toLowerCase();
  return raw === 'live' || raw === 'fixtures' ? raw : 'auto';
}

export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL ?? '').toString().replace(/\/+$/, '');

export const API_TIMEOUT_MS: number = Number.parseInt(
  (import.meta.env.VITE_API_TIMEOUT_MS ?? '15000').toString(),
  10,
);

function readStored(): DataMode | null {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v === 'auto' || v === 'live' || v === 'fixtures' ? v : null;
  } catch {
    return null;
  }
}

let current: DataMode = readStored() ?? envMode();

/** True once `auto` has fallen back because the backend was unreachable. */
let fellBack = false;

type Listener = () => void;
const listeners = new Set<Listener>();

function emit(): void {
  listeners.forEach((l) => l());
}

export const dataSource = {
  get mode(): DataMode {
    return current;
  },
  get usingFixtures(): boolean {
    return current === 'fixtures' || (current === 'auto' && fellBack);
  },
  get fellBack(): boolean {
    return fellBack;
  },
  setMode(mode: DataMode): void {
    current = mode;
    if (mode !== 'auto') fellBack = false;
    try {
      window.localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      /* storage unavailable — mode stays in memory only */
    }
    emit();
  },
  markFellBack(): void {
    if (!fellBack) {
      fellBack = true;
      emit();
    }
  },
  clearFallback(): void {
    if (fellBack) {
      fellBack = false;
      emit();
    }
  },
  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};
