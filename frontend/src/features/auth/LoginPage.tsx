import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useLocation, useNavigate } from 'react-router';
import { z } from 'zod';

import { ApiError } from '@/api/client';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Alert } from '@/components/ui/feedback';
import { FieldError, Input, Label } from '@/components/ui/input';
import { usePageTitle } from '@/hooks/usePageTitle';

import { useAuth } from './useAuth';

const schema = z.object({
  email: z.email('Enter a valid e-mail address.'),
  password: z.string().min(1, 'Enter your password.'),
});
type Values = z.infer<typeof schema>;

export function LoginPage() {
  usePageTitle('Sign in');
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  const from = (location.state as { from?: string } | null)?.from;

  const onSubmit = handleSubmit(async ({ email, password }) => {
    setError(null);
    try {
      const user = await login(email, password);
      await navigate(from ?? (user.role === 'user' ? '/' : '/admin'), { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 429
          ? 'Too many attempts. Wait a minute and try again.'
          : err instanceof ApiError && err.status === 503
            ? 'Sign-in is not available on this deployment (no database configured).'
            : err instanceof Error
              ? err.message
              : 'Sign-in failed.',
      );
    }
  });

  return (
    <div className="mx-auto flex max-w-md flex-col gap-4 p-4 pt-12">
      <Card>
        <CardHeader>
          <h1 className="text-xl font-semibold">Sign in</h1>
          <CardDescription>
            Reviewers and administrators sign in to use the dashboard.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={(e) => void onSubmit(e)} noValidate>
            {error ? (
              <Alert tone="danger" title="Could not sign in" testId="login-error">
                {error}
              </Alert>
            ) : null}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email">E-mail</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                data-testid="login-email"
                aria-invalid={errors.email ? true : undefined}
                aria-describedby={errors.email ? 'email-error' : undefined}
                {...register('email')}
              />
              <FieldError id="email-error" message={errors.email?.message} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                data-testid="login-password"
                aria-invalid={errors.password ? true : undefined}
                aria-describedby={errors.password ? 'password-error' : undefined}
                {...register('password')}
              />
              <FieldError id="password-error" message={errors.password?.message} />
            </div>
            <Button type="submit" disabled={isSubmitting} data-testid="login-submit">
              {isSubmitting ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
