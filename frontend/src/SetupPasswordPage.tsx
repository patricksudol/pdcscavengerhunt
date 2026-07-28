import { FormEvent, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";

import { api } from "./api";
import { Brand, Button, ErrorMessage, Field } from "./components";

export function SetupPasswordPage({ token }: { token: string }) {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const details = useQuery({
    queryKey: ["setup-password", token],
    queryFn: () =>
      api<{ email_address: string; full_name: string }>(
        `/api/v1/auth/password-setup/${encodeURIComponent(token)}`,
      ),
    retry: false,
  });
  const setup = useMutation({
    mutationFn: () =>
      api<{ password_set: boolean }>(
        `/api/v1/auth/password-setup/${encodeURIComponent(token)}`,
        { method: "POST", body: JSON.stringify({ password }) },
      ),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirmation) return;
    setup.mutate();
  }

  return (
    <main className="login-page login-page--center">
      <Brand />
      <section className="login-card setup-card">
        <div className="login-card__icon"><KeyRound /></div>
        {details.isLoading ? (
          <p>Checking your invitation…</p>
        ) : details.isError ? (
          <>
            <h1>Invitation unavailable</h1>
            <ErrorMessage error={details.error} />
          </>
        ) : setup.isSuccess ? (
          <>
            <h1>You’re ready</h1>
            <p>Your password is set. Sign in to see your games.</p>
            <a className="button button--primary button--wide" href="/">Go to sign-in</a>
          </>
        ) : (
          <>
            <div className="eyebrow">Welcome, {details.data?.full_name}</div>
            <h1>Set your password</h1>
            <p>
              Your email address is <strong>{details.data?.email_address}</strong>. Choose a
              password with at least 12 characters.
            </p>
            <form onSubmit={submit}>
              <Field
                label="New password"
                name="password"
                type="password"
                minLength={12}
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
              <Field
                label="Confirm password"
                name="confirmation"
                type="password"
                minLength={12}
                autoComplete="new-password"
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                required
              />
              {confirmation && password !== confirmation && (
                <div className="form-error">Passwords do not match.</div>
              )}
              <ErrorMessage error={setup.error} />
              <Button
                className="button--wide"
                busy={setup.isPending}
                disabled={password !== confirmation}
                type="submit"
              >
                Set password
              </Button>
            </form>
          </>
        )}
      </section>
    </main>
  );
}
