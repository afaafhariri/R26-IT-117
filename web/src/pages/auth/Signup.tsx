import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { resendVerification, signup } from '../../api/auth';
import { useSession } from '../../state/session';
import { MIN_PASSWORD_LENGTH, passwordProblem } from './helpers';
import { ArrowIcon, AuthField, AuthShell, FormError, PasswordInput } from './shared';

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
      <AuthShell aside="signup" badge="REG-01 // Sent" title="Check your email">
        <div className="auth-message">
          <p>
            We've sent a link to <strong>{email}</strong>. Open it to confirm your address and
            finish signing up. It expires in 24 hours.
          </p>
          {resend.isSuccess ? (
            <p className="faint">{resend.data.message}</p>
          ) : (
            <div>
              <button className="sm" disabled={resend.isPending} onClick={() => resend.mutate()}>
                Didn't get it? Send it again
              </button>
            </div>
          )}
          {resend.error && <FormError error={resend.error} />}
          <Link to="/login" className="auth-link">
            Go to sign in
          </Link>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      aside="signup"
      badge="REG-01 // Registry"
      title="Create engineering account"
      lede="Access the C01–C04 planning engines for Sri Lankan residential projects."
    >
      <form
        className="auth-form"
        onSubmit={(e) => {
          e.preventDefault();
          const p = passwordProblem(password, confirm);
          setProblem(p);
          if (!p) submit.mutate();
        }}
      >
        <AuthField id="signup-email" label="Professional email *" hint="Confirmation link sent here">
          <input
            id="signup-email"
            type="email"
            autoComplete="email"
            required
            placeholder="you@example.lk"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </AuthField>

        <div className="auth-pair">
          <AuthField id="signup-password" label="Password *">
            <PasswordInput
              id="signup-password"
              autoComplete="new-password"
              minLength={MIN_PASSWORD_LENGTH}
              value={password}
              onChange={setPassword}
            />
          </AuthField>
          <AuthField id="signup-confirm" label="Confirm password *">
            <PasswordInput
              id="signup-confirm"
              autoComplete="new-password"
              value={confirm}
              onChange={setConfirm}
            />
          </AuthField>
        </div>
        <span className="field-hint">
          At least {MIN_PASSWORD_LENGTH} characters. A few unrelated words work well; no symbols
          required.
        </span>

        {problem && <div className="alert error">{problem}</div>}
        {submit.error && <FormError error={submit.error} />}

        <button className="primary auth-submit" disabled={submit.isPending}>
          {submit.isPending ? (
            'Creating account…'
          ) : (
            <>
              Create account &amp; workspace <ArrowIcon />
            </>
          )}
        </button>
        <Link to="/login" className="auth-link">
          Already registered? Sign in to your workspace
        </Link>
      </form>
    </AuthShell>
  );
}
