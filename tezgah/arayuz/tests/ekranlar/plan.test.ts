// SPEC 47 K23 (plan kısmı) — Plan ekranının saf yardımcıları (src/ekranlar/plan_yardim.ts).
// Gerekçe / not kodları SPEC 29 §1 tablosundan; fark rozeti işaretleri yalnız sunucu sayısının işaretidir.

import { describe, expect, it } from "vitest";
import { type Fark, farkRozetleri, gerekceMetni, ozellikSirala } from "../../src/ekranlar/plan_yardim";

const GEREKCE_KODLARI = [
  "kesme_verisi_yok",
  "takim_yok",
  "takim_sigmiyor",
  "kesici_boy_yetmez",
  "ustten_erisilemez",
  "havsa_takimi_yok",
  "kilavuz_cevrimi_yok",
  "baglama_carpismasi",
  "on_delik_yok",
  "genel_girinti",
];
const NOT_KODLARI = ["kose_artigi", "yan_paso_kisildi", "delik_tasma_kisildi", "ikinci_baglama"];

function bosFark(): Fark {
  return {
    eklenen: [],
    cikan: [],
    takimi_degisen: [],
    yeni_planlanamayan: [],
    kurtulan: [],
    sure_farki: 0,
    takim_degisimi_farki: 0,
  };
}

describe("gerekceMetni", () => {
  it("SPEC 29 §1'deki 10 gerekçe kodunun hepsini kapsar, metinler farklı ve boş değil", () => {
    expect(GEREKCE_KODLARI).toHaveLength(10);
    const metinler = GEREKCE_KODLARI.map((k) => gerekceMetni(k));
    for (const [i, m] of metinler.entries()) {
      expect(typeof m).toBe("string");
      expect(m.trim().length).toBeGreaterThan(0);
      expect(m).not.toBe(GEREKCE_KODLARI[i]);
    }
    expect(new Set(metinler).size).toBe(10);
  });

  it("not kodlarının da metni var", () => {
    for (const k of NOT_KODLARI) {
      const m = gerekceMetni(k);
      expect(m.trim().length).toBeGreaterThan(0);
      expect(m).not.toBe(k);
    }
  });

  it("bilinmeyen kod → Error (sessiz varsayılan yok)", () => {
    expect(() => gerekceMetni("boyle_kod_yok")).toThrow();
    expect(() => gerekceMetni("")).toThrow();
  });
});

describe("farkRozetleri", () => {
  const tur = (r: ReturnType<typeof farkRozetleri>, t: string) => r.filter((x) => x.tur === t);

  it("eklenen +, çıkan −, takımı değişen ~", () => {
    const f: Fark = {
      ...bosFark(),
      eklenen: ["04-delik-T14"],
      cikan: ["03-cep_kalan-T2", "05-lamba-T3"],
      takimi_degisen: [{ adres: "pockets[0]", once: 1, sonra: 2 }],
    };
    const r = farkRozetleri(f);
    expect(tur(r, "eklendi").length).toBeGreaterThan(0);
    expect(tur(r, "eklendi").every((x) => x.isaret === "+")).toBe(true);
    expect(tur(r, "cikti").length).toBeGreaterThan(0);
    expect(tur(r, "cikti").every((x) => x.isaret === "−")).toBe(true);
    expect(tur(r, "takim").length).toBeGreaterThan(0);
    expect(tur(r, "takim").every((x) => x.isaret === "~")).toBe(true);
    expect(tur(r, "planlanamadi")).toHaveLength(0);
    expect(tur(r, "kurtuldu")).toHaveLength(0);
  });

  it("planlanamayana düşen ve kurtulan özellikler rozet alır", () => {
    const f: Fark = {
      ...bosFark(),
      yeni_planlanamayan: [{ adres: "pockets[1]", kod: "takim_sigmiyor" }],
      kurtulan: ["holes[2]"],
    };
    const r = farkRozetleri(f);
    expect(tur(r, "planlanamadi").length).toBeGreaterThan(0);
    expect(tur(r, "kurtuldu").length).toBeGreaterThan(0);
    for (const x of r) expect(["+", "−", "~", "0"]).toContain(x.isaret);
  });

  it("süre ve takım değişimi farkı: işaret sayının işaretidir", () => {
    const art = farkRozetleri({ ...bosFark(), sure_farki: 12.5, takim_degisimi_farki: 2 });
    expect(tur(art, "sure").map((x) => x.isaret)).toEqual(["+"]);
    expect(tur(art, "takim_degisimi").map((x) => x.isaret)).toEqual(["+"]);
    const az = farkRozetleri({ ...bosFark(), sure_farki: -0.25, takim_degisimi_farki: -1 });
    expect(tur(az, "sure").map((x) => x.isaret)).toEqual(["−"]);
    expect(tur(az, "takim_degisimi").map((x) => x.isaret)).toEqual(["−"]);
  });

  it("boş fark: değişiklik rozeti yok, sayı rozetleri (varsa) 0", () => {
    const r = farkRozetleri(bosFark());
    for (const t of ["eklendi", "cikti", "takim", "planlanamadi", "kurtuldu"]) expect(tur(r, t)).toHaveLength(0);
    for (const x of [...tur(r, "sure"), ...tur(r, "takim_degisimi")]) expect(x.isaret).toBe("0");
  });

  it("girdi değişmez ve her rozetin metni var", () => {
    const f: Fark = {
      ...bosFark(),
      eklenen: ["a"],
      cikan: ["b"],
      takimi_degisen: [{ adres: "faces[0]", once: 1, sonra: 2 }],
      sure_farki: 3,
    };
    const kopya = JSON.parse(JSON.stringify(f));
    const r = farkRozetleri(f);
    expect(f).toEqual(kopya);
    for (const x of r) expect(x.metin.trim().length).toBeGreaterThan(0);
  });
});

describe("ozellikSirala", () => {
  const satirlar = [
    { adres: "faces[0]", durum: "planlandi" },
    { adres: "pockets[0]", durum: "planlandi" },
    { adres: "holes[3]", durum: "planlanamadi" },
    { adres: "holes[0]", durum: "planlandi" },
    { adres: "holes[1]", durum: "planlanamadi" },
    { adres: "holes[2]", durum: "planlandi" },
  ];

  it("önce planlanamayanlar, sonra kalanlar; her grupta sunucu sırası korunur", () => {
    expect(ozellikSirala(satirlar).map((s) => s.adres)).toEqual([
      "holes[3]",
      "holes[1]",
      "faces[0]",
      "pockets[0]",
      "holes[0]",
      "holes[2]",
    ]);
  });

  it("girdi dizisi değişmez; satır nesneleri aynı (ek alanlar korunur)", () => {
    const girdi = satirlar.map((s, i) => ({ ...s, i }));
    const once = girdi.map((s) => s.adres);
    const sonuc = ozellikSirala(girdi);
    expect(girdi.map((s) => s.adres)).toEqual(once);
    expect(sonuc).toHaveLength(girdi.length);
    expect(sonuc[0]).toBe(girdi[2]);
    expect(sonuc.map((s) => s.i)).toEqual([2, 4, 0, 1, 3, 5]);
  });

  it("hepsi planlandı ya da boş liste", () => {
    const hepsi = satirlar.filter((s) => s.durum === "planlandi");
    expect(ozellikSirala(hepsi)).toEqual(hepsi);
    expect(ozellikSirala([])).toEqual([]);
  });
});
