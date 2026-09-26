import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { resetPassword } from '../../api/auth';
import { ApiError } from '../../api/client';
import { ME_KEY } from '../../state/session';
import { MIN_PASSWORD_LENGTH, passwordProblem, useLinkToken } from './helpers';
import { AuthLayout, FormError } from './shared';

export function ResetPassword() {
  const token = useLinkToken();
  const queryClient = useQueryClient();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  const submit = useMutation({
    mutationFn: () => resetPassword(token ?? '', password),
    // The reset ended every session, this browser's included.
    onSuccess: () => queryClient.setQueryData(ME_KEY, null),
  });

  if (!token) {
    return (
      <AuthLayout title="Choose a new password">
        <div className="alert error">
          This link is incomplete. Open the link from your email again, or{' '}
          <Link to="/forgot-password">ask for a new one</Link>.
        </div>
      </AuthLayout>
    );
  }

  if (submit.isSuccess) {
    return (
      <AuthLayout title="Password changed">
        <div className="stack">
          <p>{submit.data.message} Every device that was signed in has been signed out.</p>
          <Link to="/login">Log in</Link>
        </div>
      </AuthLayout>
    );
  }

  const deadLink = submit.error instanceof ApiError && submit.error.status === 400;

  return (
    <AuthLayout title="Choose a new password">
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
          New password
          <input
            type="password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <span className="field-hint">At least {MIN_PASSWORD_LENGTH} characters.</span>
        </label>
        <label className="field">
          Confirm new password
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
        {deadLink && <Link to="/forgot-password">Ask for a new link</Link>}

        <button className="primary" disabled={submit.isPending}>
          {submit.isPending ? 'Saving…' : 'Change password'}
        </button>
      </form>
    </AuthLayout>
  );
}
