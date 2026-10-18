// SPEC 54 K11 — hata kartı ve kurtarma iletişim kutusunun saf modelleri (src/ekranlar/kabuk.ts).
// Testler yalnız specs/54-saglamlik.md "Ön yüz" bölümünden ve iskelet imzalarından yazıldı; gövdeler okunmadı.

import { describe, expect, it } from "vitest";
import {
  hataKartiModeli,
  kurtarmaSecenekleri,
  type HataKarti,
  type KurtarmaBilgisi,
} from "../src/ekranlar/kabuk";

const KART: HataKarti = {
  sinif: "GeometryError",
  nesne: "yatak.step / gövde",
  ne_oldu: "fillet yapılamadı (r = 8 mm)",
  oneri: "yarıçapı 5 mm'nin altına indirin",
  teknik: "Traceback (most recent call last):\n  ...",
};

function bilgi(ek: Partial<KurtarmaBilgisi> = {}): KurtarmaBilgisi {
  return { yol: "/is/.yatak.3dc.kurtarma", okunur: true, kaynak_tutuyor: true, farkli: true, neden: null, ...ek };
}

describe("hataKartiModeli", () => {
  it("başlık ne_oldu; nesne, öneri ve teknik aynen", () => {
    expect(hataKartiModeli(KART, "L 9.5 → 9.0")).toEqual({
      baslik: "fillet yapılamadı (r = 8 mm)",
      nesne: "yatak.step / gövde",
      oneri: "yarıçapı 5 mm'nin altına indirin",
      teknik: KART.teknik,
      geriAl: true,
    });
  });

  it("geri alınacak değişiklik yoksa düğme yok", () => {
    expect(hataKartiModeli(KART, null).geriAl).toBe(false);
  });

  it("boş etiket de bir değişikliktir (null değil)", () => {
    expect(hataKartiModeli(KART, "").geriAl).toBe(true);
  });

  it("iç hata kartı", () => {
    const ic: HataKarti = {
      sinif: "IcHata",
      nesne: "/api/proje/degistir",
      ne_oldu: "beklenmeyen hata",
      oneri: "son değişikliği geri alın; hata kaydı /ev/.gunluk/hatalar.log içinde",
      teknik: "ZeroDivisionError",
    };
    const m = hataKartiModeli(ic, null);
    expect(m.baslik).toBe("beklenmeyen hata");
    expect(m.nesne).toBe("/api/proje/degistir");
    expect(m.geriAl).toBe(false);
  });
});

describe("kurtarmaSecenekleri", () => {
  it("sıra Kurtar / Yok say / İkisini de aç; kaynak tutuyorsa varsayılan kurtar", () => {
    const s = kurtarmaSecenekleri(bilgi());
    expect(s.map((x) => x.secim)).toEqual(["kurtar", "yoksay", "ikisi"]);
    expect(s.map((x) => x.etiket)).toEqual(["Kurtar", "Yok say", "İkisini de aç"]);
    expect(s.filter((x) => x.varsayilan).map((x) => x.secim)).toEqual(["kurtar"]);
  });

  it("kaynak tutmuyorsa varsayılan ikisi", () => {
    const s = kurtarmaSecenekleri(bilgi({ kaynak_tutuyor: false }));
    expect(s.map((x) => x.secim)).toEqual(["kurtar", "yoksay", "ikisi"]);
    expect(s.filter((x) => x.varsayilan).map((x) => x.secim)).toEqual(["ikisi"]);
  });
});
