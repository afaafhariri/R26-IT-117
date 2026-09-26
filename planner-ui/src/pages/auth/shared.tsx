import type { ReactNode } from 'react';
import { ApiError } from '../../api/client';
import { Card } from '../../components/ui';

export function AuthLayout({
  title,
  subtitle,
  footer,
  children,
}: {
  title: string;
  subtitle?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="auth">
      <Card title={title} subtitle={subtitle}>
        {children}
      </Card>
      {footer && <p className="auth-footer faint">{footer}</p>}
    </div>
  );
}

/** The gateway's own message, without the "AUTH:" prefix ErrorBox would add. */
export function FormError({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  const details = error instanceof ApiError ? error.details : [];
  return (
    <div className="alert error" role="alert">
      {message}
      {details.length > 0 && (
        <ul>
          {details.map((d) => (
            <li key={d}>{d}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
