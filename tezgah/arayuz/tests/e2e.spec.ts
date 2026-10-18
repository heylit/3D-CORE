// SPEC 24 K8 + K10 — uçtan uca (Playwright). Yalnızca yerelde, pre-push'ta çalışır (CI'da yok).
// Sunucu playwright.config.ts'deki webServer ile açılır (python -m tezgah, derlenmiş dist/).
//
// Sayılar arayüzden değil `window.__tezgah` kancasından (src/kanca.ts) ve sunucu yanıtlarından okunur.
// Testin dayandığı DOM işaretleri (data-testid):
//   gcode-satir    G-code panelindeki her satır; `data-satir` = gcode indeksi
//   zaman-seridi   zaman şeridi (sürüklenebilir alan)
//   islem          iş yığınındaki her işlem; `data-islem` = işlem indeksi (tıklanınca müfettişte açılır)
//   parametre      müfettişteki parametre girdisi; `data-anahtar` = parametre anahtarı (ör. "D")
//   komut-cubugu   Ctrl K ile açılan komut çubuğu

import { expect, test, type Page } from "@playwright/test";
import type { Is, Nokta3 } from "../src/tipler";
import "../src/kanca";

const EPS = 5e-4; // mm, K2 canlı bağ toleransı

async function hazir(page: Page): Promise<void> {
  await page.waitForFunction(() => window.__tezgah?.hazir === true, null, { timeout: 30_000 });
}

/** Belgedeki sim ikili biçimi (tezgah/kopru.py sim_ikili): k anındaki yüzey. */
function simYuzey(buf: ArrayBuffer, k: number): Float32Array {
  const hiza = (n: number) => Math.ceil(n / 8) * 8;
  const dv = new DataView(buf);
  const nx = dv.getUint32(4, true);
  const ny = dv.getUint32(8, true);
  const m = dv.getUint32(12, true);
  let yer = 16;
  const izgara = new Float64Array(buf.slice(yer, yer + 48));
  yer = hiza(yer + 48);
  const ofset = new Uint32Array(buf.slice(yer, yer + 4 * (nx * ny + 1)));
  yer = hiza(yer + 4 * (nx * ny + 1));
  const K = new Int32Array(buf.slice(yer, yer + 4 * m));
  yer = hiza(yer + 4 * m);
  const Z = new Float32Array(buf.slice(yer, yer + 4 * m));
  const Y = new Float32Array(nx * ny).fill(izgara[4]); // z_ust
  for (let c = 0; c < nx * ny; c++) {
    for (let e = ofset[c]; e < ofset[c + 1]; e++) if (K[e] <= k) Y[c] = Z[e];
  }
  return Y;
}

/** Yanıt gövdesi → ArrayBuffer. */
async function ikili(page: Page, yol: string): Promise<ArrayBuffer> {
  const b = await (await page.request.get(yol)).body();
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer;
}

/** Nokta sayısı n (noktalar_ikili başlığı). */
function noktaSayisi(buf: ArrayBuffer): number {
  return new DataView(buf).getUint32(4, true);
}

function yakin(a: Nokta3 | null, b: Nokta3, eps = EPS): void {
  expect(a).not.toBeNull();
  for (let i = 0; i < 3; i++) expect(Math.abs((a as Nokta3)[i] - b[i])).toBeLessThanOrEqual(eps);
}

test.describe("Tezgah uçtan uca @slow", () => {
  let hatalar: string[];
  let ad: string;
  let is: Is;

  test.beforeEach(async ({ page, request }) => {
    hatalar = [];
    page.on("console", (m) => {
      if (m.type() === "error") hatalar.push(m.text());
    });
    page.on("pageerror", (e) => hatalar.push(String(e)));
    ad = (await (await request.get("/api/isler")).json()).isler[0];
    await page.goto("/");
    await hazir(page);
    is = await (await request.get(`/api/is/${ad}`)).json();
  });

  test.afterEach(() => {
    expect(hatalar, "konsolda hata olmamalı").toEqual([]);
  });

  test("örnek iş açılır, G-code ve süre sunucuyla aynı", async ({ page }) => {
    expect(await page.evaluate(() => window.__tezgah!.gcodeSatirSayisi())).toBe(is.gcode.length);
    expect(await page.evaluate(() => window.__tezgah!.toplamSure())).toBeCloseTo(is.sure.toplam, 9);
  });

  test("G-code satırının üstüne gelince hayalet takım o satırın uç noktasında", async ({ page }) => {
    const satirlar = is.satir_hareket
      .map((ar, i) => (ar === null ? -1 : i))
      .filter((i) => i >= 0)
      .slice(0, 12);
    expect(satirlar.length).toBeGreaterThan(0);
    for (const i of [satirlar[0], satirlar[Math.floor(satirlar.length / 2)], satirlar[satirlar.length - 1]]) {
      const el = page.locator(`[data-testid="gcode-satir"][data-satir="${i}"]`);
      await el.scrollIntoViewIfNeeded();
      await el.hover();
      const son = (is.satir_hareket[i] as [number, number])[1];
      await expect
        .poll(async () => page.evaluate(() => window.__tezgah!.hayaletKonum()))
        .not.toBeNull();
      yakin(await page.evaluate(() => window.__tezgah!.hayaletKonum()), is.hareketler[son].b);
    }
  });

  test("zaman şeridi sürüklenince DRO değişir; şerit sonunda yüzey son sim yüzeyi", async ({ page }) => {
    const serit = page.getByTestId("zaman-seridi");
    const kutu = await serit.boundingBox();
    expect(kutu).not.toBeNull();
    const { x, y, width, height } = kutu!;
    const orta = y + height / 2;

    await page.mouse.move(x + 2, orta);
    await page.mouse.down();
    await page.mouse.move(x + width * 0.3, orta, { steps: 5 });
    await page.mouse.up();
    const dro1 = await page.evaluate(() => window.__tezgah!.dro());

    await page.mouse.move(x + width * 0.3, orta);
    await page.mouse.down();
    await page.mouse.move(x + width - 1, orta, { steps: 10 });
    await page.mouse.move(x + width + 40, orta, { steps: 2 }); // şeridin dışına taşma: sona kırpılır
    await page.mouse.up();
    const dro2 = await page.evaluate(() => window.__tezgah!.dro());
    expect(dro2).not.toEqual(dro1);

    expect(await page.evaluate(() => window.__tezgah!.zaman())).toBeCloseTo(is.sure.toplam, 6);
    const n = noktaSayisi(await ikili(page, `/api/is/${ad}/noktalar`));
    const beklenen = simYuzey(await ikili(page, `/api/is/${ad}/sim`), n - 1); // son nokta k = n − 1
    const yuzey = await page.evaluate(() => {
      const y = window.__tezgah!.yuzey();
      return y === null ? null : Array.from(y);
    });
    expect(yuzey).not.toBeNull();
    expect(yuzey!.length).toBe(beklenen.length);
    let fark = 0;
    for (let c = 0; c < beklenen.length; c++) fark = Math.max(fark, Math.abs(yuzey![c] - beklenen[c]));
    expect(fark).toBe(0);
  });

  test("takım çapı değişince G-code satır sayısı ve süre sunucu yanıtıyla aynı", async ({ page }) => {
    const cep = is.islemler.findIndex((i) => i.anahtar === "cep");
    expect(cep).toBeGreaterThanOrEqual(0);
    await page.locator(`[data-testid="islem"][data-islem="${cep}"]`).click();
    const D = page.locator('[data-testid="parametre"][data-anahtar="D"]');
    await expect(D).toBeVisible();
    const D0 = is.islemler[cep].parametreler.D;
    const D1 = D0 > 6 ? D0 - 2 : D0 + 2;

    const yanitBekle = page.waitForResponse(
      (r) => r.url().endsWith(`/api/is/${ad}/parametre`) && r.request().method() === "POST",
    );
    await D.evaluate((el, v) => {
      const g = el as HTMLInputElement;
      g.value = String(v);
      g.dispatchEvent(new Event("input", { bubbles: true }));
      g.dispatchEvent(new Event("change", { bubbles: true }));
    }, D1);
    const yanit = await yanitBekle;
    expect(yanit.status()).toBe(200);
    const govde = (await yanit.json()) as { is: Is; sure_farki: number };
    expect(govde.is.islemler[cep].parametreler.D).toBe(D1);

    await expect
      .poll(async () => page.evaluate(() => window.__tezgah!.gcodeSatirSayisi()))
      .toBe(govde.is.gcode.length);
    expect(await page.evaluate(() => window.__tezgah!.toplamSure())).toBeCloseTo(govde.is.sure.toplam, 9);

    // Sunucu durumunu geri al (diğer testler varsayılan işle başlasın).
    await page.request.post(`/api/is/${ad}/parametre`, { data: { islem: cep, anahtar: "D", deger: D0 } });
  });

  test("400 px ve 1440 px: ekran görüntüsü, yatay kaydırma yok", async ({ page }) => {
    for (const genislik of [400, 1440]) {
      await page.setViewportSize({ width: genislik, height: 900 });
      await page.waitForTimeout(200);
      const { sw, cw } = await page.evaluate(() => ({
        sw: document.documentElement.scrollWidth,
        cw: document.documentElement.clientWidth,
      }));
      expect(sw, `${genislik} px'te yatay kaydırma`).toBeLessThanOrEqual(cw);
      await page.screenshot({ path: `test-results/tezgah-${genislik}.png`, fullPage: true });
    }
  });

  test("K10 klavye: Boşluk oynat/duraklat, ←/→ adım, Ctrl K komut çubuğu, Esc kapat", async ({ page }) => {
    await page.locator("body").click({ position: { x: 1, y: 1 } });
    const t0 = await page.evaluate(() => window.__tezgah!.zaman());
    await page.keyboard.press("Space");
    await page.waitForTimeout(600);
    await page.keyboard.press("Space");
    const t1 = await page.evaluate(() => window.__tezgah!.zaman());
    expect(t1).toBeGreaterThan(t0);
    await page.waitForTimeout(300);
    expect(await page.evaluate(() => window.__tezgah!.zaman())).toBe(t1); // duraklatıldı

    await page.keyboard.press("ArrowRight");
    const t2 = await page.evaluate(() => window.__tezgah!.zaman());
    expect(t2).toBeGreaterThan(t1);
    await page.keyboard.press("ArrowLeft");
    expect(await page.evaluate(() => window.__tezgah!.zaman())).toBeLessThan(t2);

    const komut = page.getByTestId("komut-cubugu");
    await page.keyboard.press("Control+k");
    await expect(komut).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(komut).toBeHidden();
  });

  test("K10: her etkileşimli öğenin görünür odak durumu var", async ({ page }) => {
    const gorulen = new Set<string>();
    for (let i = 0; i < 25; i++) {
      await page.keyboard.press("Tab");
      const odak = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body) return null;
        const s = getComputedStyle(el);
        const cizgi = s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0;
        const golge = s.boxShadow !== "none" && s.boxShadow !== "";
        return { kim: el.outerHTML.slice(0, 80), gorunur: cizgi || golge };
      });
      if (odak === null) continue;
      gorulen.add(odak.kim);
      expect(odak.gorunur, `odak görünmüyor: ${odak.kim}`).toBe(true);
    }
    expect(gorulen.size).toBeGreaterThan(3);
  });
});
