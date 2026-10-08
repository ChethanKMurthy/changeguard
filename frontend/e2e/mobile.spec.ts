import { expect, test } from "@playwright/test";

test("navigation works from the mobile menu", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Open menu" }).click();
  await page.getByRole("navigation", { name: "Mobile" }).getByRole("link", { name: "Experience" }).click();
  await expect(page).toHaveURL(/\/experience$/);
  await expect(page.getByRole("button", { name: "Open menu" })).toBeVisible();
});

test("pages do not scroll horizontally on a phone", async ({ page }) => {
  for (const path of ["/", "/experience", "/evaluation", "/method", "/analyze", "/reports/sample"]) {
    await page.goto(path);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `${path} overflows by ${overflow}px`).toBeLessThanOrEqual(0);
  }
});
