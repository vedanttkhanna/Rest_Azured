import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./auth/Auth";
import App from "./App";
import { config } from "./config";
import "@aws-amplify/ui-react/styles.css";
import "maplibre-gl/dist/maplibre-gl.css";
import "@fontsource-variable/dm-sans/wght.css";
import "@fontsource-variable/manrope/wght.css";
import "./styles.css";

async function start() {
  if (config.useMocks) {
    const { worker } = await import("./mocks/browser");
    await worker.start({ onUnhandledFrame: "bypass" });
  }
  const queryClient = new QueryClient({
    defaultOptions: { queries: { staleTime: 15_000 } },
  });
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    </React.StrictMode>,
  );
}
void start().catch(() => {
  const root = document.getElementById("root")!;
  root.textContent =
    "Could not start the solar workspace. Reload the page, or check the MSW worker setup in web/README.md.";
});
