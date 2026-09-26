import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { forgotPassword } from '../../api/auth';
import { AuthLayout, FormError } from './shared';

export function ForgotPassword() {
  const [email, setEmail] = useState('');
  const submit = useMutation({ mutationFn: () => forgotPassword(email) });

  const back = (
    <>
      Remembered it? <Link to="/login">Log in</Link>
    </>
  );

  if (submit.isSuccess) {
    return (
      <AuthLayout title="Check your email" footer={back}>
        <p>{submit.data.message} The link expires in 30 minutes.</p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="We'll email you a link to choose a new one."
      footer={back}
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
        {submit.error && <FormError error={submit.error} />}
        <button className="primary" disabled={submit.isPending}>
          {submit.isPending ? 'Sending…' : 'Send reset link'}
        </button>
      </form>
    </AuthLayout>
  );
}
