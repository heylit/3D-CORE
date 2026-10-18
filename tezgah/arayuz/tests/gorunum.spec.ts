// SPEC 65b K5–K8 — Görünüm sekmesi uçtan uca (Playwright, @slow). Yalnızca yerelde, pre-push'ta çalışır (CI'da yok).
// Testler yalnız specs/65b-pbr-gorunum.md'den ve src/gorunum.ts arayüzünden (GorunumKanca) yazıldı; gövdeler
// okunmadı. Sunucu playwright.config.ts'deki webServer ile açılır (python -m tezgah, derlenmiş dist/).
//
// "Uygulanmamış": sunucuda "gorunum" ekranı yoksa testler test.fail ile beklenen hata sayılır (atlanmaz). Ekran
// gelince koşul kendiliğinden kalkar ve testler normal çalışır.
//
// Varsayımlar (metinde açık değil):
//   - Sekme: ekran adı "gorunum", adres "#/gorunum"; kanca window.__tezgah.gorunum (GorunumKanca).
//   - Örnek montajın bileşenleri "govde" (C45), "kapak" (6061, bir yüzü eloksal), "blok" (POM-C).
//   - Mod düğmeleri: data-testid="gorunum-modu", data-mod = "gercekci" | "teknik" | "analiz". Açılış modu gercekci.
//   - K7 için kanca ek olarak ekranKutusu(bilesen) verir: bileşenin canvas üzerindeki piksel kutusu
//     [x0, y0, x1, y1] (canvas'ın sol üst köşesine göre, CSS pikseli); bileşen görünmüyorsa null.
//   - K7 "parçanın pikselleri": teknik modda arka plandan farklı pikseller parça maskesidir; gercekci modda bu
//     maskenin %95'inden fazlası arka plan renginde olmamalı. Arka plan rengi canvas köşe pikselidir.

import { expect, test, type Page } from "@playwright/test";
import { ACESFilmicToneMapping } from "three";
import type { GorunumKanca, GorunumModu } from "../src/gorunum";
import "../src/kanca";

type Kutu = [number, number, number, number];
type Kanca = GorunumKanca & { ekranKutusu(bilesen: string): Kutu | null };

const SEKME = "#/gorunum";
const UYGULANMAMIS = 'SPEC 65b: "gorunum" ekranı henüz yok (uygulanmamış)';

async function ekranVar(page: Page): Promise<boolean> {
  const r = await page.request.get("/api/ekranlar");
  const liste: { ad: string }[] = (await r.json()).ekranlar;
  return liste.some((e) => e.ad === "gorunum");
}

/** Ekran yoksa testi beklenen hata olarak işaretler ve hemen düşürür. */
async function uygulanmamissaDus(page: Page): Promise<void> {
  const var_ = await ekranVar(page);
  test.fail(!var_, UYGULANMAMIS);
  if (!var_) throw new Error(UYGULANMAMIS);
}

async function ac(page: Page): Promise<void> {
  await page.goto(`/${SEKME}`);
  await page.waitForFunction(
    () => {
      const k = window.__tezgah?.gorunum as GorunumKanca | undefined;
      return window.__tezgah?.hazir === true && !!k && k.malzemeler("govde").length > 0;
    },
    null,
    { timeout: 30_000 },
  );
  await kare(page);
}

/** İki animasyon karesi bekler (mod değişikliği çizilsin). */
async function kare(page: Page): Promise<void> {
  await page.evaluate(
    () => new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r()))),
  );
}

async function modSec(page: Page, mod: GorunumModu): Promise<void> {
  await page.locator(`[data-testid="gorunum-modu"][data-mod="${mod}"]`).click();
  await expect.poll(() => kanca(page, "mod")).toBe(mod);
  await kare(page);
}

/** window.__tezgah.gorunum.<yontem>(...argumanlar) */
async function kanca<Y extends keyof Kanca>(
  page: Page,
  yontem: Y,
  ...argumanlar: Parameters<Kanca[Y]>
): Promise<Awaited<ReturnType<Kanca[Y]>>> {
  return page.evaluate(
    ([y, a]) => {
      const k = window.__tezgah!.gorunum as Record<string, (...x: unknown[]) => unknown>;
      return k[y as string](...(a as unknown[]));
    },
    [yontem, argumanlar] as const,
  ) as Promise<Awaited<ReturnType<Kanca[Y]>>>;
}

async function malzemeler(page: Page, bilesen: string) {
  return kanca(page, "malzemeler", bilesen);
}

/** Canvas ekran görüntüsünün RGBA pikselleri (tarayıcıda çözülür; ek bağımlılık yok). */
async function pikseller(page: Page): Promise<{ w: number; h: number; d: number[] }> {
  const canvas = page.locator("canvas").first();
  const png = (await canvas.screenshot()).toString("base64");
  return page.evaluate(async (b64) => {
    const img = new Image();
    img.src = `data:image/png;base64,${b64}`;
    await img.decode();
    const c = document.createElement("canvas");
    c.width = img.width;
    c.height = img.height;
    const ctx = c.getContext("2d")!;
    ctx.drawImage(img, 0, 0);
    return { w: c.width, h: c.height, d: Array.from(ctx.getImageData(0, 0, c.width, c.height).data) };
  }, png);
}

function arkaPlan(p: { w: number; h: number; d: number[] }): [number, number, number] {
  return [p.d[0], p.d[1], p.d[2]]; // sol üst köşe
}

function arkaPlanMi(p: { d: number[] }, i: number, ap: [number, number, number]): boolean {
  const t = 6; // sıkıştırma / dithering payı
  return Math.abs(p.d[i] - ap[0]) <= t && Math.abs(p.d[i + 1] - ap[1]) <= t && Math.abs(p.d[i + 2] - ap[2]) <= t;
}

/** Kutudaki parça (arka plan olmayan) piksellerinin parlaklık standart sapması. */
function parlaklikSapmasi(p: { w: number; h: number; d: number[] }, kutu: Kutu, olcek: number): number {
  const ap = arkaPlan(p);
  const [x0, y0, x1, y1] = kutu.map((v) => Math.round(v * olcek));
  const L: number[] = [];
  for (let y = Math.max(0, y0); y < Math.min(p.h, y1); y++) {
    for (let x = Math.max(0, x0); x < Math.min(p.w, x1); x++) {
      const i = 4 * (y * p.w + x);
      if (arkaPlanMi(p, i, ap)) continue;
      L.push(0.2126 * p.d[i] + 0.7152 * p.d[i + 1] + 0.0722 * p.d[i + 2]);
    }
  }
  expect(L.length, "kutuda parça pikseli olmalı").toBeGreaterThan(100);
  const ort = L.reduce((a, b) => a + b, 0) / L.length;
  return Math.sqrt(L.reduce((a, b) => a + (b - ort) ** 2, 0) / L.length);
}

test.describe("SPEC 65b Görünüm sekmesi @slow", () => {
  let hatalar: string[];
  let disIstekler: string[];

  test.beforeEach(async ({ page }) => {
    hatalar = [];
    disIstekler = [];
    page.on("console", (m) => {
      if (m.type() === "error") hatalar.push(m.text());
    });
    page.on("pageerror", (e) => hatalar.push(String(e)));
    page.on("request", (r) => {
      const u = new URL(r.url());
      if (u.protocol === "data:" || u.protocol === "blob:") return;
      if (u.hostname !== "127.0.0.1") disIstekler.push(r.url());
    });
  });

  test.afterEach(() => {
    expect(hatalar, "konsolda hata olmamalı").toEqual([]);
  });

  test("K5 gövde PBR metal, kapağın eloksal yüzü ayrı grup, ortam ve ton eşleme", async ({ page }) => {
    await uygulanmamissaDus(page);
    await ac(page);
    expect(await kanca(page, "mod")).toBe("gercekci");

    const govde = await malzemeler(page, "govde");
    expect(govde.length).toBeGreaterThan(0);
    for (const m of govde) {
      expect(m.tip).toBe("MeshPhysicalMaterial");
      expect(m.metalness).toBe(1);
    }

    const kapak = await malzemeler(page, "kapak");
    expect(kapak.length, "eloksal yüz ayrı malzeme grubunda").toBeGreaterThanOrEqual(2);
    for (const m of kapak) expect(m.tip).toBe("MeshPhysicalMaterial");
    expect(kapak.filter((m) => m.clearcoat === 1).length).toBeGreaterThanOrEqual(1);
    expect(kapak.some((m) => m.clearcoat !== 1), "kapağın eloksal olmayan yüzleri de var").toBe(true);

    expect(await kanca(page, "ortamVar")).toBe(true);
    expect(await kanca(page, "tonEsleme")).toBe(ACESFilmicToneMapping);
  });

  test("K6 gercekci → analiz → gercekci: analizde vertex renk, PBR kapalı; program sayısı artmaz", async ({
    page,
  }) => {
    await uygulanmamissaDus(page);
    await ac(page);
    const once = { govde: await malzemeler(page, "govde"), kapak: await malzemeler(page, "kapak") };

    const tur = async () => {
      await modSec(page, "analiz");
      for (const b of ["govde", "kapak", "blok"]) {
        const ms = await malzemeler(page, b);
        expect(ms.length).toBeGreaterThan(0);
        for (const m of ms) {
          expect(m.vertexColors, `${b} analizde vertex renkli`).toBe(true);
          expect(["MeshPhysicalMaterial", "MeshStandardMaterial"]).not.toContain(m.tip);
        }
      }
      await modSec(page, "gercekci");
      expect(await malzemeler(page, "govde")).toEqual(once.govde);
      expect(await malzemeler(page, "kapak")).toEqual(once.kapak);
      return kanca(page, "programSayisi");
    };

    const p1 = await tur();
    const p2 = await tur();
    expect(p2, "ikinci turda yeni shader programı yok (önbellek)").toBeLessThanOrEqual(p1);
    expect(await kanca(page, "ortamVar")).toBe(true);
  });

  test("K7 parça çizildi; metal gövdenin parlaklık sapması mat POM bloğundan büyük", async ({ page }) => {
    await uygulanmamissaDus(page);
    await ac(page);
    const canvas = page.locator("canvas").first();
    const cssGenislik = (await canvas.boundingBox())!.width;

    await modSec(page, "teknik");
    const teknik = await pikseller(page);
    await modSec(page, "gercekci");
    const gercek = await pikseller(page);
    expect([gercek.w, gercek.h]).toEqual([teknik.w, teknik.h]);

    const apT = arkaPlan(teknik);
    const apG = arkaPlan(gercek);
    let maske = 0;
    let dolu = 0;
    for (let i = 0; i < teknik.d.length; i += 4) {
      if (arkaPlanMi(teknik, i, apT)) continue;
      maske++;
      if (!arkaPlanMi(gercek, i, apG)) dolu++;
    }
    expect(maske, "teknik modda parça görünür").toBeGreaterThan(1000);
    expect(dolu / maske, "parça pikselleri arka plan renginde değil").toBeGreaterThan(0.95);

    const olcek = gercek.w / cssGenislik;
    const govdeKutu = await kanca(page, "ekranKutusu", "govde");
    const blokKutu = await kanca(page, "ekranKutusu", "blok");
    expect(govdeKutu).not.toBeNull();
    expect(blokKutu).not.toBeNull();
    const sGovde = parlaklikSapmasi(gercek, govdeKutu!, olcek);
    const sBlok = parlaklikSapmasi(gercek, blokKutu!, olcek);
    expect(sGovde, "metalde yansıma var").toBeGreaterThan(sBlok);
  });

  // index.html bugün Google Fonts yüklüyor (65b'den bağımsız; Tezgah ayrı PR'la kaldıracak). Katı K8 o PR'a kadar
  // beklenen hatadır; PR girince test geçer, test.fail kırmızı olur ve işaret kaldırılır.
  const YAZI_TIPI = new Set(["fonts.googleapis.com", "fonts.gstatic.com"]);

  async function cevrimdisiGezinti(page: Page): Promise<void> {
    await ac(page);
    await modSec(page, "analiz");
    await modSec(page, "gercekci");
    await page.waitForLoadState("networkidle");
  }

  test("K8 çevrimdışı (katı): 127.0.0.1 dışına hiç istek yok", async ({ page }) => {
    test.fail(true, "index.html Google Fonts kaldırılınca");
    await uygulanmamissaDus(page);
    await cevrimdisiGezinti(page);
    expect(disIstekler).toEqual([]);
  });

  test("K8 çevrimdışı (65b): yazı tipi dışında 127.0.0.1 dışına istek yok; /api/gorunum yerel", async ({
    page,
  }) => {
    await uygulanmamissaDus(page);
    const gorunumIstekleri: string[] = [];
    page.on("request", (r) => {
      if (new URL(r.url()).pathname.startsWith("/api/gorunum")) gorunumIstekleri.push(r.url());
    });
    await cevrimdisiGezinti(page);
    expect(disIstekler.filter((u) => !YAZI_TIPI.has(new URL(u).hostname))).toEqual([]);
    expect(gorunumIstekleri.length, "sekme görünümü /api/gorunum'dan alır").toBeGreaterThan(0);
  });
});
