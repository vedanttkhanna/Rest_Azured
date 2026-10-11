import { test, expect } from "@playwright/test";

test("a new local scan submits the chosen roof and renders its real report", async ({ page, request, isMobile }, testInfo) => {
  test.setTimeout(180_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.emulateMedia({ reducedMotion: "reduce" });
  const location = isMobile
    ? { lat: 28.724751299709503, lng: 77.13259006975463, label: "Rohini browser check" }
    : { lat: 28.58111902454872, lng: 77.05083905954604, label: "Dwarka browser check" };
  await page.goto("/assess");
  await expect(page.getByText("Your trained model is connected.", { exact: false })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Which rooftop is yours?" })).toBeVisible();
  await page.getByLabel("Latitude", { exact: true }).fill(String(location.lat));
  await page.getByLabel("Longitude", { exact: true }).fill(String(location.lng));
  await page.getByLabel("Rooftop name or address (optional)").fill(location.label);
  await page.getByLabel("I’ve checked the pin is on the correct rooftop.").check();
  const creation = page.waitForRequest((req) => req.url().endsWith("/api/jobs") && req.method() === "POST");
  await page.getByRole("button", { name: "Find my solar potential" }).click();
  expect((await creation).postDataJSON()).toEqual({ lat: location.lat, lng: location.lng, address: location.label });
  await expect(page).toHaveURL(/\/jobs\//);
  await expect(page.getByRole("heading", { name: "A brighter outlook for your roof." })).toBeVisible({ timeout: 150_000 });
  const jid = new URL(page.url()).pathname.split("/").pop();
  const response = await request.get(`/api/jobs/${jid}`);
  expect(response.ok()).toBe(true);
  const job = await response.json();
  expect(job.status).toBe("done");
  expect(job.lat).toBe(location.lat);
  expect(job.lng).toBe(location.lng);
  expect(job.report.job_id).toBe(jid);
  expect(job.report.system.panel_count).toBeGreaterThan(0);
  expect(job.image_png_url).toBe(`/api/assets/${jid}/rgb.png`);
  expect(job.heatmap_png_url).toBe(`/api/assets/${jid}/shade.png`);
  await expect(page.getByLabel("Roof & obstacles")).toBeChecked();
  await expect(page.getByRole("region", { name: "Satellite map with solar panel layout and shading" })).toHaveAttribute("aria-busy", "false", { timeout: 15_000 });
  await page.getByLabel("Roof & obstacles").uncheck();
  await page.getByLabel("Roof & obstacles").check();
  await page.getByLabel("Shade", { exact: true }).uncheck();
  await page.getByLabel("Shade", { exact: true }).check();
  await page.evaluate(() => { (document.activeElement as HTMLElement)?.blur(); window.scrollTo(0, 0); });
  await page.screenshot({ path: `docs/screenshots/local-report-${testInfo.project.name}.png`, fullPage: true, animations: "disabled" });
  expect(errors).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.goto("/history");
  await expect(page.locator(`a.job-title[href="/jobs/${jid}"]`)).toBeVisible();
});

test("local installer batches and invalid inputs retain their own coordinates", async ({ page, request }) => {
  test.setTimeout(180_000);
  await page.goto("/");
  await page.getByLabel("Local workspace role").selectOption("Installer");
  await page.goto("/installer");
  await page.getByLabel("CSV addresses or coordinates").fill("address,lat,lng\nBatch Mayur Vihar,28.6039825,77.2935395\nBatch Dwarka,28.5918607,77.0452540");
  const creation = page.waitForRequest((req) => req.url().endsWith("/api/jobs/batch") && req.method() === "POST");
  await page.getByRole("button", { name: "Assess these rooftops" }).click();
  const submitted = await creation;
  expect(submitted.postDataJSON()).toEqual({ addresses: [{ address: "Batch Mayur Vihar", lat: 28.6039825, lng: 77.2935395 }, { address: "Batch Dwarka", lat: 28.5918607, lng: 77.0452540 }] });
  await expect(page.getByRole("status")).toContainText("2 rooftop assessments started");
  const { job_ids } = await (await submitted.response())!.json();
  for (const jid of job_ids)
    await expect(page.getByRole("row").filter({ has: page.locator(`a.job-title[href="/jobs/${jid}"]`) })).toContainText("Ready", { timeout: 150_000 });
  const invalid = await request.post("/api/jobs", { data: { lat: 19.1, lng: 72.8 } });
  expect(invalid.status()).toBe(400);
  const address = await request.post("/api/jobs", { data: { address: "Dwarka, Delhi" } });
  const health = await (await request.get("/api/health")).json();
  if (!health.geocoding) {
    expect(address.status()).toBe(400);
    expect((await address.json()).error).toContain("AWS credentials");
  }
});
