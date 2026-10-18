// SPEC 37 K16 — kabuk uçtan uca (Playwright). Yalnızca yerelde, pre-push'ta çalışır (CI'da yok).
// Testler yalnız specs/37-proje-kabuk.md'den yazıldı; kabuk.ts gövdesi okunmadı.
// Sayılar arayüzden değil `window.__tezgah.kabuk` kancasından ve sunucu yanıtlarından okunur.
//
// Kanca (SPEC 37 "Test kancası"): window.__tezgah.kabuk = { proje(): ProjeDurumu, etki(): EtkiSatiri[] | null,
//   palet(): string[] }  — etki(): palette görünen etki kartının satırları (önizleme ya da son etki).
// Testin dayandığı DOM işaretleri (data-testid), SPEC 37 ön yüz bölümündeki öğeler için:
//   komut-paleti    Ctrl K ile açılan palet;           palet-girdi   paletin metin kutusu
//   etki-karti      etki kartı;                        sekme         üst sekmeler, `data-ekran` = ekran adı
//   rozet           sekmenin içindeki fark rozeti
// Varsayım: örnek proje POST /api/proje/ornek/yatak_grubu ile açılır; kayıt yolu sunucunun çalışma klasörüne
// (depo kökü) göredir ve gitignore'daki test-results/ altındadır.

import { expect, test, type Page } from "@playwright/test";
import type { EtkiSatiri, ProjeDurumu } from "../src/ekranlar/kabuk";
import "../src/kanca";

interface KabukKanca {
  proje(): ProjeDurumu;
  etki(): EtkiSatiri[] | null;
  palet(): string[];
}

const YOL = "tezgah/arayuz/test-results/kabuk_e2e.3dc";
const IS = "kademeli_mil";

async function kabukHazir(page: Page): Promise<void> {
  await page.waitForFunction(() => (window.__tezgah as Record<string, unknown> | undefined)?.kabuk != null, null, {
    timeout: 30_000,
  });
}

async function kanca<T>(page: Page, f: (k: KabukKanca) => T): Promise<T> {
  return page.evaluate(
    (kod) => {
      const k = (window.__tezgah as unknown as { kabuk: KabukKanca }).kabuk;
      return new Function("k", `return (${kod})(k)`)(k);
    },
    f.toString(),
  ) as Promise<T>;
}

async function gecmisUzunlugu(page: Page): Promise<number> {
  return (await (await page.request.get("/api/proje/gecmis")).json()).kayitlar.length;
}

async function rozet(page: Page, ekran: string): Promise<string | null> {
  const r = page.locator(`[data-testid="sekme"][data-ekran="${ekran}"] [data-testid="rozet"]`);
  return (await r.count()) ? ((await r.first().textContent()) ?? "").trim() : null;
}

async function yatayKaydirmaYok(page: Page): Promise<void> {
  const [sw, cw] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(sw, "yatay kaydırma olmamalı").toBeLessThanOrEqual(cw);
  for (const id of ["komut-paleti", "etki-karti"]) {
    const kutu = await page.getByTestId(id).boundingBox();
    if (kutu) expect(kutu.x + kutu.width, id).toBeLessThanOrEqual(cw + 0.5);
  }
}

async function odakGorunur(page: Page): Promise<void> {
  const ogeler = page.locator(
    '[data-testid="komut-paleti"] :is(button, input, [role="option"], a, [tabindex]:not([tabindex="-1"]))',
  );
  const n = await ogeler.count();
  expect(n).toBeGreaterThan(0);
  for (let i = 0; i < n; i++) {
    const o = ogeler.nth(i);
    if (!(await o.isVisible())) continue;
    await o.focus();
    const iz = await o.evaluate((e) => {
      const s = getComputedStyle(e);
      return { outline: s.outlineStyle !== "none" && s.outlineWidth !== "0px", golge: s.boxShadow !== "none" };
    });
    expect(iz.outline || iz.golge, `odak durumu görünür olmalı (${i})`).toBe(true);
  }
}

test.describe("Kabuk uçtan uca @slow", () => {
  let hatalar: string[];

  test.beforeEach(async ({ page, request }) => {
    hatalar = [];
    page.on("console", (m) => {
      if (m.type() === "error") hatalar.push(m.text());
    });
    page.on("pageerror", (e) => hatalar.push(String(e)));
    expect((await request.post("/api/proje/ornek/yatak_grubu")).status()).toBe(200);
    await page.goto("/");
    await kabukHazir(page);
  });

  test.afterEach(() => {
    expect(hatalar, "konsolda hata olmamalı").toEqual([]);
  });

  test("palet önizler, Enter uygular, Ctrl Z geri alır, Ctrl S kaydeder, geçmiş dosyada yaşar", async ({
    page,
  }) => {
    const isOnce = await (await page.request.get(`/api/is/${IS}`)).json();
    const uzunluk0 = await gecmisUzunlugu(page);

    // Ctrl K, "L 9.5": Enter'dan önce önizleme; geçmiş değişmez
    await page.keyboard.press("Control+k");
    await expect(page.getByTestId("komut-paleti")).toBeVisible();
    const onizleme = page.waitForResponse(
      (r) => r.url().endsWith("/api/proje/degistir") && r.request().postDataJSON()?.onizle === true && r.ok(),
    );
    await page.getByTestId("palet-girdi").fill("L 9.5");
    const yanit = await (await onizleme).json();
    await expect(page.getByTestId("etki-karti")).toBeVisible();
    await expect.poll(() => kanca(page, (k) => JSON.stringify(k.etki()))).toBe(JSON.stringify(yanit.etki));
    const torna = (yanit.etki as EtkiSatiri[]).find((x) => x.bolum === "torna_isleri");
    expect(torna).toBeDefined();
    expect(Object.keys(torna!.fark).length).toBeGreaterThan(0);
    expect(await gecmisUzunlugu(page)).toBe(uzunluk0);
    expect(await kanca(page, (k) => k.palet().length)).toBeGreaterThan(0);

    // Enter: uygulanır; torna ve montaj sekmelerinde rozet, başlıkta •
    await page.keyboard.press("Enter");
    await expect.poll(() => gecmisUzunlugu(page)).toBe(uzunluk0 + 1);
    await expect.poll(() => rozet(page, "torna")).not.toBeNull();
    await expect.poll(() => rozet(page, "montaj")).not.toBeNull();
    await expect(page).toHaveTitle(/•/);
    expect(await kanca(page, (k) => k.proje().kirli)).toBe(true);
    const tornaRozeti = (await rozet(page, "torna")) as string;
    expect(tornaRozeti).toMatch(/[−-]/);

    // Ctrl Z: torna işi ilk haliyle aynı; rozetler ters işaretli
    await page.locator("body").click({ position: { x: 1, y: 1 } });
    await page.keyboard.press("Control+z");
    await expect.poll(async () => (await page.request.get(`/api/is/${IS}`)).json()).toEqual(isOnce);
    await expect.poll(() => kanca(page, (k) => k.proje().yinele)).not.toBeNull();
    await expect.poll(() => rozet(page, "torna")).not.toBe(tornaRozeti);
    expect((await rozet(page, "torna")) ?? "").not.toMatch(/[−-]\s*\d/);

    // Ctrl Shift Z: yinele
    await page.keyboard.press("Control+Shift+z");
    await expect.poll(async () => (await (await page.request.get("/api/proje/gecmis")).json()).konum).toBe(
      uzunluk0 + 1,
    );

    // metin kutusundayken Ctrl Z projeyi geri almaz
    await page.keyboard.press("Control+k");
    await page.getByTestId("palet-girdi").fill("abc");
    await page.getByTestId("palet-girdi").focus();
    await page.keyboard.press("Control+z");
    await page.waitForTimeout(500);
    expect((await (await page.request.get("/api/proje/gecmis")).json()).konum).toBe(uzunluk0 + 1);
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("komut-paleti")).toBeHidden();

    // Ctrl S: yolu olan projede • kalkar (ilk yol sunucuya verilir; son yol kullanılır)
    expect((await page.request.post("/api/proje/kaydet", { data: { yol: YOL } })).status()).toBe(200);
    await page.request.post("/api/proje/degistir", {
      data: {
        etiket: "L 9",
        yamalar: [{ bolum: "torna_isleri", isaretci: `/${IS}/parametreler/L`, deger: 9.0 }],
        onizle: false,
      },
    });
    await page.reload();
    await kabukHazir(page);
    await expect(page).toHaveTitle(/•/);
    await page.locator("body").click({ position: { x: 1, y: 1 } });
    await page.keyboard.press("Control+s");
    await expect.poll(() => kanca(page, (k) => k.proje().kirli)).toBe(false);
    await expect(page).not.toHaveTitle(/•/);
    const etiketler = (await (await page.request.get("/api/proje/gecmis")).json()).kayitlar.map(
      (x: { etiket: string }) => x.etiket,
    );

    // sayfa yenilenip proje yeniden açılınca geçmişte aynı etiketler
    expect((await page.request.post("/api/proje/ornek/yatak_grubu")).status()).toBe(200);
    expect((await page.request.post("/api/proje/ac", { data: { yol: YOL } })).status()).toBe(200);
    await page.reload();
    await kabukHazir(page);
    const sonra = (await (await page.request.get("/api/proje/gecmis")).json()).kayitlar.map(
      (x: { etiket: string }) => x.etiket,
    );
    expect(sonra).toEqual(etiketler);
    expect(await kanca(page, (k) => k.proje().geri_al)).toBe(etiketler[etiketler.length - 1]);
  });

  for (const genislik of [400, 1440]) {
    test(`palet ve etki kartı ${genislik} px'te yatay kaydırmasız, odak görünür`, async ({ page }) => {
      await page.setViewportSize({ width: genislik, height: 900 });
      await page.reload();
      await kabukHazir(page);
      await page.keyboard.press("Control+k");
      await page.getByTestId("palet-girdi").fill("L 9.5");
      await expect(page.getByTestId("etki-karti")).toBeVisible();
      await yatayKaydirmaYok(page);
      await odakGorunur(page);
    });
  }
});
