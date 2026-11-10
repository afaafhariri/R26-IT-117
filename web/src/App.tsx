import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { logout } from './api/auth';
import { SIGNED_OUT_EVENT } from './api/client';
import { ConfirmDialog } from './components/ConfirmDialog';
import { RequireAuth } from './components/RequireAuth';
import { Stepper } from './components/Stepper';
import { releaseRun, useRun } from './state/runStore';
import { ME_KEY, useSession } from './state/session';
import { Step1Design } from './pages/Step1Design';
import { Step2Cost } from './pages/Step2Cost';
import { Step3Timeline } from './pages/Step3Timeline';
import { Step4Performance } from './pages/Step4Performance';
import { Review } from './pages/Review';
import { Landing } from './pages/Landing';
import { Overview } from './pages/Overview';
import { Login } from './pages/auth/Login';
import { Signup } from './pages/auth/Signup';
import { VerifyEmail } from './pages/auth/VerifyEmail';
import { ForgotPassword } from './pages/auth/ForgotPassword';
import { ResetPassword } from './pages/auth/ResetPassword';

const AUTH_PAGES = ['/login', '/signup', '/verify-email', '/forgot-password', '/reset-password'];

export default function App() {
  const { run, update, reset } = useRun();
  const { user } = useSession();
  const queryClient = useQueryClient();
  const nav = useNavigate();
  const { pathname } = useLocation();

  // The stepper and the run controls only make sense inside the wizard, not
  // on the landing page (the marketing front door) or the account pages.
  const inWizard = !!user && (pathname.startsWith('/step/') || pathname === '/review');

  // A service call came back 401: the session timed out or was ended
  // elsewhere. Forgetting the user makes RequireAuth send them to log in.
  useEffect(() => {
    const signedOut = () => queryClient.setQueryData(ME_KEY, null);
    window.addEventListener(SIGNED_OUT_EVENT, signedOut);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, signedOut);
  }, [queryClient]);

  const signOut = useMutation({
    mutationFn: logout,
    // Cleared even if the request fails: the user asked to be signed out here.
    // A full page load, not a client-side navigation, so nothing of theirs
    // survives in memory either (React Query's cache holds their project data).
    onSettled: () => {
      releaseRun();
      window.location.replace('/');
    },
  });

  // Asked in our own dialog rather than window.confirm(); confirming does
  // exactly what it always did.
  const [confirmingReset, setConfirmingReset] = useState(false);
  const cancelReset = useCallback(() => setConfirmingReset(false), []);
  const startOver = () => {
    setConfirmingReset(false);
    reset();
    nav('/step/1');
  };

  const guarded = (page: ReactNode) => <RequireAuth>{page}</RequireAuth>;
  // Full-bleed marketing pages share the section nav; on the overview its
  // anchors point back at the landing page's sections.
  const publicPage = pathname === '/' || pathname === '/pipeline';
  const anchorBase = pathname === '/' ? '' : '/';

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand-link">
          <BrandMark />
          <div className="brand">
            R26 Planner
            <small>AI architecture &amp; engineering</small>
          </div>
        </Link>
        {publicPage && (
          <nav className="topbar-nav" aria-label="Components">
            <a href={`${anchorBase}#c01`}>01. Architecture</a>
            <a href={`${anchorBase}#c02`}>02. Cost estimation</a>
            <a href={`${anchorBase}#c03`}>03. Timeline</a>
            <a href={`${anchorBase}#c04`}>04. Site performance</a>
            <Link to="/pipeline" aria-current={pathname === '/pipeline' ? 'page' : undefined}>
              Pipeline overview
            </Link>
          </nav>
        )}
        <div className="topbar-spacer" />
        <div className="topbar-meta">
          {inWizard && (
            <>
              <button className="ghost sm" onClick={() => setConfirmingReset(true)}>
                Start over
              </button>
            </>
          )}
          {user ? (
            <div className="account">
              <span className="who">{user.email}</span>
              <button
                className="sm"
                disabled={signOut.isPending}
                onClick={() => signOut.mutate()}
              >
                Sign out
              </button>
            </div>
          ) : (
            !AUTH_PAGES.includes(pathname) && (
              <div className="account">
                <Link to="/login" className="btn sm-link">
                  Sign in
                </Link>
                <Link to="/signup" className="btn primary sm-link">
                  Sign up
                </Link>
              </div>
            )
          )}
        </div>
      </header>

      {inWizard && <Stepper run={run} />}

      {confirmingReset && (
        <ConfirmDialog
          title="Clear this run and start over?"
          confirmLabel="Clear run & start over"
          cancelLabel="Keep my run"
          onConfirm={startOver}
          onCancel={cancelReset}
        >
          <p>
            All saved step output will be lost: the design, the cost estimate, the timeline and any
            recorded site progress in this browser.
          </p>
        </ConfirmDialog>
      )}

      <main className={publicPage ? 'container bleed' : 'container'}>
        <Routes>
          <Route path="/" element={<Landing run={run} />} />
          <Route path="/pipeline" element={<Overview run={run} />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/verify-email" element={<VerifyEmail />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/step/1" element={guarded(<Step1Design run={run} update={update} />)} />
          <Route path="/step/2" element={guarded(<Step2Cost run={run} update={update} />)} />
          <Route path="/step/3" element={guarded(<Step3Timeline run={run} update={update} />)} />
          <Route path="/step/4" element={guarded(<Step4Performance run={run} update={update} />)} />
          <Route path="/review" element={guarded(<Review run={run} />)} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

/** Bauhaus mark: an ink block cut by a terracotta quadrant. */
function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" fill="var(--ink)" />
      <path d="M8 24V8a16 16 0 0 1 16 16Z" fill="var(--terra)" />
      <rect x="8" y="24" width="16" height="2" fill="var(--on-ink)" />
    </svg>
  );
}
