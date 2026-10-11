const localApi = import.meta.env.DEV && import.meta.env.VITE_LOCAL_API === "true";
export const config = {
  localApi,
  useMocks: !localApi && import.meta.env.VITE_USE_MOCKS === "true",
  apiUrl: localApi ? "/api" : (import.meta.env.VITE_API_URL || "").replace(/\/$/, ""),
  userPoolId: import.meta.env.VITE_USER_POOL_ID || "",
  userPoolClientId: import.meta.env.VITE_USER_POOL_CLIENT_ID || "",
  region: import.meta.env.VITE_REGION || "ap-south-1",
  serviceArea: { minLat: 28.4, maxLat: 28.9, minLng: 76.8, maxLng: 77.4 },
  pollingMs: 3_000,
  heatmapRefreshMs: 12 * 60_000,
  maxBatch: 25,
};

export const hasLiveConfig = Boolean(
  config.apiUrl && config.userPoolId && config.userPoolClientId,
);
