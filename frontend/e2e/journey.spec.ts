import { expect, test, type Page } from "@playwright/test";

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

test("landing page leads into the guided experience, which replays the recording", async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Evidence for every risk in your diff." })).toBeVisible();
  await page.getByRole("link", { name: /Take the guided experience/ }).click();
  await expect(page).toHaveURL(/\/experience$/);
  await expect(page.getByRole("heading", { level: 1, name: "Follow one change through the engine." })).toBeVisible();
  await page.getByRole("button", { name: "Replay the recording" }).scrollIntoViewIfNeeded();
  await expect(page.getByRole("link", { name: /Open the recorded report/ })).toBeVisible();
  expect(errors).toEqual([]);
});

test("a live run on the engine reproduces the recorded finding IDs", async ({ page }) => {
  await page.goto("/experience");
  await page.getByRole("button", { name: "Run it on your engine" }).click();
  await expect(page.getByText(/All \d+ finding IDs match the recording/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("log", { name: "Run events" })).toContainText("done");
});

test("analyse the sample, inspect a finding and its evidence, then find it in Reports", async ({ page }) => {
  await page.goto("/analyze");
  await page.getByRole("button", { name: "Analyse sample" }).first().click();
  await page.waitForURL(/\/reports\/an_[0-9a-f]{20}/, { timeout: 30_000 });

  await expect(page.getByText("Synthetic sample data")).toBeVisible();
  await page.getByRole("button", { name: /call site\(s\) incompatible with new signature/ }).first().click();
  await expect(page.getByRole("heading", { level: 2, name: /call site\(s\) incompatible with new signature/ }).first()).toBeVisible();
  await expect(page.getByText(/^Evidence \(\d+\)$/).first()).toBeVisible();

  await page.getByRole("button", { name: "Export" }).click();
  await expect(page.getByRole("menuitem", { name: /Markdown/ })).toHaveAttribute("href", /\/export\?format=markdown$/);
  await page.keyboard.press("Escape");

  const reportUrl = page.url();
  await page.goto("/history");
  const id = reportUrl.split("/reports/")[1].split("#")[0];
  await expect(page.locator(`a[href="/reports/${id}"]`).first()).toBeVisible();
});

test("reports are private to the browser that created them", async ({ browser }) => {
  const owner = await browser.newContext();
  const ownerPage = await owner.newPage();
  await ownerPage.goto("/analyze");
  await ownerPage.getByRole("button", { name: "Analyse sample" }).first().click();
  await ownerPage.waitForURL(/\/reports\/an_[0-9a-f]{20}/, { timeout: 30_000 });
  const reportPath = new URL(ownerPage.url()).pathname;

  const stranger = await browser.newContext();
  const strangerPage = await stranger.newPage();
  await strangerPage.goto(reportPath);
  await expect(strangerPage.getByText("Report not found")).toBeVisible();
  await strangerPage.goto("/history");
  await expect(strangerPage.locator(`a[href="${reportPath}"]`)).toHaveCount(0);

  await owner.close();
  await stranger.close();
});

test("the recorded sample report opens without running anything", async ({ page }) => {
  await page.goto("/reports/sample");
  await expect(page.getByText("Recorded run.")).toBeVisible();
  await expect(page.getByRole("tab", { name: /Findings/ })).toBeVisible();
});

test("method anchors resolve and the evaluation renders its tables", async ({ page }) => {
  await page.goto("/method#rule-CG-API-001");
  await expect(page.locator("#rule-CG-API-001")).toBeInViewport();
  await page.goto("/evaluation");
  await expect(page.getByRole("heading", { level: 1, name: "What the evaluation shows, and what it cannot." })).toBeVisible();
  await expect(page.locator("#all-cases table tbody tr")).not.toHaveCount(0);
});

test("unknown pages get a real 404", async ({ page }) => {
  const response = await page.goto("/no-such-page");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "Nothing here to analyse." })).toBeVisible();
});
