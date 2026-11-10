import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

/** Mirrors the gateway's rule, so a short password is caught before sending. */
export const MIN_PASSWORD_LENGTH = 12;

export function passwordProblem(password: string, confirm: string): string | null {
  if ([...password].length < MIN_PASSWORD_LENGTH) {
    return `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  if (password !== confirm) return "The two passwords don't match.";
  return null;
}

/** Where to go after logging in. `next` comes from the URL, so only a path on
 *  this site is accepted; anything else could bounce the user to another site. */
export function safeNext(next: string | null): string {
  if (next && next.startsWith('/') && !next.startsWith('//') && !next.startsWith('/\\')) {
    return next;
  }
  return '/step/1';
}

/** The token from an emailed link. It arrives in the #fragment, which is
 *  never sent to a server or leaked in a Referer header. Read it once, then
 *  drop it from the address bar so it isn't left in the history. */
export function useLinkToken(): string | null {
  const location = useLocation();
  const navigate = useNavigate();
  const [token] = useState(() => new URLSearchParams(location.hash.slice(1)).get('token'));

  useEffect(() => {
    if (location.hash) navigate(location.pathname, { replace: true });
  }, [location.hash, location.pathname, navigate]);

  return token;
}
