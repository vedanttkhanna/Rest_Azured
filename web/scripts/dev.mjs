import { spawn } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { createConnection } from "node:net";

const root = fileURLToPath(new URL("../../", import.meta.url));
const settings = JSON.parse(readFileSync(new URL("../local/config.json", import.meta.url), "utf8"));
const appUrl = "http://localhost:5173";
const apiUrl = `http://127.0.0.1:${settings.port}`;
async function health(url) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(1000) });
    const value = await response.json();
    return response.ok && value.status === "ok" && value.mode === "local" &&
      value.model_version === settings.model_version;
  } catch { return false; }
}
function portInUse(port) {
  return new Promise((resolve) => {
    const socket = createConnection({ host: "127.0.0.1", port });
    let settled = false;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(result);
    };
    socket.once("connect", () => finish(true));
    socket.once("error", () => finish(false));
    socket.setTimeout(1000, () => finish(false));
  });
}

// Check existing services before starting another Python/model process.
const [appReady, apiReady] = await Promise.all([
  health("http://127.0.0.1:5173/api/health"), health(`${apiUrl}/health`),
]);
if (appReady) {
  console.log(`SolarRooftop AI is already running.\nOpen ${appUrl}/assess\nTo restart, press Ctrl+C in its original terminal, then run npm run dev.`);
  process.exit(0);
}
if (await portInUse(5173)) {
  console.error("Port 5173 is used by another server or a demo/live workspace. Stop it with Ctrl+C in its terminal, then run npm run dev again. No existing process was stopped.");
  process.exit(1);
}
if (!apiReady && await portInUse(settings.port)) {
  console.error(`Port ${settings.port} is already used by an unavailable or different API. Stop that server in its terminal before launching this workspace.`);
  process.exit(1);
}
const python = resolve(root, "ml/.venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
if (!apiReady && !existsSync(python)) {
  console.error("Set up the ML/solar environment first. See web/README.md.");
  process.exit(1);
}
let closing = false;
let vite;
const backend = apiReady ? undefined : spawn(python, ["-u", "web/local/server.py"], {
  cwd: root,
  stdio: "inherit",
  env: { ...process.env, HF_HUB_OFFLINE: "1", TRANSFORMERS_OFFLINE: "1" },
});
const stop = (code = 0) => {
  if (closing) return;
  closing = true;
  backend?.kill("SIGTERM");
  vite?.kill("SIGTERM");
  process.exitCode = code;
};
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => stop());
backend?.on("error", (error) => { console.error(error.message); stop(1); });
backend?.on("exit", (code) => { if (!closing) stop(code || 1); });
if (apiReady) console.log(`Using the existing local model API at ${apiUrl}.`);

// Start the GUI only after the actual model is ready. No demo fallback.
for (let attempt = 0; attempt < 120 && !closing; attempt++) {
  try {
    if (await health(`${apiUrl}/health`)) {
      vite = spawn(process.execPath, [resolve(root, "web/node_modules/vite/bin/vite.js"), "--mode", "workspace", "--host", "127.0.0.1", "--port", "5173", "--strictPort"], {
        cwd: resolve(root, "web"), stdio: "inherit",
        env: { ...process.env, VITE_USE_MOCKS: "false", VITE_LOCAL_API: "true", VITE_API_URL: "/api" },
      });
      vite.on("exit", (code) => { if (!closing) stop(code || 0); });
      vite.on("error", (error) => { console.error(error.message); stop(1); });
      break;
    }
  } catch { /* model is still loading */ }
  await new Promise((resolve) => setTimeout(resolve, 500));
}
if (!vite && !closing) { console.error("The local model API did not start. Check the model path and dependencies."); stop(1); }
