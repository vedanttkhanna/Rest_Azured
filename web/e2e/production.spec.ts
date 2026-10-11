import { expect, test } from "@playwright/test";

test("production requires Cognito sign-in and renders the bundled sample", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/assess");
  await expect(page).toHaveURL(/\/login/);
  await expect(
    page.getByRole("heading", { name: "Welcome to your solar workspace." }),
  ).toBeVisible();
  await expect(
    page.getByRole("tab", { name: "Sign In", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("tab", { name: "Create Account", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Demo role")).toHaveCount(0);
  await page.goto("/sample");
  await expect(
    page.getByRole("heading", { name: "A brighter outlook for your roof." }),
  ).toBeVisible();
  await expect(page.getByLabel("Panels", { exact: true })).toBeChecked();
  expect(errors).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
