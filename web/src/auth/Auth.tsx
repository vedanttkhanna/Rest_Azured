import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { Amplify } from "aws-amplify";
import { fetchAuthSession, signOut } from "aws-amplify/auth";
import { Hub } from "aws-amplify/utils";
import { useQueryClient } from "@tanstack/react-query";
import { config, hasLiveConfig } from "../config";
import type { Role } from "../api/types";

const localWorkspace = config.useMocks || config.localApi;
const roleKey = config.localApi ? "solar-local-role" : "solar-demo-role";
if (!localWorkspace && hasLiveConfig)
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: config.userPoolId,
        userPoolClientId: config.userPoolClientId,
        loginWith: { email: true },
      },
    },
  });

interface Identity {
  signedIn: boolean;
  loading: boolean;
  email: string;
  role: Role;
  demo: boolean;
  local: boolean;
  logout: () => Promise<void>;
  setDemoRole: (role: Role) => void;
}
const AuthContext = createContext<Identity | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
  const [signedIn, setSignedIn] = useState(localWorkspace);
  const [loading, setLoading] = useState(!localWorkspace);
  const [email, setEmail] = useState("Solar explorer");
  const [role, setRole] = useState<Role>(
    (sessionStorage.getItem(roleKey) as Role) === "Installer"
      ? "Installer"
      : "Homeowner",
  );
  const queryClient = useQueryClient();
  useEffect(() => {
    if (localWorkspace || !hasLiveConfig) {
      setLoading(false);
      return;
    }
    let active = true;
    const refresh = async () => {
      try {
        const { tokens } = await fetchAuthSession();
        if (!active) return;
        setSignedIn(Boolean(tokens));
        const payload = tokens?.idToken?.payload;
        setEmail(
          typeof payload?.email === "string" ? payload.email : "Solar explorer",
        );
        setRole(
          Array.isArray(payload?.["cognito:groups"]) &&
            payload["cognito:groups"].includes("Installer")
            ? "Installer"
            : "Homeowner",
        );
      } catch {
        if (active) setSignedIn(false);
      } finally {
        if (active) setLoading(false);
      }
    };
    void refresh();
    const stop = Hub.listen("auth", ({ payload }) => {
      if (
        [
          "signedIn",
          "signedOut",
          "tokenRefresh",
          "tokenRefresh_failure",
        ].includes(payload.event)
      ) {
        queryClient.clear();
        void refresh();
      }
    });
    return () => {
      active = false;
      stop();
    };
  }, [queryClient]);
  const logout = async () => {
    if (!localWorkspace) await signOut();
    queryClient.clear();
    setSignedIn(localWorkspace);
  };
  const setDemoRole = (value: Role) => {
    if (localWorkspace) {
      sessionStorage.setItem(roleKey, value);
      setRole(value);
      queryClient.clear();
    }
  };
  return (
    <AuthContext.Provider
      value={{
        signedIn,
        loading,
        email,
        role,
        demo: config.useMocks,
        local: config.localApi,
        logout,
        setDemoRole,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider is missing.");
  return value;
}
