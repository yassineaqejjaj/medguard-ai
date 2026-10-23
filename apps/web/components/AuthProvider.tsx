"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type Me } from "@/lib/api";
import { getManager } from "@/lib/auth";

type State = { status: "loading" } | { status: "anonymous" } | { status: "error"; message: string } | { status: "ready"; me: Me };
const Ctx = createContext<State>({ status: "loading" });
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const user = await getManager().getUser();
        if (!user || user.expired) return !cancelled && setState({ status: "anonymous" });
        const me = await api<Me>("/me");
        if (!cancelled) setState({ status: "ready", me });
      } catch (e) {
        if (!cancelled) setState({ status: "error", message: e instanceof Error ? e.message : "Unexpected error" });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return <Ctx.Provider value={state}>{children}</Ctx.Provider>;
}
