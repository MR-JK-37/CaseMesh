import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/**
 * Phase 0 gate (Section 9.11 point 3): sign-in + gallery, light + dark,
 * zero serious/critical axe violations. Not yet backend-wired (Phase 1
 * builds real auth) — this only covers the styled shell.
 */
for (const path of ["/", "/dev/gallery"]) {
  for (const theme of ["light", "dark"] as const) {
    test(`${path} has no serious/critical axe violations (${theme})`, async ({ page }) => {
      await page.goto(path);
      await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
      const results = await new AxeBuilder({ page }).analyze();
      const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
      expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);
    });
  }
}

test("sign-in has no horizontal overflow at 390px", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dev/gallery");
  const [scrollWidth, clientWidth] = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    document.documentElement.clientWidth,
  ]);
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
});
