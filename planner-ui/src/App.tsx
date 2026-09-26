import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, type ReactNode } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { logout } from './api/auth';
import { SIGNED_OUT_EVENT } from './api/client';
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

  const startOver = () => {
    if (!confirm('Clear this run and start over? All saved step output will be lost.')) return;
    reset();
    nav('/step/1');
  };

  const guarded = (page: ReactNode) => <RequireAuth>{page}</RequireAuth>;

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand-link">
          <div className="brand">
            Construction Planner
            <small>R26-IT-117</small>
          </div>
        </Link>
        <div className="topbar-spacer" />
        {inWizard && (
          <>
            <span className="faint mono">{run.runId.slice(0, 8)}</span>
            <button className="ghost" onClick={startOver}>
              Start over
            </button>
          </>
        )}
        {user ? (
          <div className="account">
            <span className="faint">{user.email}</span>
            <button className="ghost" disabled={signOut.isPending} onClick={() => signOut.mutate()}>
              Log out
            </button>
          </div>
        ) : (
          !AUTH_PAGES.includes(pathname) && (
            <div className="account">
              <Link to="/login">Log in</Link>
              <Link to="/signup">Sign up</Link>
            </div>
          )
        )}
      </header>

      {inWizard && <Stepper run={run} />}

      <main className="container">
        <Routes>
          <Route path="/" element={<Landing run={run} />} />
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
