import { FormEvent, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { LogIn, MapPinned } from "lucide-react";

import { api, Me, setCsrfToken } from "./api";
import { Brand, Button, ErrorMessage, Field } from "./components";

export function LoginPage({ onSignedIn }: { onSignedIn: () => void }) {
  const [emailAddress, setEmailAddress] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () =>
      api<{ signed_in: boolean; user: Me; csrf_token: string }>(
        "/api/v1/auth/login",
        {
          method: "POST",
          body: JSON.stringify({ email_address: emailAddress, password }),
        },
      ),
    onSuccess: (result) => {
      setCsrfToken(result.csrf_token);
      onSignedIn();
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    login.mutate();
  }

  return (
    <main className="login-page">
      <Brand />
      <div className="login-layout">
        <section className="login-intro">
          <div className="eyebrow">Your next clue is waiting</div>
          <h1>Explore. Discover. Unlock.</h1>
          <p>
            Sign in with the email address from your invitation and follow the trail,
            one clue at a time.
          </p>
          <div className="login-intro__icon" aria-hidden="true">
            <MapPinned />
          </div>
        </section>
        <section className="login-card">
          <div className="login-card__icon"><LogIn /></div>
          <h2>Player sign-in</h2>
          <p>Enter the credentials you set from your invitation link.</p>
          <form onSubmit={submit}>
            <Field
              label="Email address"
              name="email-address"
              type="email"
              autoComplete="email"
              value={emailAddress}
              onChange={(event) => setEmailAddress(event.target.value)}
              required
            />
            <Field
              label="Password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            <ErrorMessage error={login.error} />
            <Button className="button--wide" busy={login.isPending} type="submit">
              Sign in
            </Button>
          </form>
        </section>
      </div>
    </main>
  );
}
