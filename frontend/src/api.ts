export type Persona = 'employee' | 'manager';
export type DemoSession = {
  persona: Persona; profile: { id: string; displayName: string; grade?: string };
  csrfToken: string; expiresAt: string;
};
export type Header = { name: string; startDate: string; endDate: string; businessPurpose: string };
export type Report = Header & { id: string; status: 'draft' | 'submitted' | 'partially_approved' | 'approved'; version: number; currency: 'GBP'; createdAt: string };
export type Proposal = {
  header: Header; proposalToken: string; message: string; questions: string[];
  ready: boolean; parser: 'deterministic-v1';
};

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public fields: { field: string; message: string }[] = []) {
    super(message);
  }
}

export async function api<T>(path: string, options: { method?: string; body?: unknown; csrf?: string; signal?: AbortSignal } = {}): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), options.body instanceof FormData ? 180000 : 10000);
  const abort = () => controller.abort();
  options.signal?.addEventListener('abort', abort, { once: true });
  if (options.signal?.aborted) controller.abort();
  try {
    const response = await fetch(`/api${path}`, {
      method: options.method ?? 'GET', credentials: 'same-origin', cache: 'no-store',
      headers: { ...(options.body !== undefined && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
        ...(options.csrf ? { 'X-CSRF-Token': options.csrf } : {}) },
      body: options.body === undefined ? undefined : options.body instanceof FormData ? options.body : JSON.stringify(options.body), signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) throw new ApiError(response.status, data.error?.code ?? 'request_failed',
      data.error?.message ?? 'The request failed. Try again.', data.fields ?? []);
    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (options.signal?.aborted) throw error;
    throw new ApiError(0, 'connection_failed', 'Cannot reach the workspace. Check the connection and try again.');
  } finally {
    window.clearTimeout(timer);
    options.signal?.removeEventListener('abort', abort);
  }
}

let bootstrap: Promise<DemoSession> | null = null;
const SESSION_STARTED = 'unloop-demo-started';
export function rememberSession() { window.sessionStorage.setItem(SESSION_STARTED, 'true'); }
export function loadSession(): Promise<DemoSession> {
  // React StrictMode can mount twice; share bootstrap to avoid orphan demo sessions.
  if (!bootstrap) bootstrap = api<DemoSession>('/session').catch(error => {
    if (error instanceof ApiError && error.code === 'session_required') {
      if (window.sessionStorage.getItem(SESSION_STARTED) === 'true')
        throw new ApiError(401, 'session_expired', 'Your demo session ended. Start a new one explicitly.');
      return api<DemoSession>('/session', { method: 'POST', body: {} });
    }
    throw error;
  }).then(value => { rememberSession(); return value; }).finally(() => { bootstrap = null; });
  return bootstrap;
}

export const dateLabel = (value: string) => new Intl.DateTimeFormat('en-GB', {
  day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
}).format(new Date(`${value}T00:00:00Z`));
