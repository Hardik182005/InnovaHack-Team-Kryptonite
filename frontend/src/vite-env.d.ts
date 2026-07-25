/// <reference types="vite/client" />

/* Only non-secret configuration is ever read from the environment. Vite inlines
   every VITE_* value into the browser bundle, so provider keys must never be
   declared here (spec §3.16, §29.17). */
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_DATA_MODE?: string;
  readonly VITE_API_TIMEOUT_MS?: string;
  /** Convenience alias for VITE_DATA_MODE=fixtures. */
  readonly VITE_USE_FIXTURES?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
