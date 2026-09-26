import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, Navigate, useSearchParams } from 'react-router-dom';
import { login, resendVerification } from '../../api/auth';
import { ApiError } from '../../api/client';
import { useSession, useSignedIn } from '../../state/session';
import { safeNext } from './helpers';
import { AuthLayout, FormError } from './shared';

export function Login() {
  const [params] = useSearchParams();
  const next = safeNext(params.get('next'));
  const { user } = useSession();
  const signedIn = useSignedIn();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);

  const submit = useMutation({
    mutationFn: () => login(email, password, rememberMe),
    onSuccess: signedIn,
  });
  const resend = useMutation({ mutationFn: () => resendVerification(email) });

  // Also where a successful login lands: signedIn() fills in the user.
  if (user) return <Navigate to={next} replace />;

  const unconfirmed = submit.error instanceof ApiError && submit.error.status === 403;

  return (
    <AuthLayout
      title="Log in"
      footer={
        <>
          New here? <Link to="/signup">Create an account</Link>
        </>
      }
    >
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          submit.mutate();
        }}
      >
        <label className="field">
          Email
          <input
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="field">
          Password
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={rememberMe}
            onChange={(e) => setRememberMe(e.target.checked)}
          />
          Keep me signed in on this device
        </label>

        {unconfirmed ? (
          <div className="alert info" role="alert">
            <div>{submit.error?.message}</div>
            {resend.isSuccess ? (
              <div>{resend.data.message}</div>
            ) : (
              <button
                type="button"
                className="ghost"
                disabled={resend.isPending}
                onClick={() => resend.mutate()}
              >
                Send a new link
              </button>
            )}
            {resend.error && <FormError error={resend.error} />}
          </div>
        ) : (
          submit.error && <FormError error={submit.error} />
        )}

        <button className="primary" disabled={submit.isPending}>
          {submit.isPending ? 'Logging in…' : 'Log in'}
        </button>
        <Link to="/forgot-password">Forgot your password?</Link>
      </form>
    </AuthLayout>
  );
}
