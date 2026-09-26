import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useSession } from '../state/session';
import { ErrorBox, Loading } from './ui';

/** Wraps pages that need a signed-in user; everyone else is sent to log in
 *  and brought back here afterwards. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, isLoading, error, retry } = useSession();
  const location = useLocation();

  if (isLoading) return <Loading what="Checking your session" />;
  // Not "signed out" (that is a null user) but the gateway being unreachable.
  if (error) return <ErrorBox error={error} onRetry={() => retry()} />;
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <>{children}</>;
}
