import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, Navigate, useSearchParams } from 'react-router-dom';
import { login, resendVerification } from '../../api/auth';
import { ApiError } from '../../api/client';
import { useSession, useSignedIn } from '../../state/session';
import { safeNext } from './helpers';
import { ArrowIcon, AuthField, AuthShell, FormError, PasswordInput } from './shared';

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
    <AuthShell
      badge="Sign in"
      title="Sign in to workspace"
      lede="Your construction planning pipeline: design, cost, programme and site performance."
      after={
        <div className="auth-callout">
          <div>
            <b>New engineer or surveyor?</b>
            <span>Create an account, confirm your email, then sign in here.</span>
          </div>
          <Link to="/signup" className="btn">
            Create account
          </Link>
        </div>
      }
    >
      <form
        className="auth-form"
        onSubmit={(e) => {
          e.preventDefault();
          submit.mutate();
        }}
      >
        <AuthField id="login-email" label="Work email address">
          <input
            id="login-email"
            type="email"
            autoComplete="email"
            required
            placeholder="you@example.lk"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </AuthField>

        <AuthField id="login-password" label="Password">
          <PasswordInput
            id="login-password"
            autoComplete="current-password"
            value={password}
            onChange={setPassword}
          />
        </AuthField>

        <div className="between">
          <label className="check">
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
            />
            Keep me signed in on this device
          </label>
          <Link to="/forgot-password">Forgot password?</Link>
        </div>

        {unconfirmed ? (
          <div className="alert info" role="alert">
            <div>{submit.error?.message}</div>
            {resend.isSuccess ? (
              <div>{resend.data.message}</div>
            ) : (
              <button
                type="button"
                className="ghost sm"
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

        <button className="primary auth-submit" disabled={submit.isPending}>
          {submit.isPending ? (
            'Signing in…'
          ) : (
            <>
              Sign in &amp; enter pipeline <ArrowIcon />
            </>
          )}
        </button>
      </form>
    </AuthShell>
  );
}
