import { Authenticator } from "@aws-amplify/ui-react";
import { Navigate, useLocation } from "react-router-dom";
import { Sun, ShieldCheck } from "lucide-react";
import { useAuth } from "../auth/Auth";
import { hasLiveConfig } from "../config";
import { ErrorPanel, Loading } from "../components/ui";

export default function Login() {
  const auth = useAuth();
  const location = useLocation();
  const destination =
    typeof location.state?.from === "string" &&
    location.state.from.startsWith("/") &&
    !location.state.from.startsWith("//")
      ? location.state.from
      : "/assess";
  if (auth.loading) return <Loading />;
  if (auth.signedIn) return <Navigate to={destination} replace />;
  if (!hasLiveConfig)
    return (
      <ErrorPanel error="Live sign-in is not configured. Follow web/README.md to set the Cognito and API environment variables." />
    );
  return (
    <div className="login-page">
      <div className="login-story">
        <Sun size={55} strokeWidth={1.3} />
        <div className="eyebrow">YOUR BRIGHTER FUTURE STARTS HERE</div>
        <h1>
          A roof.
          <br />A little sunshine.
          <br />A lot of potential.
        </h1>
        <p>
          Sign in to save your solar assessments, revisit reports, and explore
          what’s possible above your home.
        </p>
        <span>
          <ShieldCheck size={17} /> Secure sign-in with Amazon Cognito
        </span>
      </div>
      <div className="login-card">
        <h2>Welcome to your solar workspace.</h2>
        <p>Sign in or create a Homeowner account.</p>
        <Authenticator loginMechanisms={["email"]} signUpAttributes={["email"]}>
          <Loading text="Opening your workspace…" />
        </Authenticator>
        <p className="login-note">
          Installer access is enabled by the project administrator. New accounts
          start as Homeowners.
        </p>
      </div>
    </div>
  );
}
