"use client";
import { useEffect, useState } from "react";
import { getManager } from "@/lib/auth";

export default function Callback() {
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getManager()
      .signinRedirectCallback()
      .then(() => window.location.replace("/"))
      .catch((e) => setError(e instanceof Error ? e.message : "Sign-in failed"));
  }, []);
  return error ? <p role="alert" className="p-8 text-red-700">{error}</p> : <p role="status" className="p-8">Signing in…</p>;
}
