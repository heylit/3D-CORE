// SPEC 54 K11 — hata kartı ve kurtarma iletişim kutusu uçtan uca (Playwright). Yalnızca yerelde (pre-push).
// Testler yalnız specs/54-saglamlik.md "Ön yüz" bölümünden yazıldı; kabuk.ts'nin SPEC 54 gövdesi okunmadı.
//
// DOM (SPEC 54): kart [data-testid="hata-karti"], alanlar [data-alan="ne_oldu"|"nesne"|"oneri"],
//   ayrıntı details[data-alan="teknik"] (kapalı), düğme [data-eylem="geri-al"];
//   kurtarma kutusu dialog[data-testid="kurtarma"], düğmeler button[data-secim="kurtar"|"yoksay"|"ikisi"].
// Varsayımlar (SPEC'in açık bıraktığı yerler):
// - Hata yanıtı page.route ile sunucu yerine verilir (422 gövdesi SPEC 54 §REST biçiminde); kart, kabuğun kendi
//   isteğinin (Ctrl Z → POST /api/proje/geri-al, Ctrl S → POST /api/proje/kaydet) yanıtından kurulur.
// - Kabuk açılışta GET /api/proje/kurtarma'yı sorar; `bulunan.okunur && bulunan.farkli` ise kutu açılır.

import { expect, test, type Page, type Route } from "@playwright/test";

const IS = "kademeli_mil";
const YOL = "tezgah/arayuz/test-results/saglamlik_e2e.3dc";

const KART = {
  sinif: "GeometryError",
  nesne: "yatak.step / gövde",
  ne_oldu: "fillet yapılamadı (r = 8 mm)",
  oneri: "yarıçapı 5 mm'nin altına indirin",
  teknik: "Traceback (most recent call last):\n  StdFail_NotDone",
};

async function kabukHazir(page: Page): Promise<void> {
  await page.waitForFunction(() => (window.__tezgah as Record<string, unknown> | undefined)?.kabuk != null, null, {
    timeout: 30_000,
  });
}

function hata422(route: Route): Promise<void> {
  return route.fulfill({
    status: 422,
    contentType: "application/json",
    body: JSON.stringify({ detail: `${KART.nesne}: ${KART.ne_oldu} — ${KART.oneri}`, hata: KART }),
  });
}

async function degistir(page: Page, etiket: string, L: number): Promise<void> {
  const r = await page.request.post("/api/proje/degistir", {
    data: {
      etiket,
      yamalar: [{ bolum: "torna_isleri", isaretci: `/${IS}/parametreler/L`, deger: L }],
      onizle: false,
    },
  });
  expect(r.status()).toBe(200);
}

async function kartiDenetle(page: Page, geriAl: boolean): Promise<void> {
  const kart = page.getByTestId("hata-karti");
  await expect(kart).toBeVisible();
  await expect(kart.locator('[data-alan="ne_oldu"]')).toHaveText(KART.ne_oldu);
  await expect(kart.locator('[data-alan="nesne"]')).toHaveText(KART.nesne);
  await expect(kart.locator('[data-alan="oneri"]')).toHaveText(KART.oneri);
  const ayrinti = kart.locator('details[data-alan="teknik"]');
  await expect(ayrinti).toHaveCount(1);
  expect(await ayrinti.evaluate((e) => (e as HTMLDetailsElement).open)).toBe(false);
  await expect(kart.locator('[data-eylem="geri-al"]')).toHaveCount(geriAl ? 1 : 0);
}

test.describe("Sağlamlık uçtan uca @slow", () => {
  test.beforeEach(async ({ page, request }) => {
    expect((await request.post("/api/proje/ornek/yatak_grubu")).status()).toBe(200);
    await page.route("**/api/proje/kurtarma", (r) =>
      r.request().method() === "GET"
        ? r.fulfill({ contentType: "application/json", body: JSON.stringify({ bulunan: null, adsizlar: [], uyarilar: [] }) })
        : r.continue(),
    );
  });

  test("hata kartı: alanlar, ayrıntı kapalı, geçmiş varken geri al düğmesi", async ({ page }) => {
    await degistir(page, "L 9.5", 9.5);
    await page.goto("/");
    await kabukHazir(page);
    await page.route("**/api/proje/geri-al", hata422);
    await page.locator("body").click({ position: { x: 1, y: 1 } });
    await page.keyboard.press("Control+z");
    await kartiDenetle(page, true);

    // "Son değişikliği geri al" düğmesi gerçek geri al'ı çağırır (yönlendirme kaldırılınca)
    await page.unroute("**/api/proje/geri-al");
    const istek = page.waitForRequest((r) => r.url().endsWith("/api/proje/geri-al") && r.method() === "POST");
    await page.getByTestId("hata-karti").locator('[data-eylem="geri-al"]').click();
    await istek;
    await expect.poll(async () => (await (await page.request.get("/api/proje/gecmis")).json()).konum).toBe(0);
  });

  test("hata kartı: geçmiş boşken geri al düğmesi yok", async ({ page }) => {
    expect((await page.request.post("/api/proje/kaydet", { data: { yol: YOL } })).status()).toBe(200);
    await page.goto("/");
    await kabukHazir(page);
    await page.route("**/api/proje/kaydet", hata422);
    await page.locator("body").click({ position: { x: 1, y: 1 } });
    await page.keyboard.press("Control+s");
    await kartiDenetle(page, false);
  });

  for (const [tutuyor, varsayilan] of [
    [true, "kurtar"],
    [false, "ikisi"],
  ] as const) {
    test(`kurtarma kutusu: üç seçenek, klavye, varsayılan ${varsayilan}`, async ({ page }) => {
      const secimler: string[] = [];
      await page.unroute("**/api/proje/kurtarma");
      await page.route("**/api/proje/kurtarma", (r) => {
        if (r.request().method() === "POST") {
          secimler.push(r.request().postDataJSON()?.secim);
          return r.fulfill({ status: 409, contentType: "application/json", body: '{"detail":"test"}' });
        }
        return r.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            bulunan: { yol: "/is/.yatak.3dc.kurtarma", okunur: true, kaynak_tutuyor: tutuyor, farkli: true, neden: null },
            adsizlar: [],
            uyarilar: [],
          }),
        });
      });
      await page.goto("/");
      await kabukHazir(page);
      const kutu = page.locator('dialog[data-testid="kurtarma"]');
      await expect(kutu).toBeVisible();
      const dugmeler = kutu.locator("button[data-secim]");
      await expect(dugmeler).toHaveCount(3);
      expect(await dugmeler.evaluateAll((d) => d.map((x) => x.getAttribute("data-secim")))).toEqual([
        "kurtar",
        "yoksay",
        "ikisi",
      ]);
      // varsayılan odaklı
      await expect(kutu.locator(`button[data-secim="${varsayilan}"]`)).toBeFocused();
      // Tab ile her seçeneğe erişilir
      const gorulen = new Set<string>();
      for (let i = 0; i < 6; i++) {
        const s = await page.evaluate(() => document.activeElement?.getAttribute("data-secim") ?? null);
        if (s) gorulen.add(s);
        await page.keyboard.press("Tab");
      }
      expect([...gorulen].sort()).toEqual(["ikisi", "kurtar", "yoksay"]);
      // Esc kutuyu kapatır, seçim yapılmaz
      await page.keyboard.press("Escape");
      await expect(kutu).toBeHidden();
      expect(secimler).toEqual([]);
    });
  }
});
