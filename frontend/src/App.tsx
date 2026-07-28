import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import { AdminPage } from "./AdminPage";
import { api, Me, setCsrfToken } from "./api";
import { LoginPage } from "./LoginPage";
import { PlayerPage } from "./PlayerPage";
import { SetupPasswordPage } from "./SetupPasswordPage";

export default function App() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (path.startsWith("/setup-password/")) {
    return (
      <SetupPasswordPage
        token={decodeURIComponent(path.slice("/setup-password/".length))}
      />
    );
  }
  return <AuthenticatedApp adminRoute={path.startsWith("/admin")} />;
}

function AuthenticatedApp({ adminRoute }: { adminRoute: boolean }) {
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<Me>("/api/v1/auth/me"),
    retry: false,
  });

  useEffect(() => {
    setCsrfToken(me.data?.csrf_token ?? null);
  }, [me.data]);

  if (me.isLoading) return <div className="app-loading">Opening the hunt…</div>;
  if (me.isError || !me.data) {
    return <LoginPage onSignedIn={() => me.refetch()} />;
  }
  if (adminRoute && me.data.is_admin) return <AdminPage me={me.data} />;
  return <PlayerPage me={me.data} />;
}
