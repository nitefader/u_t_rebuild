import { expect, test } from "@playwright/test";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:5173";

test("ChartLab renders a real preview chart with volume and reset controls", async ({ page }) => {
  await page.goto(`${BASE_URL}/chart-lab`);

  await page.getByRole("button", { name: /Load Data/i }).click();

  const chart = page.getByTestId("strategy-preview-chart-real");
  await expect(chart).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("chart-lab-volume-pane")).toBeVisible();
  await expect(page.getByRole("button", { name: /Reset Zoom/i })).toBeVisible();

  const totalBarsText = await page
    .getByTestId("chart-lab-context-strip")
    .textContent({ timeout: 30_000 });
  const totalBars = Number(totalBarsText?.match(/Total bars\s*([0-9,]+)/i)?.[1].replace(/,/g, ""));
  expect(totalBars).toBeGreaterThan(0);

  const canvasCount = await chart.locator("canvas").count();
  expect(canvasCount).toBeGreaterThan(0);

  const nonEmptyCanvas = await chart.locator("canvas").first().evaluate((canvas) => {
    const element = canvas as HTMLCanvasElement;
    const ctx = element.getContext("2d");
    if (!ctx || element.width === 0 || element.height === 0) return false;
    const pixels = ctx.getImageData(0, 0, element.width, element.height).data;
    for (let index = 3; index < pixels.length; index += 4) {
      if (pixels[index] !== 0) return true;
    }
    return false;
  });
  expect(nonEmptyCanvas).toBe(true);

  const warmupLabel = page.getByText("Warm-up", { exact: true });
  if ((await warmupLabel.count()) > 0) {
    await expect(warmupLabel.first()).toBeVisible();
  }

  await expect(page.getByText(/Entry markers:/i)).toBeVisible();
  await expect(page.getByText(/Exit markers:/i)).toBeVisible();

  const firstTimelineTime = page.locator("table.ut-table tbody tr td:nth-child(2)").first();
  await expect(firstTimelineTime).toContainText(/20\d{2}|AM|PM|:/);
});
