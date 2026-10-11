import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { setupServer } from "msw/node";
vi.mock("../config", async (importOriginal) => {
  const original = await importOriginal<typeof import("../config")>();
  return {
    ...original,
    config: { ...original.config, apiUrl: "https://fixture.test" },
  };
});
import { handlers } from "./handlers";
import { config } from "../config";
const server = setupServer(...handlers);
beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterAll(() => {
  server.close();
  vi.restoreAllMocks();
});
const request = (path: string, addresses: unknown, role = "Installer") =>
  fetch(`${config.apiUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Demo-Role": role },
    body: JSON.stringify(addresses),
  });
describe("fixture API behavior", () => {
  it("blocks homeowner batch and makes invalid batches atomic", async () => {
    expect(
      (await request("/jobs/batch", { addresses: ["Delhi"] }, "Homeowner"))
        .status,
    ).toBe(403);
    const response = await request("/jobs/batch", {
      addresses: [{ lat: 19, lng: 72 }, "Delhi"],
    });
    expect(response.status).toBe(400);
    expect(await response.json()).toMatchObject({ invalid: [{ index: 0 }] });
  });
  it("walks a created job to a done contract C report", async () => {
    const response = await request("/jobs", { lat: 28.6, lng: 77.2 });
    expect(response.status).toBe(201);
    const { job_id } = (await response.json()) as { job_id: string };
    const queued = await (
      await fetch(`${config.apiUrl}/jobs/${job_id}`)
    ).json();
    expect(queued.status).toBe("queued");
    const originalNow = Date.now();
    vi.spyOn(Date, "now").mockReturnValue(originalNow + 12_000);
    const done = await (await fetch(`${config.apiUrl}/jobs/${job_id}`)).json();
    expect(done.status).toBe("done");
    expect(done.report.energy.monthly_kwh).toHaveLength(12);
    expect(done.heatmap_png_url).toBe("/demo/shade.png");
    vi.restoreAllMocks();
  });
});
