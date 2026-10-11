import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
vi.mock("aws-amplify/auth", () => ({ fetchAuthSession: vi.fn() }));
vi.mock("../config", () => ({
  config: { useMocks: false, localApi: false, apiUrl: "https://solar.test" },
}));
import { fetchAuthSession } from "aws-amplify/auth";
import { api, ApiError } from "./client";
import { config } from "../config";

beforeEach(() => {
  config.useMocks = false;
  config.localApi = false;
  vi.mocked(fetchAuthSession).mockResolvedValue({
    tokens: { idToken: { toString: () => "id-token" } },
  } as Awaited<ReturnType<typeof fetchAuthSession>>);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});
describe("Cognito API transport", () => {
  it("attaches the ID token and respects abort signals", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ job_id: "roof" }), { status: 201 }),
      );
    vi.stubGlobal("fetch", fetch);
    const controller = new AbortController();
    expect(await api("/jobs", { signal: controller.signal })).toEqual({
      job_id: "roof",
    });
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("https://solar.test/jobs");
    expect(options.headers.get("Authorization")).toBe("Bearer id-token");
    expect(options.signal).toBe(controller.signal);
  });
  it("never sends an unauthenticated live request", async () => {
    vi.mocked(fetchAuthSession).mockResolvedValue({});
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    await expect(api("/jobs")).rejects.toMatchObject({ status: 401 });
    expect(fetch).not.toHaveBeenCalled();
  });
  it("preserves quota errors and batch row details", async () => {
    const body = {
      error: "Quota reached",
      invalid: [{ index: 0, input: "Roof", error: "outside Delhi" }],
    };
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(new Response(JSON.stringify(body), { status: 429 })),
    );
    try {
      await api("/jobs");
      expect.fail("should reject");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect(error).toMatchObject({ status: 429, body });
    }
  });
  it("keeps fixture demo requests separate from Cognito", async () => {
    config.useMocks = true;
    vi.stubGlobal("sessionStorage", { getItem: () => "Installer" });
    const fetch = vi.fn().mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", fetch);
    await api("/jobs");
    expect(fetch.mock.calls[0][1].headers.get("X-Demo-Role")).toBe("Installer");
    expect(fetch.mock.calls[0][1].headers.has("Authorization")).toBe(false);
    expect(fetchAuthSession).not.toHaveBeenCalled();
  });
  it("sends local coordinates without Cognito or a demo header", async () => {
    config.localApi = true;
    vi.stubGlobal("sessionStorage", { getItem: () => "Installer" });
    const fetch = vi.fn().mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", fetch);
    const body = JSON.stringify({ lat: 28.7, lng: 77.1 });
    await api("/jobs", { method: "POST", body });
    const options = fetch.mock.calls[0][1];
    expect(options.body).toBe(body);
    expect(options.headers.get("X-Local-Role")).toBe("Installer");
    expect(options.headers.has("X-Demo-Role")).toBe(false);
    expect(options.headers.has("Authorization")).toBe(false);
    expect(fetchAuthSession).not.toHaveBeenCalled();
  });
});
