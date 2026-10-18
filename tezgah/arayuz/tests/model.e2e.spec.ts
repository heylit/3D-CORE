// SPEC 26 K11 + K12 — modelleme ekranı uçtan uca (Playwright, @slow). Yalnızca yerelde, pre-push'ta çalışır
// (CI'da yok). Testler yalnız specs/26-tezgah-modelleme.md'den (Ek A dahil) yazıldı; ekranlar/model.ts gövdesi
// okunmadı. Sunucu playwright.config.ts'deki webServer ile açılır (python -m tezgah, derlenmiş dist/).
// Sayılar arayüzden değil `window.__tezgah.model` kancasından ve sunucu yanıtlarından okunur (SPEC 24 ilkesi:
// arayüz mühendislik sayısı hesaplamaz).
//
// Kanca (bu testin varsaydığı sözleşme; ekran yalnız okuma için açar): window.__tezgah.model = ModelKanca
//   hazir              ekran açıldı, model yüklendi ve ilk kare çizildi
//   arac()             etkin araç: "cizgi" | "daire" | "yay" | "olcu" | "ekstruzyon" | "delik" | null
//   dof()              köşedeki DOF sayacının gösterdiği sayı (son /eskiz/coz ya da /eskiz/surukle yanıtının dof'u)
//   durum(kimlik)      öğenin serbestlik rengi: "tam" | "eksik" | "fazla" (SPEC 17 freedom / redundant)
//   ogeler()           etkin eskizdeki profil öğelerinin kimlikleri
//   noktalar()         etkin eskizdeki nokta kimlikleri
//   nokta(kimlik)      noktanın gösterilen uv konumu (sunucu yanıtından), yoksa null
//   ekranPx(uv)        etkin eskiz düzlemindeki uv'nin sayfadaki (client) piksel konumu
//   kenarOrtasi(kimlik) çizginin orta noktasının sayfa pikseli (ölçü eklemek için tıklanacak yer)
//   hacim()            kanıt panelinde gösterilen hacim [mm³] (son PUT yanıtındaki rapordan); katı yoksa null
//   gecmisK()          geçmiş şeridinin konumu k (ilk k adım gösteriliyor)
//   adimSayisi()       modeldeki adım sayısı
//   agBayt()           sahnede gösterilen ağın geldiği GET /ag yanıtının bayt uzunluğu; ağ yoksa 0
//
// Testin dayandığı DOM işaretleri (data-testid):
//   duzlem-xy          "XY'de yeni eskiz" düğmesi (boş modelde eskiz başlatır)
//   eskiz-alani        eskizin çizildiği tuval / katman (fare olayları buraya)
//   dof-sayaci         köşedeki toplam DOF sayacı
//   olcu-girdi         ölçü / mesafe kutusu (D ya da E aracı açınca odaklanır; Enter uygular)
//   celiski-karti      çelişki kartı;  celiski-kisit  kartın her satırı, `data-kisit` = kısıt sırası (tıkla → kaldır)
//   kanit-hacim        kanıt panelindeki hacim değeri
//   parametre-tablosu  parametre tablosu; model-parametre  her parametrenin girdisi, `data-ad` = parametre adı
//   gecmis-seridi      geçmiş şeridi;   gecmis-dilim  her adım dilimi, `data-k` = o adımla biten k (1'den)
//   tezgaha-gonder     "Tezgah'a gönder" düğmesi
//   komut-cubugu       Ctrl K ile açılan komut çubuğu (SPEC 24)
//   islem              freze ekranının iş yığınındaki işlem (SPEC 24)
// Varsayımlar: eskiz düzleminin uv orijininde sabit bir referans noktası vardır; çizgi aracında tıklanan nokta
// SPEC 26 yakalama önerilerini (yatay / dikey / uç noktaya çakışık) kısıt olarak uygular. Böylece orijinden
// başlayıp kapanan eksenlere hizalı dikdörtgen yalnız iki boy ölçüsüyle tam tanımlı olur.

import { expect, test, type Page, type Response } from "@playwright/test";
import "../src/kanca";

type Uv = [number, number];

interface ModelKanca {
  hazir: boolean;
  arac(): string | null;
  dof(): number;
  durum(kimlik: string): "tam" | "eksik" | "fazla";
  ogeler(): string[];
  noktalar(): string[];
  nokta(kimlik: string): Uv | null;
  ekranPx(uv: Uv): Uv;
  kenarOrtasi(kimlik: string): Uv;
  hacim(): number | null;
  gecmisK(): number;
  adimSayisi(): number;
  agBayt(): number;
}

const ON = "/api/ekran/model";
const W = 40;
const H = 30;
const D = 10;

const BOS_MODEL = { sema: 1, ad: "e2e", parametreler: { genislik: "40" }, adimlar: [] as unknown[] };

async function modelHazir(page: Page): Promise<void> {
  await page.waitForFunction(
    () => ((window.__tezgah as Record<string, unknown> | undefined)?.model as { hazir?: boolean } | undefined)?.hazir === true,
    null,
    { timeout: 30_000 },
  );
}

async function kanca<T>(page: Page, f: (k: ModelKanca) => T): Promise<T> {
  return page.evaluate(
    (kod) => {
      const k = (window.__tezgah as unknown as { model: ModelKanca }).model;
      return new Function("k", `return (${kod})(k)`)(k);
    },
    f.toString(),
  ) as Promise<T>;
}

async function px(page: Page, uv: Uv): Promise<Uv> {
  return page.evaluate(
    (u) => (window.__tezgah as unknown as { model: ModelKanca }).model.ekranPx(u as Uv),
    uv,
  );
}

function cozumYaniti(r: Response): boolean {
  const u = r.url();
  return u.includes(`${ON}/eskiz/coz`) || u.includes(`${ON}/eskiz/surukle`);
}

async function sonCozum<T>(page: Page, eylem: () => Promise<T>): Promise<{ status: number; json: any }> {
  const bekle = page.waitForResponse(cozumYaniti);
  await eylem();
  const r = await bekle;
  return { status: r.status(), json: await r.json() };
}

async function sayac(page: Page): Promise<number> {
  const t = ((await page.getByTestId("dof-sayaci").textContent()) ?? "").match(/-?\d+/);
  expect(t, "DOF sayacında sayı olmalı").not.toBeNull();
  return Number(t![0]);
}

async function dofTutarli(page: Page, beklenen: number): Promise<void> {
  await expect.poll(() => kanca(page, (k) => k.dof())).toBe(beklenen);
  await expect.poll(() => sayac(page)).toBe(beklenen);
}

/** Orijinden başlayan W × H dikdörtgeni çizgi aracıyla çizer (beş tıklama, son tıklama ilk noktaya). */
async function dikdortgenCiz(page: Page): Promise<number> {
  await page.getByTestId("duzlem-xy").click();
  await page.getByTestId("eskiz-alani").hover();
  await page.keyboard.press("l");
  await expect.poll(() => kanca(page, (k) => k.arac())).toBe("cizgi");
  const koseler: Uv[] = [
    [0, 0],
    [W, 0],
    [W, H],
    [0, H],
    [0, 0],
  ];
  let dof = -1;
  for (const [i, uv] of koseler.entries()) {
    const [x, y] = await px(page, uv);
    if (i === 0) {
      await page.mouse.click(x, y);
      continue;
    }
    const c = await sonCozum(page, () => page.mouse.click(x, y));
    expect(c.status).toBe(200);
    dof = c.json.dof;
  }
  await page.keyboard.press("Escape");
  await expect.poll(() => kanca(page, (k) => k.arac())).toBeNull();
  return dof;
}

/** D aracıyla çizginin ortasına tıklar, değeri yazar, Enter. */
async function olcuEkle(page: Page, oge: string, deger: string): Promise<{ status: number; json: any }> {
  await page.getByTestId("eskiz-alani").hover();
  await page.keyboard.press("d");
  await expect.poll(() => kanca(page, (k) => k.arac())).toBe("olcu");
  const [x, y] = await page.evaluate(
    (o) => (window.__tezgah as unknown as { model: ModelKanca }).model.kenarOrtasi(o),
    oge,
  );
  await page.mouse.click(x, y);
  const girdi = page.getByTestId("olcu-girdi");
  await expect(girdi).toBeVisible();
  await girdi.fill(deger);
  const c = await sonCozum(page, () => girdi.press("Enter"));
  return c;
}

/** Noktanın başlangıçtaki uv'sine göre bir çizginin (alt / sağ / üst / sol) kimliği. */
async function cizgiBul(page: Page, a: Uv, b: Uv): Promise<string> {
  const ogeler = await kanca(page, (k) => k.ogeler());
  for (const o of ogeler) {
    const [x, y] = await page.evaluate((id) => (window.__tezgah as unknown as { model: ModelKanca }).model.kenarOrtasi(id), o);
    const [mx, my] = await px(page, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]);
    if (Math.hypot(x - mx, y - my) < 2) return o;
  }
  throw new Error(`çizgi bulunamadı: ${a} → ${b}`);
}

async function yatayKaydirmaYok(page: Page): Promise<void> {
  const [sw, cw] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(sw, "yatay kaydırma olmamalı").toBeLessThanOrEqual(cw);
}

async function putYaniti(page: Page, eylem: () => Promise<unknown>): Promise<any> {
  const bekle = page.waitForResponse((r) => r.url().endsWith(`${ON}/`) && r.request().method() === "PUT");
  await eylem();
  const r = await bekle;
  expect(r.status()).toBe(200);
  return r.json();
}

test.describe("Model ekranı uçtan uca @slow", () => {
  let hatalar: string[];

  test.beforeEach(async ({ page, request }) => {
    hatalar = [];
    page.on("console", (m) => {
      if (m.type() === "error") hatalar.push(m.text());
    });
    page.on("pageerror", (e) => hatalar.push(String(e)));
    expect((await request.post("/api/sifirla")).status()).toBe(200);
  });

  test.afterEach(() => {
    expect(hatalar, "konsolda hata olmamalı").toEqual([]);
  });

  test("K11 eskiz: DOF sayacı, renkler, çelişki kartı, sürükleme", async ({ page, request }) => {
    expect((await request.put(`${ON}/`, { data: BOS_MODEL })).status()).toBe(200);
    await page.goto("/#/model");
    await modelHazir(page);

    // Dikdörtgen: DOF sayacı sunucu yanıtıyla aynı
    const dof0 = await dikdortgenCiz(page);
    expect(dof0).toBe(2);
    await dofTutarli(page, dof0);
    const alt = await cizgiBul(page, [0, 0], [W, 0]);
    const sag = await cizgiBul(page, [W, 0], [W, H]);
    const ust = await cizgiBul(page, [W, H], [0, H]);
    const eksikOnce = await page.evaluate((o) => (window.__tezgah as unknown as { model: ModelKanca }).model.durum(o), sag);
    expect(eksikOnce).toBe("eksik");

    // Birinci ölçü (ifadeyle): DOF 1'e iner
    const c1 = await olcuEkle(page, alt, "=genislik");
    expect(c1.status).toBe(200);
    expect(c1.json.dof).toBe(1);
    await dofTutarli(page, 1);

    // Eksik tanımlı nokta sürüklenir: gösterilen konum son /surukle yanıtıyla aynı
    const serbest = c1.json.freedom as Record<string, number>;
    const noktalar = await kanca(page, (k) => k.noktalar());
    const surulen = noktalar.find((n) => (serbest[n] ?? 0) > 0);
    expect(surulen, "serbest nokta olmalı").toBeDefined();
    const p0 = (await page.evaluate((n) => (window.__tezgah as unknown as { model: ModelKanca }).model.nokta(n), surulen!)) as Uv;
    const [x0, y0] = await px(page, p0);
    const [x1, y1] = await px(page, [p0[0] + 3, p0[1] + 8]);
    const istekler: string[] = [];
    const say = (r: { url(): string }) => {
      if (r.url().includes(`${ON}/eskiz/surukle`)) istekler.push(r.url());
    };
    page.on("request", say);
    await page.mouse.move(x0, y0);
    await page.mouse.down();
    await page.mouse.move(x1, y1, { steps: 12 });
    const son = await sonCozum(page, () => page.mouse.up());
    page.off("request", say);
    expect(son.status).toBe(200);
    expect(istekler.length, "çerçeve başına en fazla bir sürükleme isteği").toBeLessThanOrEqual(13);
    const goster = (await page.evaluate((n) => (window.__tezgah as unknown as { model: ModelKanca }).model.nokta(n), surulen!)) as Uv;
    const beklenen = son.json.points[surulen!] as Uv;
    expect(Math.abs(goster[0] - beklenen[0])).toBeLessThanOrEqual(1e-9);
    expect(Math.abs(goster[1] - beklenen[1])).toBeLessThanOrEqual(1e-9);
    await dofTutarli(page, 1);

    // İkinci ölçü: tam tanımlı; her öğe "tam"
    const c2 = await olcuEkle(page, sag, String(H));
    expect(c2.status).toBe(200);
    await dofTutarli(page, 0);
    for (const o of await kanca(page, (k) => k.ogeler())) {
      expect(await page.evaluate((id) => (window.__tezgah as unknown as { model: ModelKanca }).model.durum(id), o)).toBe("tam");
    }

    // Çelişen ölçü: 422, kart SPEC 17 çelişki kümesini listeler; eskiz bozulmaz
    const c3 = await olcuEkle(page, ust, "45");
    expect(c3.status).toBe(422);
    const kisitlar = (c3.json.detail.kisitlar as number[]).slice().sort((a, b) => a - b);
    expect(kisitlar.length).toBeGreaterThan(0);
    const kart = page.getByTestId("celiski-karti");
    await expect(kart).toBeVisible();
    const satirlar = kart.getByTestId("celiski-kisit");
    await expect(satirlar).toHaveCount(kisitlar.length);
    const listelenen = (await satirlar.evaluateAll((e) => e.map((x) => Number((x as HTMLElement).dataset.kisit)))).sort(
      (a, b) => a - b,
    );
    expect(listelenen).toEqual(kisitlar);
    await dofTutarli(page, 0);

    // Biri kaldırılınca eskiz yeniden çözülür, DOF sayacı yanıtla tutarlı
    const c4 = await sonCozum(page, () => satirlar.first().click());
    expect(c4.status).toBe(200);
    await dofTutarli(page, c4.json.dof);
    await expect(kart).toBeHidden();
  });

  test("K11 model: ekstrüzyon hacmi, parametre, geçmiş şeridi, Ctrl Z, genişlik", async ({ page, request }) => {
    expect((await request.put(`${ON}/`, { data: BOS_MODEL })).status()).toBe(200);
    await page.goto("/#/model");
    await modelHazir(page);
    await dikdortgenCiz(page);
    await olcuEkle(page, await cizgiBul(page, [0, 0], [W, 0]), "=genislik");
    await olcuEkle(page, await cizgiBul(page, [W, 0], [W, H]), String(H));
    await dofTutarli(page, 0);

    // Ekstrüzyon 10 → kanıt panelinde gerçek hacim (sunucudan)
    await page.getByTestId("eskiz-alani").hover();
    const J = await putYaniti(page, async () => {
      await page.keyboard.press("e");
      await expect.poll(() => kanca(page, (k) => k.arac())).toBe("ekstruzyon");
      await page.getByTestId("olcu-girdi").fill(String(D));
      await page.getByTestId("olcu-girdi").press("Enter");
    });
    expect(J.rapor).toBeDefined();
    await expect.poll(() => kanca(page, (k) => k.hacim())).not.toBeNull();
    expect(Math.abs((await kanca(page, (k) => k.hacim()))! - W * H * D)).toBeLessThanOrEqual(W * H * D * 1e-6);
    await expect(page.getByTestId("kanit-hacim")).toBeVisible();

    // Parametre değişince model baştan kurulur, hacim güncellenir
    const girdi = page.getByTestId("parametre-tablosu").locator('[data-testid="model-parametre"][data-ad="genislik"]');
    await putYaniti(page, async () => {
      await girdi.fill("50");
      await girdi.press("Enter");
    });
    await expect.poll(async () => Math.abs(((await kanca(page, (k) => k.hacim())) ?? 0) - 50 * H * D)).toBeLessThanOrEqual(
      50 * H * D * 1e-6,
    );
    const n = await kanca(page, (k) => k.adimSayisi());
    expect(n).toBeGreaterThanOrEqual(2);

    // Geçmiş şeridi k. adıma: ağ GET /ag?k= ile aynı
    await page.getByTestId("gecmis-dilim").and(page.locator('[data-k="1"]')).click();
    await expect.poll(() => kanca(page, (k) => k.gecmisK())).toBe(1);
    await expect.poll(() => kanca(page, (k) => k.agBayt())).toBe(0); // yalnız eskiz: katı yok
    const agBekle = page.waitForResponse((r) => r.url().includes(`${ON}/ag`) && r.url().includes(`k=${n}`));
    await page.getByTestId("gecmis-dilim").and(page.locator(`[data-k="${n}"]`)).click();
    const ag = await agBekle;
    expect(ag.status()).toBe(200);
    const govde = await ag.body();
    const dogrudan = await (await request.get(`${ON}/ag?k=${n}`)).body();
    expect(govde.equals(dogrudan)).toBe(true);
    await expect.poll(() => kanca(page, (k) => k.agBayt())).toBe(govde.byteLength);

    // K12: Ctrl Z / Ctrl Shift Z şeritte konum değiştirir
    await page.locator("body").click({ position: { x: 1, y: 1 } });
    await page.keyboard.press("Control+z");
    await expect.poll(() => kanca(page, (k) => k.gecmisK())).toBe(n - 1);
    await page.keyboard.press("Control+Shift+z");
    await expect.poll(() => kanca(page, (k) => k.gecmisK())).toBe(n);

    for (const genislik of [400, 1440]) {
      await page.setViewportSize({ width: genislik, height: 900 });
      await yatayKaydirmaYok(page);
    }
  });

  test("K11 Tezgah'a gönder: freze ekranı cep işlemiyle açılır", async ({ page }) => {
    // /api/sifirla → örnek flanş modeli (ortada 8 mm kör cep)
    await page.goto("/#/model");
    await modelHazir(page);
    const bekle = page.waitForResponse((r) => r.url().endsWith(`${ON}/tezgaha-gonder`));
    await page.getByTestId("tezgaha-gonder").click();
    const r = await bekle;
    expect(r.status()).toBe(200);
    const is = await r.json();
    const anahtarlar = (is.islemler as { anahtar: string }[]).map((i) => i.anahtar);
    expect(anahtarlar).toContain("cep");
    await expect(page).toHaveURL(/#\/freze/);
    await expect(page.getByTestId("islem")).toHaveCount(anahtarlar.length);
    await expect(page.getByTestId("islem").nth(anahtarlar.indexOf("cep"))).toBeVisible();
  });

  test("K12 klavye: araç tuşları, Esc, Ctrl K, görünür odak", async ({ page }) => {
    await page.goto("/#/model");
    await modelHazir(page);
    await page.getByTestId("eskiz-alani").hover();
    const tuslar: [string, string][] = [
      ["l", "cizgi"],
      ["c", "daire"],
      ["a", "yay"],
      ["d", "olcu"],
      ["e", "ekstruzyon"],
      ["h", "delik"],
    ];
    for (const [tus, arac] of tuslar) {
      await page.keyboard.press(tus);
      await expect.poll(() => kanca(page, (k) => k.arac())).toBe(arac);
      await page.keyboard.press("Escape");
      await expect.poll(() => kanca(page, (k) => k.arac())).toBeNull();
    }

    await page.keyboard.press("Control+k");
    await expect(page.getByTestId("komut-cubugu")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("komut-cubugu")).toBeHidden();

    // Her etkileşimli öğenin görünür odak durumu var
    const ogeler = page.locator("body :is(button, input, select, [tabindex]:not([tabindex='-1']))");
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
  });
});
