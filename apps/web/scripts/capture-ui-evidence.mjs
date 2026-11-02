import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const outDir = process.argv[2] ?? new URL('../../../docs/ui-evidence/phase-0', import.meta.url).pathname;
mkdirSync(outDir, { recursive: true });

const viewports = [
  { name: "1440x900", width: 1440, height: 900 },
  { name: "1024x768", width: 1024, height: 768 },
  { name: "390x844", width: 390, height: 844 },
];
const pages = [
  { name: "signin", path: "/" },
  { name: "gallery", path: "/dev/gallery" },
];
const themes = ["light", "dark"];

const browser = await chromium.launch();
for (const theme of themes) {
  for (const vp of viewports) {
    const page = await browser.newPage({
      viewport: { width: vp.width, height: vp.height },
      colorScheme: theme,
    });
    for (const p of pages) {
      await page.goto(`http://localhost:3001${p.path}`, { waitUntil: "networkidle" });
      await page.evaluate((t) => {
        document.documentElement.setAttribute("data-theme", t);
        try { localStorage.setItem("icm-theme", t); } catch {}
      }, theme);
      await page.waitForTimeout(200);
      const file = `${outDir}/${p.name}-${theme}-${vp.name}.png`;
      await page.screenshot({ path: file, fullPage: true });
      console.log("wrote", file);
    }
    await page.close();
  }
}
await browser.close();
