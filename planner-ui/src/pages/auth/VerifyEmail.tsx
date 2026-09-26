import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { verifyEmail } from '../../api/auth';
import { ApiError } from '../../api/client';
import { useSignedIn } from '../../state/session';
import { useLinkToken } from './helpers';
import { AuthLayout, FormError } from './shared';

/** Opened from the confirmation email. The gateway needs the link *and* the
 *  password, so a link opened by someone else can't activate the account. */
export function VerifyEmail() {
  const token = useLinkToken();
  const signedIn = useSignedIn();
  const navigate = useNavigate();
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);

  const submit = useMutation({
    mutationFn: () => verifyEmail(token ?? '', password, rememberMe),
    onSuccess: (user) => {
      signedIn(user);
      navigate('/step/1', { replace: true });
    },
  });

  if (!token) {
    return (
      <AuthLayout title="Confirm your email">
        <div className="alert error">
          This link is incomplete. Open the link from your email again, or{' '}
          <Link to="/login">log in</Link> to get a new one.
        </div>
      </AuthLayout>
    );
  }

  const wrongPassword = submit.error instanceof ApiError && submit.error.status === 401;
  const deadLink = submit.error instanceof ApiError && submit.error.status === 400;

  return (
    <AuthLayout
      title="Confirm your email"
      subtitle="Enter the password you chose when you signed up."
    >
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          submit.mutate();
        }}
      >
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

        {submit.error && <FormError error={submit.error} />}
        {wrongPassword && <Link to="/forgot-password">Forgot your password?</Link>}
        {deadLink && <Link to="/login">Go to log in</Link>}

        <button className="primary" disabled={submit.isPending}>
          {submit.isPending ? 'Confirming…' : 'Confirm and continue'}
        </button>
      </form>
    </AuthLayout>
  );
}
