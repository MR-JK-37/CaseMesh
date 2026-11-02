import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const outDir = process.argv[2];
const totpSecret = process.argv[3];
const password = process.argv[4];
mkdirSync(outDir, { recursive: true });

function b32decode(b32) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const c of b32.replace(/=+$/, "")) bits += alphabet.indexOf(c).toString(2).padStart(5, "0");
  const bytes = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  return Uint8Array.from(bytes);
}

async function totpNow(secret) {
  const crypto = await import("node:crypto");
  const key = b32decode(secret);
  const counter = Math.floor(Date.now() / 1000 / 30);
  const buf = Buffer.alloc(8);
  buf.writeBigUInt64BE(BigInt(counter));
  const hmac = crypto.createHmac("sha1", Buffer.from(key)).update(buf).digest();
  const offset = hmac[hmac.length - 1] & 0xf;
  const code = ((hmac[offset] & 0x7f) << 24) | (hmac[offset + 1] << 16) | (hmac[offset + 2] << 8) | hmac[offset + 3];
  return String(code % 1_000_000).padStart(6, "0");
}

const viewports = [
  { name: "1440x900", width: 1440, height: 900 },
  { name: "1024x768", width: 1024, height: 768 },
  { name: "390x844", width: 390, height: 844 },
];
const themes = process.argv[5] ? [process.argv[5]] : ["light", "dark"];

const browser = await chromium.launch();

for (const theme of themes) {
  for (const vp of viewports) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, colorScheme: theme });
    const page = await ctx.newPage();
    await page.goto("http://localhost:3001/");
    await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);

    await page.screenshot({ path: `${outDir}/signin-${theme}-${vp.name}.png`, fullPage: true });

    await page.getByLabel("Email").fill("admin@icm.local");
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForResponse((r) => r.url().includes("/auth/login"));
    await page.getByLabel("Authenticator code").fill(await totpNow(totpSecret));
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL("**/home");
    await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
    await page.waitForTimeout(200);
    await page.screenshot({ path: `${outDir}/home-${theme}-${vp.name}.png`, fullPage: true });

    await page.goto("http://localhost:3001/security");
    await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${outDir}/security-${theme}-${vp.name}.png`, fullPage: true });

    await page.goto("http://localhost:3001/admin/users");
    await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${outDir}/admin-users-${theme}-${vp.name}.png`, fullPage: true });

    await ctx.close();
  }
}

await browser.close();
console.log("done");
