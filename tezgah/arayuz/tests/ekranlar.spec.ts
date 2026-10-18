// A3 K10 — ekran kabuğu uçtan uca (Playwright). Yalnızca yerelde çalışır (bkz. e2e.spec.ts, playwright.config.ts).
//
// Testin dayandığı DOM işaretleri (kabuk, src/main.ts):
//   ekran-sekmesi   üst sekmelerdeki her ekran; `data-ekran` = Ekran.ad, `aria-selected` = etkin mi,
//                   kapalı sekme `aria-disabled="true"`
// Sahne katmanları `window.__tezgah.katmanlar()` ile okunur (src/kanca.ts).

import { expect, test, type Page } from "@playwright/test";
import type { SunucuEkrani } from "../src/ekranlar/tip";
import "../src/kanca";

const SEKME = '[data-testid="ekran-sekmesi"]';

async function hazir(page: Page): Promise<void> {
  await page.waitForFunction(() => window.__tezgah?.hazir === true, null, { timeout: 30_000 });
}

async function sekmeAdlari(page: Page): Promise<string[]> {
  return page.locator(SEKME).evaluateAll((el) => el.map((e) => (e as HTMLElement).dataset.ekran ?? ""));
}

async function etkin(page: Page): Promise<string | null> {
  return page
    .locator(`${SEKME}[aria-selected="true"]`)
    .evaluateAll((el) => (el.length === 1 ? ((el[0] as HTMLElement).dataset.ekran ?? null) : null));
}

async function katmanlar(page: Page): Promise<string[]> {
  return page.evaluate(() => window.__tezgah!.katmanlar());
}

test.describe("Tezgah ekran kabuğu @slow", () => {
  let hatalar: string[];
  let liste: SunucuEkrani[];

  test.beforeEach(async ({ page, request }) => {
    hatalar = [];
    page.on("console", (m) => {
      if (m.type() === "error") hatalar.push(m.text());
    });
    page.on("pageerror", (e) => hatalar.push(String(e)));
    liste = (await (await request.get("/api/ekranlar")).json()).ekranlar;
  });

  test.afterEach(() => {
    expect(hatalar, "konsolda hata olmamalı").toEqual([]);
  });

  test("sekmeler /api/ekranlar sırasıyla çizilir; hazır olmayan kapalı", async ({ page }) => {
    await page.goto("/#/freze");
    await hazir(page);
    const adlar = await sekmeAdlari(page);
    const sunucuSirasi = liste.map((e) => e.ad);
    // Sunucuda olup ön yüzü olmayan da (kapalı) çizilir: sekmeler sunucu sırasının kendisidir.
    expect(adlar).toEqual(sunucuSirasi.filter((ad) => adlar.includes(ad)));
    expect(adlar).toContain("freze");
    for (const e of liste.filter((x) => !x.hazir && adlar.includes(x.ad))) {
      await expect(page.locator(`${SEKME}[data-ekran="${e.ad}"]`)).toHaveAttribute("aria-disabled", "true");
    }
  });

  test("#/freze freze'yi açar; yenileyince aynı ekran", async ({ page }) => {
    await page.goto("/#/freze");
    await hazir(page);
    expect(await etkin(page)).toBe("freze");
    await page.reload();
    await hazir(page);
    expect(await etkin(page)).toBe("freze");
    expect(page.url()).toContain("#/freze");
  });

  test("1 tuşu freze'yi açar", async ({ page }) => {
    const ikinci = liste.find((e) => e.hazir && e.ad !== "freze" && e.tus !== null);
    await page.goto(ikinci ? `/#/${ikinci.ad}` : "/");
    await hazir(page);
    await page.locator("body").click({ position: { x: 1, y: 1 } });
    await page.keyboard.press("1");
    await expect.poll(() => etkin(page)).toBe("freze");
    await expect.poll(() => page.url()).toContain("#/freze");
  });

  test("sekme değişince önceki ekranın sahne katmanı kalkar", async ({ page }) => {
    const ikinci = liste.find((e) => e.hazir && e.ad !== "freze");
    test.skip(!ikinci, "ikinci kullanılabilir ekran yok (ekranlar taşındıkça çalışır)");
    await page.goto("/#/freze");
    await hazir(page);
    await expect.poll(() => katmanlar(page)).toContain("freze");

    await page.locator(`${SEKME}[data-ekran="${ikinci!.ad}"]`).click();
    await expect.poll(() => etkin(page)).toBe(ikinci!.ad);
    await expect.poll(() => katmanlar(page)).not.toContain("freze");
    expect(page.url()).toContain(`#/${ikinci!.ad}`);

    await page.locator(`${SEKME}[data-ekran="freze"]`).click();
    await expect.poll(() => etkin(page)).toBe("freze");
    await expect.poll(() => katmanlar(page)).not.toContain(ikinci!.ad);
  });
});
