/** Shared fetch wrapper. Surfaces backend validation messages instead of
 *  swallowing them — C04 in particular returns useful `details` arrays. */

export class ApiError extends Error {
  readonly status: number;
  readonly details: string[];
  readonly service?: string;

  constructor(message: string, status: number, details: string[] = [], service?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
    this.service = service;
  }
}

/** Every service is reached through the gateway, on this page's own origin.
 *  In dev, Vite forwards /api to the gateway (see vite.config.ts); in
 *  production the gateway serves the same paths. */
export const BASE = {
  auth: '/api/auth',
  c01: '/api/c01',
  c02: '/api/c02',
  c03: '/api/c03',
  c04: '/api/c04',
};

/** Fired when a service call comes back 401: the session ended (timed out,
 *  or signed out elsewhere). App listens and sends the user to log in. */
export const SIGNED_OUT_EVENT = 'r26:signed-out';

/** Pull a human-usable message out of whatever shape the service returned. */
function extract(body: unknown, status: number): { message: string; details: string[] } {
  if (body && typeof body === 'object') {
    const b = body as Record<string, unknown>;

    // C04 (Flask): { success: false, error, details: string[] }
    if (typeof b.error === 'string') {
      const details = Array.isArray(b.details) ? (b.details as string[]).map(String) : [];
      return { message: b.error, details };
    }

    // FastAPI: { detail: string } or { detail: [{ loc, msg, ... }] }
    if (typeof b.detail === 'string') return { message: b.detail, details: [] };
    if (Array.isArray(b.detail)) {
      const details = (b.detail as Record<string, unknown>[]).map((d) => {
        const loc = Array.isArray(d.loc) ? d.loc.filter((p) => p !== 'body').join('.') : '';
        return loc ? `${loc}: ${String(d.msg)}` : String(d.msg);
      });
      return { message: 'Validation failed', details };
    }
  }
  return { message: `Request failed (HTTP ${status})`, details: [] };
}

export async function request<T>(
  service: keyof typeof BASE,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const url = `${BASE[service]}${path}`;

  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        ...init?.headers,
      },
    });
  } catch {
    // Network-level failure. A service being down is not this case: the
    // gateway answers for it with a 502 that extract() turns into a message.
    throw new ApiError(
      'Cannot reach the API gateway. Is it running?',
      0,
      [],
      service,
    );
  }

  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!res.ok) {
    // /auth answers 401 for a wrong password or "not signed in yet", which
    // the auth pages handle themselves; anywhere else it means the session died.
    if (res.status === 401 && service !== 'auth') {
      window.dispatchEvent(new Event(SIGNED_OUT_EVENT));
    }
    const { message, details } = extract(body, res.status);
    throw new ApiError(message, res.status, details, service);
  }
  return body as T;
}

export const get = <T,>(s: keyof typeof BASE, p: string) => request<T>(s, p);

export const post = <T,>(s: keyof typeof BASE, p: string, payload: unknown) =>
  request<T>(s, p, { method: 'POST', body: JSON.stringify(payload) });

export const patch = <T,>(s: keyof typeof BASE, p: string, payload: unknown) =>
  request<T>(s, p, { method: 'PATCH', body: JSON.stringify(payload) });
