import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api, AUTH_EXPIRED_EVENT, ApiError } from "@/lib/api";
import type {
  MeOut,
  RegisterPayload,
  SessionOut,
  SwitchTarget,
} from "@/lib/types";

interface AuthState {
  status: "loading" | "authenticated" | "anonymous";
  me: MeOut | null;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => Promise<void>;
  switchContext: (target: SwitchTarget) => Promise<void>;
  reload: () => Promise<void>;
  acceptInvitation: (token: string) => Promise<void>;
  hasPermission: (permission: string) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const [me, setMe] = useState<MeOut | null>(null);
  const bootstrapped = useRef(false);

  const loadMe = useCallback(async () => {
    const profile = await api.get<MeOut>("/auth/me");
    setMe(profile);
    setStatus("authenticated");
  }, []);

  useEffect(() => {
    const onExpired = () => {
      setMe(null);
      setStatus("anonymous");
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, []);

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;

    (async () => {
      const session = await api.refreshSession();
      if (!session) {
        setStatus("anonymous");
        return;
      }
      try {
        await loadMe();
      } catch {
        api.setToken(null);
        setStatus("anonymous");
      }
    })();
  }, [loadMe]);

  const adoptSession = useCallback(async (session: SessionOut) => {
    api.setToken(session.access_token);
    await loadMe();
  }, [loadMe]);

  const login = useCallback(
    async (email: string, password: string) => {
      const session = await api.post<SessionOut>(
        "/auth/login",
        { email, password },
        { skipRefresh: true },
      );
      await adoptSession(session);
    },
    [adoptSession],
  );

  const register = useCallback(
    async (payload: RegisterPayload) => {
      const session = await api.post<SessionOut>("/auth/register", payload, {
        skipRefresh: true,
      });
      await adoptSession(session);
    },
    [adoptSession],
  );

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout", undefined, { skipRefresh: true });
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
    } finally {
      api.setToken(null);
      setMe(null);
      setStatus("anonymous");
    }
  }, []);

  const switchContext = useCallback(async (target: SwitchTarget) => {
    const session = await api.post<SessionOut>("/auth/switch-context", target);
    api.setToken(session.access_token);
    setMe((current) =>
      current
        ? {
            ...current,
            context: session.context,
            available_contexts: session.available_contexts,
          }
        : current,
    );
  }, []);

  const reload = useCallback(async () => {
    await loadMe();
  }, [loadMe]);

  const acceptInvitation = useCallback(
    async (token: string) => {
      await api.post("/staff/invitations/accept", { token });
      await loadMe();
    },
    [loadMe],
  );

  const hasPermission = useCallback(
    (permission: string) => me?.context.permissions.includes(permission) ?? false,
    [me],
  );

  const value = useMemo<AuthState>(
    () => ({
      status,
      me,
      login,
      register,
      logout,
      switchContext,
      reload,
      acceptInvitation,
      hasPermission,
    }),
    [
      status,
      me,
      login,
      register,
      logout,
      switchContext,
      reload,
      acceptInvitation,
      hasPermission,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
