"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, AuthUser, getToken, setToken } from "./api";

type AuthState = {
  user: AuthUser | null;
  loading: boolean;
  signup: (email: string, password: string, name?: string) => Promise<void>;
  signin: (email: string, password: string) => Promise<void>;
  signout: () => void;
  refresh: () => Promise<void>;
};

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api<AuthUser>("/api/auth/me");
      setUser(me);
    } catch {
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const signup = useCallback(async (email: string, password: string, name?: string) => {
    const res = await api<{ access_token: string; user: AuthUser }>("/api/auth/signup", {
      method: "POST",
      auth: false,
      body: JSON.stringify({ email, password, name }),
    });
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const signin = useCallback(async (email: string, password: string) => {
    const res = await api<{ access_token: string; user: AuthUser }>("/api/auth/signin", {
      method: "POST",
      auth: false,
      body: JSON.stringify({ email, password }),
    });
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const signout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthCtx.Provider value={{ user, loading, signup, signin, signout, refresh }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
