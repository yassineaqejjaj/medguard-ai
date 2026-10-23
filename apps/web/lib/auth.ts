"use client";
import { UserManager, WebStorageStateStore, type User } from "oidc-client-ts";

let manager: UserManager | null = null;

export function getManager(): UserManager {
  if (!manager) {
    manager = new UserManager({
      authority: process.env.NEXT_PUBLIC_OIDC_AUTHORITY ?? "http://localhost:8080/realms/medguard",
      client_id: process.env.NEXT_PUBLIC_OIDC_CLIENT_ID ?? "medguard-web",
      redirect_uri: `${window.location.origin}/auth/callback`,
      post_logout_redirect_uri: window.location.origin,
      response_type: "code", // authorization code + PKCE (S256)
      scope: "openid profile email",
      // Tokens live in sessionStorage: cleared when the tab closes.
      userStore: new WebStorageStateStore({ store: window.sessionStorage }),
      automaticSilentRenew: true,
    });
  }
  return manager;
}

export type { User };
