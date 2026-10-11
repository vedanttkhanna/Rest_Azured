import { lazy, Suspense, Component, type ReactNode } from "react";
import { Navigate, Route, Routes, Link, useLocation } from "react-router-dom";
import { useAuth } from "./auth/Auth";
import { Layout } from "./components/Layout";
import { Loading, ErrorPanel } from "./components/ui";
import Overview from "./pages/Overview";
const NewAssessment = lazy(() => import("./pages/NewAssessment"));
const ReportPage = lazy(() => import("./pages/Report"));
const SampleReport = lazy(() =>
  import("./pages/Report").then((module) => ({ default: module.SampleReport })),
);
const History = lazy(() => import("./pages/History"));
const Installer = lazy(() => import("./pages/Installer"));
const Login = lazy(() => import("./pages/Login"));
const About = lazy(() => import("./pages/About"));

function Protected({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const location = useLocation();
  if (auth.loading) return <Loading />;
  if (!auth.signedIn)
    return (
      <Navigate
        to="/login"
        state={{ from: location.pathname + location.search }}
        replace
      />
    );
  return children;
}
class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: boolean }
> {
  state = { error: false };
  static getDerivedStateFromError() {
    return { error: true };
  }
  render() {
    return this.state.error ? (
      <div className="app-crash">
        <ErrorPanel error="The workspace couldn’t render. Reload the page to try again." />
        <button className="button" onClick={() => window.location.reload()}>
          Reload workspace
        </button>
      </div>
    ) : (
      this.props.children
    );
  }
}
export default function App() {
  return (
    <ErrorBoundary>
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Overview />} />
            <Route path="about" element={<About />} />
            <Route path="login" element={<Login />} />
            <Route path="sample" element={<SampleReport />} />
            <Route
              path="assess"
              element={
                <Protected>
                  <NewAssessment />
                </Protected>
              }
            />
            <Route
              path="jobs/:id"
              element={
                <Protected>
                  <ReportPage />
                </Protected>
              }
            />
            <Route
              path="history"
              element={
                <Protected>
                  <History />
                </Protected>
              }
            />
            <Route
              path="installer"
              element={
                <Protected>
                  <Installer />
                </Protected>
              }
            />
            <Route
              path="*"
              element={
                <div className="empty-state">
                  <h1>This page took a wrong turn.</h1>
                  <Link className="button" to="/">
                    Back to the sunshine
                  </Link>
                </div>
              }
            />
          </Route>
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
