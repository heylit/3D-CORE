// SPEC 25 K18 + K19 — torna ve montaj ekranları uçtan uca (Playwright, @slow). Yalnızca yerelde (pre-push).
// Sunucu playwright.config.ts'deki webServer ile açılır; sayılar arayüzden değil `window.__tezgah` kancasından
// ve sunucu yanıtlarından okunur. Uçlar A3 ekran kaydına göre /api/ekran/torna/... ve /api/ekran/montaj/...
//
// A3 ekran kancaları (src/kanca.ts: window.__tezgah.<ekran>):
//   torna.kesitAcik(): boolean            torna sahnesinde 270° kesit görünümü açık mı (S tuşu)
//   torna.capModu(): boolean              DRO çap mı (varsayılan true; R tuşu yarıçap)
//   torna.seciliIslem(): number | null    torna ekranında seçili işlem indeksi
//   torna.dro(), torna.hayaletKonum(), torna.gcodeSatirSayisi(), torna.toplamSure(), torna.zaman()
//                                         SPEC 24 kancasının torna karşılıkları (dro()[0] çap modunda çap)
//   montaj.montajU(): number              montaj şeridinin konumu u ∈ [0, N]
//   montaj.montajPoz(yol): number[]       sahnede gösterilen bileşen dönüşümü (16, satır öncelikli)
// Üst düzey dro / hayaletKonum / gcodeSatirSayisi / toplamSure freze'nindir. Etkin ekran `location.hash`'ten
// okunur (#/<ekran>[?...]); kabuğa kanca eklenmez.
//
// DOM işaretleri (data-testid):
//   ekran-sekmesi    (A3) üst çubuktaki sekme; `data-ekran` = "freze" | "torna" | "montaj"
//   gcode-satir      (SPEC 24) torna ekranında da G-code satırları; `data-satir` = gcode indeksi
//   montaj-seridi    montaj sırası şeridi
//   girisim-karti    iplik kartı (girişim yoksa "temiz" yazar)
//   oner, uygula     kart düğmeleri
//   sure-farki       uygulanınca torna işinin süre farkı rozeti
//   tornada-goster   torna ekranını değişen işlem seçili açan bağlantı: #/torna?islem=<i>&fark=<s>

import { expect, test, type Locator, type Page } from "@playwright/test";
import type { Is, Nokta3 } from "../src/tipler";
import { kesitAt, tornaSimCoz } from "../src/torna";
import "../src/kanca";

const EPS = 5e-4; // mm (K2 / K3 toleransı)

interface TornaKanca {
  hazir: boolean;
  kesitAcik(): boolean;
  capModu(): boolean;
  seciliIslem(): number | null;
  dro(): Nokta3;
  hayaletKonum(): Nokta3 | null;
  gcodeSatirSayisi(): number;
  toplamSure(): number;
  zaman(): number;
}

interface MontajKanca {
  hazir: boolean;
  montajU(): number;
  montajPoz(yol: string): number[];
}

interface Kanca25 {
  hazir: boolean;
  torna: TornaKanca;
  montaj: MontajKanca;
}

interface Adim {
  i: number;
  yol: string;
  T_once: Record<string, number[][] | number[]>;
  T_sonra: Record<string, number[][] | number[]>;
}

interface Montaj {
  sira: Adim[];
  bilesenler: { yol: string }[];
  girisimler: { a: string; b: string; hacim: number }[];
}

function duz(T: number[][] | number[]): number[] {
  return (T as (number | number[])[]).flat() as number[];
}

async function kanca<T>(page: Page, f: (k: Kanca25) => T): Promise<T> {
  return page.evaluate(
    (kod) => {
      const k = (window as unknown as { __tezgah: Kanca25 }).__tezgah;
      return new Function("k", `return (${kod})(k);`)(k) as T;
    },
    f.toString(),
  );
}

/** Etkin ekran adresten: "#/torna?islem=2" → "torna". */
function etkin(page: Page): string | null {
  const m = new URL(page.url()).hash.match(/^#\/([^?]+)/);
  return m ? m[1] : null;
}

async function hazir(page: Page): Promise<void> {
  await page.waitForFunction(() => (window as unknown as { __tezgah?: Kanca25 }).__tezgah?.hazir === true, null, {
    timeout: 30_000,
  });
}

/** Hedef ekranın kendi kancası hazır olana dek bekler. Sekme değişince adres hemen değişir ama kabuk ekranı
 * biraz sonra açar; o arada `__tezgah.hazir` önceki ekranınkidir (freze), o yüzden ekranın `hazir`'ına bakılır. */
async function ekranHazir(page: Page, ad: string): Promise<void> {
  await page.waitForFunction(
    (a) => (window as unknown as { __tezgah?: Record<string, { hazir?: boolean } | undefined> }).__tezgah?.[a]?.hazir === true,
    ad,
    { timeout: 30_000 },
  );
}

async function ikili(page: Page, yol: string): Promise<ArrayBuffer> {
  const b = await (await page.request.get(yol)).body();
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer;
}

function yakin(a: Nokta3 | null, b: Nokta3, eps = EPS): void {
  expect(a).not.toBeNull();
  for (let i = 0; i < 3; i++) expect(Math.abs((a as Nokta3)[i] - b[i])).toBeLessThanOrEqual(eps);
}

/** Şeridi sağ uçtan (oran 1) verilen orana sürükler; oran < 0 veya > 1 şeridin dışına taşar. */
async function seritSurukle(page: Page, serit: Locator, oran: number): Promise<void> {
  const kutu = await serit.boundingBox();
  expect(kutu).not.toBeNull();
  const { x, y, width, height } = kutu!;
  const orta = y + height / 2;
  const bas = oran < 0.5 ? x + width - 1 : x + 1;
  await page.mouse.move(bas, orta);
  await page.mouse.down();
  await page.mouse.move(x + width * Math.min(Math.max(oran, 0), 1), orta, { steps: 8 });
  if (oran < 0) await page.mouse.move(x - 40, orta, { steps: 2 });
  if (oran > 1) await page.mouse.move(x + width + 40, orta, { steps: 2 });
  await page.mouse.up();
}

function matYakin(a: number[], b: number[], eps = 1e-9): void {
  expect(a.length).toBe(16);
  for (let i = 0; i < 16; i++) expect(Math.abs(a[i] - b[i])).toBeLessThanOrEqual(eps);
}

/** Satırdaki X sözcüğünün sayısı (yorumlar atılır); yoksa null. */
function xSozcugu(satir: string): number | null {
  const m = satir.replace(/\([^()]*\)/g, "").match(/(?<![A-Z])X([+-]?(?:\d+\.?\d*|\.\d+))/);
  return m ? Number(m[1]) : null;
}

test.describe("Tezgah torna ve montaj uçtan uca @slow", () => {
  let hatalar: string[];

  test.beforeEach(async ({ page, request }) => {
    hatalar = [];
    page.on("console", (m) => {
      if (m.type() === "error") hatalar.push(m.text());
    });
    page.on("pageerror", (e) => hatalar.push(String(e)));
    await request.post("/api/sifirla");
    await page.goto("/");
    await hazir(page);
    await page.locator("body").click({ position: { x: 1, y: 1 } });
  });

  test.afterEach(async ({ request }) => {
    await request.post("/api/sifirla");
    expect(hatalar, "konsolda hata olmamalı").toEqual([]);
  });

  test("1/2/3 sekmeleri ve adresler", async ({ page }) => {
    await page.keyboard.press("2");
    await expect.poll(() => etkin(page)).toBe("torna");
    await ekranHazir(page, "torna");
    expect(new URL(page.url()).hash).toBe("#/torna");
    await page.keyboard.press("3");
    await expect.poll(() => etkin(page)).toBe("montaj");
    await ekranHazir(page, "montaj");
    expect(new URL(page.url()).hash).toBe("#/montaj");
    await page.keyboard.press("1");
    await expect.poll(() => etkin(page)).toBe("freze");
    await hazir(page); // freze: kabuğun üst düzey kancası
    expect(new URL(page.url()).hash).toBe("#/freze");
    await page.goto("/#/montaj");
    await hazir(page);
    expect(etkin(page)).toBe("montaj");
    await ekranHazir(page, "montaj");
    for (const s of ["freze", "torna", "montaj"]) {
      await expect(page.locator(`[data-testid="ekran-sekmesi"][data-ekran="${s}"]`)).toBeVisible();
    }
  });

  test("#/torna?is=<ad> torna ekranını o işle açar (A3 iş deposu)", async ({ page, request }) => {
    const is: Is = await (await request.get("/api/ekran/torna/is/kademeli_mil")).json();
    await page.goto("/#/torna?is=kademeli_mil");
    await hazir(page);
    expect(etkin(page)).toBe("torna");
    await ekranHazir(page, "torna");
    await expect.poll(() => kanca(page, (k) => k.torna.gcodeSatirSayisi())).toBe(is.gcode.length);
    expect(await kanca(page, (k) => k.torna.toplamSure())).toBeCloseTo(is.sure.toplam, 9);
  });

  test("torna: satırın üstünde hayali uç satırın uç noktasında, DRO X satırdaki sayı; S kesit, R yarıçap", async ({
    page,
    request,
  }) => {
    const is: Is = await (await request.get("/api/ekran/torna/is/kademeli_mil")).json();
    await page.keyboard.press("2");
    await expect.poll(() => etkin(page)).toBe("torna");
    await ekranHazir(page, "torna");
    await expect.poll(() => kanca(page, (k) => k.torna.gcodeSatirSayisi())).toBe(is.gcode.length);
    expect(await kanca(page, (k) => k.torna.toplamSure())).toBeCloseTo(is.sure.toplam, 9);
    expect(await kanca(page, (k) => k.torna.capModu())).toBe(true);

    const satirlar = is.satir_hareket
      .map((ar, i) => (ar !== null && xSozcugu(is.gcode[i].metin) !== null ? i : -1))
      .filter((i) => i >= 0);
    expect(satirlar.length).toBeGreaterThan(0);
    for (const i of [satirlar[0], satirlar[Math.floor(satirlar.length / 2)], satirlar[satirlar.length - 1]]) {
      const el = page.locator(`[data-testid="gcode-satir"][data-satir="${i}"]`);
      await el.scrollIntoViewIfNeeded();
      await el.hover();
      await expect.poll(() => kanca(page, (k) => k.torna.hayaletKonum())).not.toBeNull();
      const son = (is.satir_hareket[i] as [number, number])[1];
      yakin(await kanca(page, (k) => k.torna.hayaletKonum()), is.hareketler[son].b);
      const dro = await kanca(page, (k) => k.torna.dro());
      expect(Math.abs(dro[0] - (xSozcugu(is.gcode[i].metin) as number))).toBeLessThanOrEqual(EPS);
    }

    await page.locator("body").click({ position: { x: 1, y: 1 } });
    const kesit0 = await kanca(page, (k) => k.torna.kesitAcik());
    await page.keyboard.press("s");
    expect(await kanca(page, (k) => k.torna.kesitAcik())).toBe(!kesit0);
    await page.keyboard.press("s");
    expect(await kanca(page, (k) => k.torna.kesitAcik())).toBe(kesit0);

    await page.keyboard.press("r");
    expect(await kanca(page, (k) => k.torna.capModu())).toBe(false);
    await page.keyboard.press("r");
    expect(await kanca(page, (k) => k.torna.capModu())).toBe(true);
  });

  test("torna sim dizisi: tornaSimCoz + kesitAt bağımsız taramayla aynı (K6 verisi)", async ({ page }) => {
    const buf = await ikili(page, "/api/ekran/torna/is/kademeli_mil/sim");
    const S = tornaSimCoz(buf);
    expect(S.nz).toBeGreaterThan(0);
    for (const k of [0, 5, 50, 1_000_000]) {
      const { dis, ic } = kesitAt(S, k);
      for (let h = 0; h < S.nz; h++) {
        let d = S.rDis0;
        let r = S.rIc0;
        for (let e = S.ofset[h]; e < S.ofset[h + 1]; e++) {
          if (S.k[e] <= k) {
            d = S.rDis[e];
            r = S.rIc[e];
          }
        }
        expect(dis[h]).toBe(Math.fround(d));
        expect(ic[h]).toBe(Math.fround(r));
      }
    }
  });

  test("montaj: şerit başında bileşenler T_once'da, sonunda T_sonra'da; E patlat / topla", async ({
    page,
    request,
  }) => {
    const M: Montaj = await (await request.get("/api/ekran/montaj/yatak_grubu")).json();
    const N = M.sira.length;
    await page.keyboard.press("3");
    await expect.poll(() => etkin(page)).toBe("montaj");
    await ekranHazir(page, "montaj");

    const serit = page.getByTestId("montaj-seridi");
    await seritSurukle(page, serit, -1); // şeridin soluna taşma: başa kırpılır
    await expect.poll(() => kanca(page, (k) => k.montaj.montajU())).toBe(0);
    for (const a of M.sira) {
      const T = await page.evaluate(
        (yol) => (window as unknown as { __tezgah: Kanca25 }).__tezgah.montaj.montajPoz(yol),
        a.yol,
      );
      matYakin(T, duz(a.T_once[a.yol]));
    }
    await seritSurukle(page, serit, 2); // sağa taşma: sona kırpılır
    await expect.poll(() => kanca(page, (k) => k.montaj.montajU())).toBe(N);
    const son = M.sira[N - 1];
    for (const b of M.bilesenler) {
      const T = await page.evaluate(
        (yol) => (window as unknown as { __tezgah: Kanca25 }).__tezgah.montaj.montajPoz(yol),
        b.yol,
      );
      matYakin(T, duz(son.T_sonra[b.yol]));
    }

    await page.keyboard.press("e");
    await expect.poll(() => kanca(page, (k) => k.montaj.montajU())).toBe(0);
    await page.keyboard.press("e");
    await expect.poll(() => kanca(page, (k) => k.montaj.montajU())).toBe(N);

    // Şerit geri sürüklenince montaj patlar (u küçülür).
    await seritSurukle(page, serit, 0.4);
    const u = await kanca(page, (k) => k.montaj.montajU());
    expect(u).toBeGreaterThan(0);
    expect(u).toBeLessThan(N);
  });

  test("iplik: girişim kartı → Öner + Uygula → temiz; torna G-code ve süresi yanıtla aynı; Tornada göster", async ({
    page,
    request,
  }) => {
    const M: Montaj = await (await request.get("/api/ekran/montaj/yatak_grubu")).json();
    expect(M.girisimler.length).toBe(1);
    await page.keyboard.press("3");
    await expect.poll(() => etkin(page)).toBe("montaj");
    await ekranHazir(page, "montaj");
    const kart = page.getByTestId("girisim-karti");
    await expect(kart).toBeVisible();
    await expect(kart).not.toContainText(/temiz/i);

    const oneriYaniti = page.waitForResponse((r) => r.url().includes("/api/ekran/montaj/yatak_grubu/oneri"));
    await page.getByTestId("oner").click();
    const oneri = (await (await oneriYaniti).json()) as { deger: number | null };
    expect(oneri.deger).not.toBeNull();
    expect(Math.abs((oneri.deger as number) - 10)).toBeLessThanOrEqual(1e-3);

    const uygulaYaniti = page.waitForResponse(
      (r) => r.url().endsWith("/api/ekran/montaj/yatak_grubu/parametre") && r.request().method() === "POST",
    );
    await page.getByTestId("uygula").click();
    const yanit = await uygulaYaniti;
    expect(yanit.status()).toBe(200);
    const govde = (await yanit.json()) as { montaj: Montaj; is: Is; sure_farki: number };
    expect(govde.montaj.girisimler).toEqual([]);
    await expect(kart).toContainText(/temiz/i);
    await expect(page.getByTestId("sure-farki")).toBeVisible();

    await page.getByTestId("tornada-goster").click();
    await expect.poll(() => etkin(page)).toBe("torna");
    await ekranHazir(page, "torna");
    const [yol, sorgu] = new URL(page.url()).hash.split("?");
    expect(yol).toBe("#/torna");
    const q = new URLSearchParams(sorgu ?? "");
    expect(q.get("islem")).toMatch(/^\d+$/);
    expect(Number(q.get("fark"))).toBeCloseTo(govde.sure_farki, 3);
    await expect.poll(() => kanca(page, (k) => k.torna.gcodeSatirSayisi())).toBe(govde.is.gcode.length);
    expect(await kanca(page, (k) => k.torna.toplamSure())).toBeCloseTo(govde.is.sure.toplam, 9);
    expect(await kanca(page, (k) => k.torna.seciliIslem())).toBe(Number(q.get("islem")));
    const simdiki: Is = await (await request.get("/api/ekran/torna/is/kademeli_mil")).json();
    expect(simdiki.gcode).toEqual(govde.is.gcode);
  });

  test("400 px ve 1440 px: torna ve montaj ekran görüntüsü, yatay kaydırma yok", async ({ page }) => {
    for (const [tus, ad] of [
      ["2", "torna"],
      ["3", "montaj"],
    ]) {
      await page.keyboard.press(tus);
      await expect.poll(() => etkin(page)).toBe(ad);
      await ekranHazir(page, ad);
      for (const genislik of [400, 1440]) {
        await page.setViewportSize({ width: genislik, height: 900 });
        await page.waitForTimeout(200);
        const { sw, cw } = await page.evaluate(() => ({
          sw: document.documentElement.scrollWidth,
          cw: document.documentElement.clientWidth,
        }));
        expect(sw, `${ad}, ${genislik} px'te yatay kaydırma`).toBeLessThanOrEqual(cw);
        await page.screenshot({ path: `test-results/tezgah-${ad}-${genislik}.png`, fullPage: true });
      }
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.locator("body").click({ position: { x: 1, y: 1 } });
    }
  });

  test("K19: torna ve montaj ekranında her etkileşimli öğenin görünür odağı; glif yanında metin", async ({ page }) => {
    for (const [tus, ad] of [
      ["2", "torna"],
      ["3", "montaj"],
    ]) {
      await page.keyboard.press(tus);
      await expect.poll(() => etkin(page)).toBe(ad);
      await ekranHazir(page, ad);
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
        expect(odak.gorunur, `${ad}: odak görünmüyor: ${odak.kim}`).toBe(true);
      }
      expect(gorulen.size).toBeGreaterThan(3);
      await page.locator("body").click({ position: { x: 1, y: 1 } });
    }
    // Montajda girişim kartı ve serbestlik çipleri metin taşır (renk tek başına bilgi değil).
    await page.keyboard.press("3");
    await expect(page.getByTestId("girisim-karti")).toHaveText(/\S/);
  });
});
