import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { resendVerification, signup } from '../../api/auth';
import { useSession } from '../../state/session';
import { MIN_PASSWORD_LENGTH, passwordProblem } from './helpers';
import { AuthLayout, FormError } from './shared';

export function Signup() {
  const { user } = useSession();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  const submit = useMutation({ mutationFn: () => signup(email, password) });
  const resend = useMutation({ mutationFn: () => resendVerification(email) });

  if (user) return <Navigate to="/step/1" replace />;

  // Shown whether or not the address already had an account: the gateway
  // answers the same either way, and so does this page.
  if (submit.isSuccess) {
    return (
      <AuthLayout title="Check your email">
        <div className="stack">
          <p>
            We've sent a link to <strong>{email}</strong>. Open it to confirm your address and
            finish signing up. It expires in 24 hours.
          </p>
          {resend.isSuccess ? (
            <p className="faint">{resend.data.message}</p>
          ) : (
            <button className="ghost" disabled={resend.isPending} onClick={() => resend.mutate()}>
              Didn't get it? Send it again
            </button>
          )}
          {resend.error && <FormError error={resend.error} />}
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Create an account"
      footer={
        <>
          Already have an account? <Link to="/login">Log in</Link>
        </>
      }
    >
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          const p = passwordProblem(password, confirm);
          setProblem(p);
          if (!p) submit.mutate();
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
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <span className="field-hint">
            At least {MIN_PASSWORD_LENGTH} characters. A few unrelated words work well.
          </span>
        </label>
        <label className="field">
          Confirm password
          <input
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </label>

        {problem && <div className="alert error">{problem}</div>}
        {submit.error && <FormError error={submit.error} />}

        <button className="primary" disabled={submit.isPending}>
          {submit.isPending ? 'Creating account…' : 'Create account'}
        </button>
      </form>
    </AuthLayout>
  );
}
