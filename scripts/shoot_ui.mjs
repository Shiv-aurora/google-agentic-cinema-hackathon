// Visual verification pass for the studio shell. Captures the real app served
// by Vite against the local API; nothing about the UI is stubbed.
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const out = 'output/redesign';
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', (error) => errors.push(String(error.message)));
page.on('console', (message) => {
  if (message.type() === 'error') errors.push(`console: ${message.text()}`);
});

await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' });
await page.waitForSelector('.transport', { timeout: 20000 });
await page.waitForTimeout(1200);

const shot = async (name) => {
  await page.screenshot({ path: `${out}/${name}.png` });
  console.log(`saved ${out}/${name}.png`);
};

await shot('desktop-light');

await page.getByLabel('Switch to dark theme').click();
await page.waitForTimeout(400);
await shot('desktop-dark');
await page.getByLabel('Switch to light theme').click();
await page.waitForTimeout(400);

await page.getByRole('tab', { name: /Clappy/ }).click();
await page.waitForTimeout(400);
await shot('clappy-panel');
await page.getByRole('tab', { name: /Screenplay/ }).click();

await page.locator('.status-pill').click();
await page.waitForTimeout(300);
await shot('status-menu');
await page.keyboard.press('Escape');

await page.getByRole('button', { name: /Takes & edits/ }).click();
await page.waitForTimeout(600);
await shot('review-empty');
await page.getByRole('button', { name: 'On set' }).click();
await page.waitForTimeout(400);

for (const [name, width, height] of [['tablet', 900, 800], ['mobile', 390, 844]]) {
  await page.setViewportSize({ width, height });
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: true });
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  console.log(`saved ${out}/${name}.png  scrollWidth=${scrollWidth} (viewport ${width})`);
}

console.log(errors.length ? `ERRORS:\n${errors.join('\n')}` : 'no console/page errors');
await browser.close();
