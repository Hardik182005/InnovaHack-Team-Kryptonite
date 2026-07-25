/* ============================================================================
   Error handling.

   Spec §5: the UI must never display raw backend error text. Every failure is
   translated here into a stable code plus a sentence written for a
   non-technical person. The original detail is kept on the object for
   debugging but is never rendered.
   ========================================================================= */

export type ApiErrorKind =
  | 'offline'
  | 'timeout'
  | 'unreachable'
  | 'not_found'
  | 'validation'
  | 'too_large'
  | 'password_required'
  | 'password_incorrect'
  | 'unsupported_type'
  | 'rate_limited'
  | 'provider_unavailable'
  | 'server'
  | 'unknown';

const MESSAGES: Record<ApiErrorKind, string> = {
  offline: 'You appear to be offline. Reconnect and try again — nothing was lost.',
  timeout: 'That took longer than expected. The service may be busy.',
  unreachable: 'We could not reach the analysis service.',
  not_found: 'We could not find that analysis. It may have been deleted.',
  validation: 'Some of the details supplied were not accepted. Please review and try again.',
  too_large: 'That file is larger than the 15 MB limit.',
  password_required: 'This PDF is password protected. Enter its password to continue.',
  password_incorrect: 'That password did not open the document. Please check and try again.',
  unsupported_type: 'That file type is not supported.',
  rate_limited: 'Too many requests in a short time. Please wait a moment and try again.',
  provider_unavailable:
    'The AI service is unavailable right now. All calculated figures are still available — only the written explanation is affected.',
  server: 'Something went wrong on our side. Your data was not changed.',
  unknown: 'Something unexpected happened. Please try again.',
};

/** Backend error codes we understand, mapped to a kind. */
const CODE_MAP: Record<string, ApiErrorKind> = {
  PASSWORD_REQUIRED: 'password_required',
  PASSWORD_INCORRECT: 'password_incorrect',
  UNSUPPORTED_FILE_TYPE: 'unsupported_type',
  FILE_TOO_LARGE: 'too_large',
  PROVIDER_UNAVAILABLE: 'provider_unavailable',
  RATE_LIMITED: 'rate_limited',
};

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string | null;
  /** Raw server detail. Kept for the console; never rendered. */
  readonly detail: string | null;
  readonly retryable: boolean;

  constructor(kind: ApiErrorKind, opts: { status?: number | null; code?: string | null; detail?: string | null } = {}) {
    super(MESSAGES[kind]);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = opts.status ?? null;
    this.code = opts.code ?? null;
    this.detail = opts.detail ?? null;
    this.retryable = kind === 'timeout' || kind === 'unreachable' || kind === 'offline' || kind === 'server';
  }

  /** The only string that may be shown to a user. */
  get userMessage(): string {
    return MESSAGES[this.kind];
  }

  static fromStatus(status: number, body: unknown): ApiError {
    const code = extractCode(body);
    const detail = extractDetail(body);
    if (code && CODE_MAP[code]) {
      return new ApiError(CODE_MAP[code] as ApiErrorKind, { status, code, detail });
    }
    if (status === 404) return new ApiError('not_found', { status, code, detail });
    if (status === 413) return new ApiError('too_large', { status, code, detail });
    if (status === 415) return new ApiError('unsupported_type', { status, code, detail });
    if (status === 422 || status === 400) return new ApiError('validation', { status, code, detail });
    if (status === 429) return new ApiError('rate_limited', { status, code, detail });
    if (status === 503) return new ApiError('provider_unavailable', { status, code, detail });
    if (status >= 500) return new ApiError('server', { status, code, detail });
    return new ApiError('unknown', { status, code, detail });
  }
}

function extractCode(body: unknown): string | null {
  if (body && typeof body === 'object') {
    const b = body as Record<string, unknown>;
    if (typeof b.code === 'string') return b.code;
    if (b.error && typeof b.error === 'object') {
      const e = b.error as Record<string, unknown>;
      if (typeof e.code === 'string') return e.code;
    }
  }
  return null;
}

function extractDetail(body: unknown): string | null {
  if (typeof body === 'string') return body.slice(0, 500);
  if (body && typeof body === 'object') {
    const b = body as Record<string, unknown>;
    if (typeof b.detail === 'string') return b.detail.slice(0, 500);
    if (typeof b.message === 'string') return b.message.slice(0, 500);
  }
  return null;
}

/** Coerce anything thrown into an ApiError so the UI has one shape to render. */
export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    return new ApiError('offline');
  }
  if (err instanceof DOMException && err.name === 'AbortError') {
    return new ApiError('timeout');
  }
  if (err instanceof TypeError) {
    // fetch() throws TypeError when the connection cannot be established.
    return new ApiError('unreachable', { detail: err.message });
  }
  return new ApiError('unknown', { detail: err instanceof Error ? err.message : null });
}
