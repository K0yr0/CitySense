"use client";

import { useEffect, type ReactNode } from "react";
import { checkSession } from "@/lib/api";
import { useSession } from "@/lib/auth";
import LoginView from "./LoginView";

/** Every page of the web admin needs a signed-in admin; otherwise the sign-in screen is shown in its place. */
export default function AuthGate({ children }: { children: ReactNode }) {
  const session = useSession();
  const token = session?.token;

  // A stored token may have expired or lost admin rights since the last visit.
  useEffect(() => {
    if (token) checkSession();
  }, [token]);

  if (session === undefined) return <main className="flex-1" aria-busy="true" />;
  if (!session) return <LoginView />;
  return <>{children}</>;
}
