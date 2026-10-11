import { expect, test } from "@playwright/test";

test("solar overview and sample report show actual fixture values", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Make room for a brighter future/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("article").filter({ hasText: "Clean energy / year" }),
  ).toContainText("27,274");
  await expect(page.getByLabel("Demo role")).toHaveValue("Homeowner");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `docs/screenshots/overview-${testInfo.project.name}.png`,
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("link", { name: "View sample report" }).click();
  await expect(
    page.getByRole("heading", { name: "A brighter outlook for your roof." }),
  ).toBeVisible();
  await expect(
    page.getByRole("article").filter({ hasText: "System capacity" }),
  ).toContainText("16.2");
  await expect(page.getByLabel("Panels", { exact: true })).toBeChecked();
  await expect(
    page.getByRole("region", {
      name: "Satellite map with solar panel layout and shading",
    }),
  ).toHaveAttribute("aria-busy", "false", { timeout: 15_000 });
  await page.getByLabel("Panels", { exact: true }).uncheck();
  await expect(page.getByLabel("Panels", { exact: true })).not.toBeChecked();
  await page.getByText("Model assumptions", { exact: true }).click();
  await expect(page.getByText("Finance", { exact: true })).toBeVisible();
  await page.getByText("Model assumptions", { exact: true }).click();
  await page.getByLabel("Panels", { exact: true }).check();
  expect(errors).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.evaluate(() => {
    (document.activeElement as HTMLElement)?.blur();
    window.scrollTo(0, 0);
  });
  await page.screenshot({
    path: `docs/screenshots/report-${testInfo.project.name}.png`,
    fullPage: true,
    animations: "disabled",
  });
  await page.evaluate(() => window.dispatchEvent(new Event("beforeprint")));
  await expect(page.getByText("Model version", { exact: true })).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new Event("afterprint")));
});

test("homeowner pin assessment progresses to a saved report", async ({
  page,
}) => {
  await page.goto("/assess");
  await expect(
    page.getByRole("heading", { name: "Which rooftop is yours?" }),
  ).toBeVisible();
  await page.getByLabel("Latitude", { exact: true }).fill("19.1");
  await page.getByRole("button", { name: "Find my solar potential" }).click();
  await expect(page.getByRole("alert")).toContainText("inside Delhi/NCR");
  await page.getByLabel("Latitude", { exact: true }).fill("28.6039825");
  await page
    .getByLabel("Rooftop name or address (optional)")
    .fill("My test rooftop");
  await page
    .getByLabel("I’ve checked the pin is on the correct rooftop.")
    .check();
  await page.getByRole("button", { name: "Find my solar potential" }).click();
  await expect(page).toHaveURL(/\/jobs\//);
  await expect(
    page.getByRole("heading", { name: "Your roof meets a year of sunshine." }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "A brighter outlook for your roof." }),
  ).toBeVisible({ timeout: 25_000 });
  await page
    .getByRole("link", { name: "All assessments", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: /^My test rooftop/ }),
  ).toBeVisible();
});

test("installer starts a CSV batch, sees ready rows, and exports", async ({
  page,
  isMobile,
}) => {
  await page.goto("/");
  await page.getByLabel("Demo role").selectOption("Installer");
  await page.goto("/installer");
  await expect(
    page.getByRole("heading", { name: "Your installer workspace." }),
  ).toBeVisible();
  const csv =
    'address,lat,lng\nSample roof,28.6039825,77.2935395\n"Dwarka, Delhi",,';
  if (isMobile) {
    await page.getByLabel("Upload addresses CSV").setInputFiles({
      name: "rooftops.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(csv),
    });
  } else {
    await page.getByLabel("CSV addresses or coordinates").fill(csv);
  }
  const assessButton = page.getByRole("button", {
    name: "Assess these rooftops",
  });
  if (isMobile) await assessButton.tap();
  else await assessButton.click();
  await expect(page.getByRole("status")).toContainText(
    "2 rooftop assessments started",
  );
  await expect(
    page.getByRole("row").filter({ hasText: "Sample roof" }),
  ).toContainText("Ready", { timeout: 25_000 });
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV", exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("installer-rooftops.csv");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("unknown jobs and homeowner installer route show useful outcomes", async ({
  page,
}) => {
  await page.goto("/jobs/missing");
  await expect(page.getByRole("alert")).toContainText("Job not found");
  await page.goto("/installer");
  await expect(
    page.getByRole("heading", { name: "A workspace for installers." }),
  ).toBeVisible();
});
