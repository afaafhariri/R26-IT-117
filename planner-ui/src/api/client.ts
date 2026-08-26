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

function envUrl(key: string, fallback: string): string {
  const v = (import.meta.env as Record<string, string | undefined>)[key];
  return (v ?? fallback).replace(/\/$/, '');
}

export const BASE = {
  c01: envUrl('VITE_C01_URL', 'http://localhost:8001'),
  c02: envUrl('VITE_C02_URL', 'http://localhost:8002'),
  c03: envUrl('VITE_C03_URL', 'http://localhost:8000'),
  c04: envUrl('VITE_C04_URL', 'http://localhost:5004'),
};

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
    // Network-level failure: service down, or a CORS preflight rejection.
    throw new ApiError(
      `Cannot reach ${service.toUpperCase()} at ${BASE[service]}. Is the service running?`,
      0,
      ['If the service is up, this is usually a CORS problem.'],
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
    const { message, details } = extract(body, res.status);
    throw new ApiError(message, res.status, details, service);
  }
  return body as T;
}

export const get = <T,>(s: keyof typeof BASE, p: string) => request<T>(s, p);

export const post = <T,>(s: keyof typeof BASE, p: string, payload: unknown) =>
  request<T>(s, p, { method: 'POST', body: JSON.stringify(payload) });
