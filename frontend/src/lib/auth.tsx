import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import * as api from "./api";
import type { User } from "./types";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  // Reviewers and Admins can use normal app functionality (upload, process,
  // review, export). Guests (no user) can only view.
  canEdit: boolean;
  isAdmin: boolean;
  login: (name: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadUser = useCallback(async () => {
    // No getToken() short-circuit here on purpose: a returning visitor
    // may have no (or an expired) access token in localStorage but still
    // have a valid httpOnly refresh cookie. getMe() will 401 in that
    // case, and the response interceptor in lib/api.ts transparently
    // exchanges the cookie for a fresh access token and retries -- so
    // this silently restores the session instead of showing Guest state
    // for a person who's actually still signed in.
    try {
      const me = await api.getMe();
      setUser(me);
    } catch {
      api.setToken(null);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  // Wire forceLogoutRedirect (in api.ts) into React state: when the
  // interceptor detects a revoked session it calls this, setting user to
  // null before the /login redirect fires. That way canEdit/isAdmin
  // immediately become false and all editor controls disappear instead
  // of staying visible during the brief redirect window.
  useEffect(() => {
    api.setSessionRevokedHandler(() => setUser(null));
  }, []);

  // Poll /auth/me while authenticated so a server-side session revocation
  // (e.g. Admin deletes this account) is caught promptly. On a revoked
  // access token the backend returns 401; the response interceptor in
  // api.ts then attempts a token refresh, which also fails because
  // revoke_user_sessions() cleared the refresh-token family in Redis.
  // That second 401 triggers forceLogoutRedirect() -- no extra logic
  // needed here, the catch below is intentionally empty.
  useEffect(() => {
    if (!user) return;
    const id = setInterval(() => {
      api.getMe().catch(() => {
        // The api.ts interceptor owns forced-logout on 401.
        // Any other error (network blip, etc.) is silently ignored;
        // the next tick will retry.
      });
    }, 15_000);
    return () => clearInterval(id);
  }, [user]);

  const login = useCallback(async (name: string, password: string) => {
    const { access_token } = await api.login(name, password);
    api.setToken(access_token);
    const me = await api.getMe();
    setUser(me);
  }, []);

  const logout = useCallback(async () => {
    // Revokes this session's refresh token server-side (so the cookie
    // can't be used to mint another access token) in addition to
    // clearing local state -- api.logout() never throws, so this is
    // safe to fire from a plain onClick.
    await api.logout();
    setUser(null);
  }, []);

  const isAdmin = user?.role === "admin";
  const canEdit = user?.role === "admin" || user?.role === "reviewer";

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        canEdit,
        isAdmin,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
