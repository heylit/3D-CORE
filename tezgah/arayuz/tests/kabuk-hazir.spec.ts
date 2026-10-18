// A3 — kabuğun `window.__tezgah.hazir` sinyali sekme değişiminde (Playwright, @slow). Yalnızca yerelde çalışır.
//
// Sözleşme (koordinatör kararı, "(b)" seçeneği): adres (#/<ad>) etkin ekrandan başka bir ekranı gösteriyorsa ya da
// etkin ekranın ac()'ı hâlâ sürüyorsa `hazir` false'tur; yeni ekran açılınca true'ya döner. Böylece sekme
// değiştiren bir test önceki ekranın "hazır" sinyalini yanlışlıkla yeni ekranınki sanamaz.
//
// DOM işareti: ekran-sekmesi (bkz. ekranlar.spec.ts). Model ekranının açılış isteği GET /api/ekran/model/
// (SPEC 26); bu istek bekletilerek ac()'ın sürdüğü an oluşturulur.

import { expect, test, type Page } from "@playwright/test";
import type { SunucuEkrani } from "../src/ekranlar/tip";
import "../src/kanca";

const SEKME = '[data-testid="ekran-sekmesi"]';

async function hazirBekle(page: Page): Promise<void> {
  await page.waitForFunction(() => window.__tezgah?.hazir === true, null, { timeout: 30_000 });
}

async function hazirOku(page: Page): Promise<boolean> {
  return page.evaluate(() => window.__tezgah!.hazir === true);
}

async function etkin(page: Page): Promise<string | null> {
  return page
    .locator(`${SEKME}[aria-selected="true"]`)
    .evaluateAll((el) => (el.length === 1 ? ((el[0] as HTMLElement).dataset.ekran ?? null) : null));
}

/** Adresi değiştirir ve hashchange işlenmeden, aynı görevde `hazir`'i okur. */
async function adresDegistirHemenOku(page: Page, adres: string): Promise<boolean> {
  return page.evaluate((a) => {
    location.hash = a;
    return window.__tezgah!.hazir === true;
  }, adres);
}

test.describe("Kabuk hazır sinyali @slow", () => {
  let hatalar: string[];

  test.beforeEach(async ({ page, request }) => {
    hatalar = [];
    page.on("console", (m) => {
      if (m.type() === "error") hatalar.push(m.text());
    });
    page.on("pageerror", (e) => hatalar.push(String(e)));
    const liste: SunucuEkrani[] = (await (await request.get("/api/ekranlar")).json()).ekranlar;
    const model = liste.find((e) => e.ad === "model");
    test.skip(!model || !model.hazir, `model ekranı kullanılamaz (${model?.neden ?? "listede yok"})`);
  });

  test.afterEach(() => {
    expect(hatalar, "konsolda hata olmamalı").toEqual([]);
  });

  test("adres başka ekranı gösterince hazir hemen false; yeni ekran açılınca true", async ({ page }) => {
    await page.goto("/#/freze");
    await hazirBekle(page);
    expect(await etkin(page)).toBe("freze");

    expect(await adresDegistirHemenOku(page, "#/model")).toBe(false);
    await hazirBekle(page);
    expect(await etkin(page)).toBe("model");
    expect(page.url()).toContain("#/model");

    expect(await adresDegistirHemenOku(page, "#/freze")).toBe(false);
    await hazirBekle(page);
    expect(await etkin(page)).toBe("freze");
  });

  test("etkin ekranın ac()'ı sürerken hazir false; bitince true", async ({ page }) => {
    let birak!: () => void;
    const kapi = new Promise<void>((r) => (birak = r));
    let bekletilen = 0;
    await page.route(
      (u) => u.pathname === "/api/ekran/model/",
      async (route) => {
        if (route.request().method() === "GET") {
          bekletilen++;
          await kapi;
        }
        await route.continue();
      },
    );

    await page.goto("/#/freze");
    await hazirBekle(page);
    await page.evaluate(() => {
      location.hash = "#/model";
    });

    // Model ekranı etkin, adres de onu gösteriyor; ama açılış isteği bekletildiği için ac() sürüyor.
    await expect.poll(() => bekletilen).toBeGreaterThan(0);
    await expect.poll(() => etkin(page)).toBe("model");
    expect(page.url()).toContain("#/model");
    for (let i = 0; i < 5; i++) {
      expect(await hazirOku(page)).toBe(false);
      await page.waitForTimeout(100);
    }

    birak();
    await hazirBekle(page);
    expect(await etkin(page)).toBe("model");
  });

  test("ac() sürerken başka sekmeye geçilirse yarım açılış hazır saymaz", async ({ page }) => {
    let birak!: () => void;
    const kapi = new Promise<void>((r) => (birak = r));
    let bekletilen = 0;
    await page.route(
      (u) => u.pathname === "/api/ekran/model/",
      async (route) => {
        if (route.request().method() === "GET") {
          bekletilen++;
          await kapi;
        }
        await route.continue();
      },
    );

    await page.goto("/#/freze");
    await hazirBekle(page);
    await page.evaluate(() => {
      location.hash = "#/model";
    });
    await expect.poll(() => bekletilen).toBeGreaterThan(0);

    expect(await adresDegistirHemenOku(page, "#/freze")).toBe(false);
    await hazirBekle(page);
    expect(await etkin(page)).toBe("freze");

    // Geride kalan model açılışı bitince freze'nin hazır sinyali bozulmaz.
    birak();
    await page.waitForTimeout(300);
    expect(await etkin(page)).toBe("freze");
    expect(await hazirOku(page)).toBe(true);
  });
});
