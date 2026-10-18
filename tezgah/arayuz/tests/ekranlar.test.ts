// A3 K9 — ön yüz ekran kaydı (src/ekranlar/kayit.ts) ve ekran istemcisi (src/api.ts).
// Yalnız onaylı arayüz metnine (specs/24a-ekran-kaydi.md §2, §3, §5) dayanır; ekranlar uydurmadır.
// Sunucu ekranlarının hepsine sekme tuşu verilir: tuşsuz ekranların sekme kuralı bu testin konusu değil.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SunucuHatasi, degisiklikSonrasi, ekranApi, parametreGonder } from "../src/api";
import { ekranlariSirala, kisayolDogrula, modulleriDogrula } from "../src/ekranlar/kayit";
import { KABUK_KISAYOLLARI, type EkranModulu, type SunucuEkrani } from "../src/ekranlar/tip";

function modul(ad: string, tus?: string): EkranModulu {
  return {
    ad,
    baslik: ad.toUpperCase(),
    tus,
    ac: async () => {},
    kapat: () => {},
  };
}

function sunucu(ad: string, sira: number, tus: string, hazir = true, neden: string | null = null): SunucuEkrani {
  return { ad, baslik: ad.toUpperCase(), sira, tus, hazir, neden, bolum: null, bagimli: [] };
}

// ------------------------------------------------------------------ ekranlariSirala

describe("ekranlariSirala", () => {
  it("sunucunun sira'sı, eşitse ad", () => {
    const S = [sunucu("torna", 20, "2"), sunucu("montaj", 20, "3"), sunucu("freze", 10, "1"), sunucu("analiz", 5, "6")];
    const M = [modul("freze", "1"), modul("torna", "2"), modul("montaj", "3"), modul("analiz", "6")];
    expect(ekranlariSirala(S, M).map((s) => s.ad)).toEqual(["analiz", "freze", "montaj", "torna"]);
  });

  it("sıra ön yüz dizisinin ve sunucu dizisinin sırasından bağımsız", () => {
    const S = [sunucu("b", 1, "2"), sunucu("a", 1, "1"), sunucu("c", 0, "3")];
    const M = [modul("c", "3"), modul("a", "1"), modul("b", "2")];
    const beklenen = ["c", "a", "b"];
    expect(ekranlariSirala(S, M).map((s) => s.ad)).toEqual(beklenen);
    expect(ekranlariSirala([...S].reverse(), [...M].reverse()).map((s) => s.ad)).toEqual(beklenen);
  });

  it("sunucu ∩ ön yüz: ikisinde de olan açık sekme, modülü ve alanları dolu", () => {
    const m = modul("freze", "1");
    const [s] = ekranlariSirala([sunucu("freze", 10, "1")], [m]);
    expect(s.ad).toBe("freze");
    expect(s.baslik).toBe("FREZE");
    expect(s.tus).toBe("1");
    expect(s.acik).toBe(true);
    expect(s.neden).toBeNull();
    expect(s.modul).toBe(m);
  });

  it("ön yüzde olup sunucuda olmayan gösterilmez", () => {
    const T = ekranlariSirala([sunucu("freze", 10, "1")], [modul("freze", "1"), modul("hayalet", "9")]);
    expect(T.map((s) => s.ad)).toEqual(["freze"]);
  });

  it("sunucuda olup ön yüzü olmayan kapalı sekme, nedeni var", () => {
    const T = ekranlariSirala([sunucu("freze", 10, "1"), sunucu("torna", 20, "2")], [modul("freze", "1")]);
    expect(T.map((s) => s.ad)).toEqual(["freze", "torna"]);
    const torna = T[1];
    expect(torna.acik).toBe(false);
    expect(torna.modul).toBeNull();
    expect(typeof torna.neden).toBe("string");
    expect((torna.neden as string).length).toBeGreaterThan(0);
  });

  it("sunucuda hazır olmayan ekran kapalı sekme, ipucu sunucunun nedeni", () => {
    const T = ekranlariSirala(
      [sunucu("freze", 10, "1"), sunucu("analiz", 60, "6", false, "gmsh kurulu değil")],
      [modul("freze", "1"), modul("analiz", "6")],
    );
    expect(T.map((s) => [s.ad, s.acik])).toEqual([
      ["freze", true],
      ["analiz", false],
    ]);
    expect(T[1].neden).toBe("gmsh kurulu değil");
  });

  it("boş listeler", () => {
    expect(ekranlariSirala([], [])).toEqual([]);
    expect(ekranlariSirala([], [modul("freze", "1")])).toEqual([]);
  });
});

// ------------------------------------------------------------------ modulleriDogrula / kisayolDogrula

describe("modulleriDogrula", () => {
  it("geçerli modüller (tuşsuz dahil) hata vermez", () => {
    expect(() => modulleriDogrula([modul("freze", "1"), modul("torna", "2"), modul("kabuk")])).not.toThrow();
    expect(() => modulleriDogrula([])).not.toThrow();
  });

  it("çift ad → Error", () => {
    expect(() => modulleriDogrula([modul("freze", "1"), modul("freze", "2")])).toThrow(Error);
  });

  it("çift sekme tuşu → Error", () => {
    expect(() => modulleriDogrula([modul("freze", "1"), modul("torna", "1")])).toThrow(Error);
  });

  it.each(["a", "12", "Ctrl+K", "Ctrl+S", " "])("tek rakam olmayan tuş %j → Error", (tus) => {
    expect(() => modulleriDogrula([modul("freze", tus)])).toThrow(Error);
  });

  it.each(["1", "2", "5", "7", "9"])("tek rakam tuş %j geçerli", (tus) => {
    expect(() => modulleriDogrula([modul("freze", tus)])).not.toThrow();
  });
});

describe("kisayolDogrula", () => {
  it("kabuk kısayolları §3 ile aynı", () => {
    expect([...KABUK_KISAYOLLARI].sort()).toEqual(
      ["Ctrl+K", "Ctrl+Z", "Ctrl+Shift+Z", "Ctrl+Y", "Ctrl+S", "Ctrl+Shift+S", "Ctrl+O"].sort(),
    );
  });

  it.each([...KABUK_KISAYOLLARI])("kabuk kısayolu %s → Error", (k) => {
    expect(() => kisayolDogrula(k)).toThrow(Error);
  });

  it.each(["ctrl+k", "CTRL+S", "Ctrl+o", "Shift+Ctrl+Z", "shift+ctrl+s", "CTRL+SHIFT+Z"])(
    "büyük/küçük harf ve sıra farkı gözetilmez: %s → Error",
    (k) => {
      expect(() => kisayolDogrula(k)).toThrow(Error);
    },
  );

  it.each(["Ctrl+J", "L", "Ctrl+Shift+K", "Alt+Z", "Ctrl+Alt+Z", "Shift+S"])("ekrana serbest: %s", (k) => {
    expect(() => kisayolDogrula(k)).not.toThrow();
  });
});

// ------------------------------------------------------------------ api.ts: X-Tezgah-Etiket, degisiklikSonrasi

interface Cagri {
  yol: string;
  yontem: string;
  basliklar: Headers;
  govde: string | null;
}

let cagrilar: Cagri[];
let siradaki: () => Response;
let abonelikler: (() => void)[];

function jsonYanit(veri: unknown, durum = 200): Response {
  return new Response(JSON.stringify(veri), { status: durum, headers: { "Content-Type": "application/json" } });
}

async function kaydet(girdi: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const istek = new Request(new URL(String(girdi instanceof Request ? girdi.url : girdi), "http://127.0.0.1"), init);
  const kaynak = girdi instanceof Request ? girdi : istek;
  const basliklar = new Headers(kaynak.headers);
  if (init?.headers) new Headers(init.headers).forEach((v, k) => basliklar.set(k, v));
  cagrilar.push({
    yol: new URL(istek.url).pathname,
    yontem: (init?.method ?? kaynak.method ?? "GET").toUpperCase(),
    basliklar,
    govde: init?.body != null ? String(init.body) : null,
  });
  return siradaki();
}

/** Başlık değeri etikete karşılık gelir: düz ya da URI kodlanmış (başlıklar Latin-1 olmalı). */
function etiketCoz(deger: string | null): string | null {
  if (deger === null) return null;
  try {
    return decodeURIComponent(deger);
  } catch {
    return deger;
  }
}

function abone(cb: (etiket: string | null) => void): void {
  abonelikler.push(degisiklikSonrasi(cb));
}

beforeEach(() => {
  cagrilar = [];
  abonelikler = [];
  siradaki = () => jsonYanit({ tamam: true });
  vi.stubGlobal("fetch", vi.fn(kaydet));
});

afterEach(() => {
  for (const kaldir of abonelikler) kaldir();
  vi.unstubAllGlobals();
});

describe("ekranApi", () => {
  it("yollar /api/ekran/<ad>/ önekine göre", async () => {
    const api = ekranApi("freze");
    expect(await api.getJson("x")).toEqual({ tamam: true });
    await api.postJson("y/z", { a: 1 }, "deneme");
    expect(cagrilar.map((c) => [c.yontem, c.yol])).toEqual([
      ["GET", "/api/ekran/freze/x"],
      ["POST", "/api/ekran/freze/y/z"],
    ]);
    expect(JSON.parse(cagrilar[1].govde as string)).toEqual({ a: 1 });
  });

  it("iki ekranın aynı yolu ayrı öneklere gider", async () => {
    await ekranApi("torna").getJson("x");
    await ekranApi("montaj").getJson("x");
    expect(cagrilar.map((c) => c.yol)).toEqual(["/api/ekran/torna/x", "/api/ekran/montaj/x"]);
  });

  it("getIkili ArrayBuffer döner", async () => {
    siradaki = () => new Response(new Uint8Array([1, 2, 3, 4]), { status: 200 });
    const b = await ekranApi("freze").getIkili("veri");
    expect(b).toBeInstanceOf(ArrayBuffer);
    expect([...new Uint8Array(b)]).toEqual([1, 2, 3, 4]);
    expect(cagrilar[0].yol).toBe("/api/ekran/freze/veri");
  });

  it("postJson X-Tezgah-Etiket taşır; GET'ler taşımaz", async () => {
    const api = ekranApi("freze");
    const etiket = "Cep: D 10 → 8";
    await api.getJson("x");
    siradaki = () => new Response(new ArrayBuffer(8), { status: 200 });
    await api.getIkili("x");
    siradaki = () => jsonYanit({ tamam: true });
    await api.postJson("x", { D: 8 }, etiket);
    expect(cagrilar[0].basliklar.has("X-Tezgah-Etiket")).toBe(false);
    expect(cagrilar[1].basliklar.has("X-Tezgah-Etiket")).toBe(false);
    expect(cagrilar[2].basliklar.has("X-Tezgah-Etiket")).toBe(true);
    expect(etiketCoz(cagrilar[2].basliklar.get("X-Tezgah-Etiket"))).toBe(etiket);
  });

  it("parametreGonder (durum değiştiren istek) X-Tezgah-Etiket taşır", async () => {
    siradaki = () => jsonYanit({ sema: 1, is: {}, sure_farki: 0 });
    await parametreGonder("flans-plakasi", 2, "D", 8);
    expect(cagrilar[0].yontem).toBe("POST");
    expect(cagrilar[0].basliklar.has("X-Tezgah-Etiket")).toBe(true);
  });

  it.each([
    ["getJson", 422],
    ["postJson", 422],
    ["getJson", 503],
  ] as const)("%s %i → SunucuHatasi (detail metni)", async (yontem, durum) => {
    siradaki = () => jsonYanit({ detail: "takım çapı sıfır" }, durum);
    const api = ekranApi("freze");
    const p = yontem === "getJson" ? api.getJson("x") : api.postJson("x", {}, "e");
    await expect(p).rejects.toBeInstanceOf(SunucuHatasi);
    siradaki = () => jsonYanit({ detail: "takım çapı sıfır" }, durum);
    const p2 = yontem === "getJson" ? api.getJson("x") : api.postJson("x", {}, "e");
    await expect(p2).rejects.toMatchObject({ durum, message: "takım çapı sıfır" });
  });
});

describe("degisiklikSonrasi", () => {
  it("başarılı postJson'dan sonra bir kez, etiketle çağrılır", async () => {
    const cb = vi.fn();
    abone(cb);
    await ekranApi("freze").postJson("x", {}, "Cep: D 10 → 8");
    expect(cb).toHaveBeenCalledTimes(1);
    expect(cb).toHaveBeenCalledWith("Cep: D 10 → 8");
  });

  it("GET'lerden sonra çağrılmaz", async () => {
    const cb = vi.fn();
    abone(cb);
    await ekranApi("freze").getJson("x");
    siradaki = () => new Response(new ArrayBuffer(4), { status: 200 });
    await ekranApi("freze").getIkili("x");
    expect(cb).not.toHaveBeenCalled();
  });

  it("başarısız değiştiren istekten sonra çağrılmaz", async () => {
    const cb = vi.fn();
    abone(cb);
    siradaki = () => jsonYanit({ detail: "bozuk" }, 422);
    await expect(ekranApi("freze").postJson("x", {}, "e")).rejects.toBeInstanceOf(SunucuHatasi);
    siradaki = () => jsonYanit({ detail: "yok" }, 503);
    await expect(ekranApi("freze").postJson("x", {}, "e")).rejects.toBeInstanceOf(SunucuHatasi);
    expect(cb).not.toHaveBeenCalled();
  });

  it("çağrı yanıt geldikten sonra olur (istek sırasında değil)", async () => {
    const sira: string[] = [];
    abone(() => sira.push("cb"));
    siradaki = () => {
      sira.push("yanit");
      return jsonYanit({});
    };
    await ekranApi("freze").postJson("x", {}, "e");
    expect(sira).toEqual(["yanit", "cb"]);
  });

  it("başarılı parametreGonder'den sonra da çağrılır", async () => {
    const cb = vi.fn();
    abone(cb);
    siradaki = () => jsonYanit({ sema: 1, is: {}, sure_farki: 0 });
    await parametreGonder("flans-plakasi", 2, "D", 8);
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it("birden çok abone; dönen fonksiyon aboneliği kaldırır", async () => {
    const a = vi.fn();
    const b = vi.fn();
    const kaldirA = degisiklikSonrasi(a);
    abone(b);
    await ekranApi("freze").postJson("x", {}, "bir");
    kaldirA();
    await ekranApi("freze").postJson("x", {}, "iki");
    expect(a).toHaveBeenCalledTimes(1);
    expect(b).toHaveBeenCalledTimes(2);
    expect(b).toHaveBeenLastCalledWith("iki");
  });
});
