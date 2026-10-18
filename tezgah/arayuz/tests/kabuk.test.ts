// SPEC 37 K15 — komut paleti eşleştirmesi (src/ekranlar/kabuk_ara.ts) ve rozet metni (src/ekranlar/kabuk.ts).
// Testler yalnız specs/37-proje-kabuk.md "Komut paleti eşleştirmesi" bölümünden yazıldı; gövdeler okunmadı.
// Puan basamakları: (1) başlık sorguyla başlar, (2) sorgu bir kelime başında başlıyor, (3) sorgu bitişik geçiyor,
// (4) alt dizi. Örnekler iki okumada da (kelime başı = bitişik ya da alt dizinin ilk harfi) aynı sırayı verecek
// biçimde seçildi. `son` listesi komut kimliklerini taşır; örneklerde kimlik = başlık.

import { describe, expect, it } from "vitest";
import { rozetMetni, type EtkiSatiri } from "../src/ekranlar/kabuk";
import { desenSayisi, eslestir, katla } from "../src/ekranlar/kabuk_ara";
import type { Komut } from "../src/ekranlar/tip";

function k(baslik: string, ek: Partial<Komut> = {}): Komut {
  return { kimlik: baslik, baslik, calistir: () => undefined, ...ek };
}

function basliklar(sorgu: string, komutlar: Komut[], son: string[] = []): string[] {
  return eslestir(sorgu, komutlar, son).map((x) => x.baslik);
}

describe("katla", () => {
  it("Türkçe küçük harf ve aksan tablosu", () => {
    expect(katla("İŞLEM")).toBe("islem");
    expect(katla("ışık")).toBe("isik");
    expect(katla("Çap")).toBe("cap");
    expect(katla("IŞIK")).toBe("isik"); // tr: I → ı → i
    expect(katla("Ğüöç")).toBe("guoc");
    expect(katla("âîû")).toBe("aiu");
    expect(katla("Sıfırla")).toBe("sifirla");
    expect(katla("L 9.5")).toBe("l 9.5");
  });
});

describe("eslestir", () => {
  it("katlanmış alt dizi eşleşmesi; eşleşmeyen elenir", () => {
    const komutlar = [k("Sıfırla"), k("Kaydet"), k("Geri al")];
    expect(basliklar("sifirla", komutlar)).toEqual(["Sıfırla"]);
    expect(basliklar("SIFIR", komutlar)).toEqual(["Sıfırla"]);
    expect(basliklar("xyz", komutlar)).toEqual([]);
    // harfler sırayla bulunmalı
    expect(basliklar("tedyak", komutlar)).toEqual([]);
  });

  it("anahtar kelimeler de aranır", () => {
    const komutlar = [k("Geri al", { anahtar_kelimeler: ["undo"] }), k("Kaydet")];
    expect(basliklar("undo", komutlar)).toEqual(["Geri al"]);
  });

  it("(1) başlık sorguyla başlar > (2) kelime başı", () => {
    expect(basliklar("kay", [k("Farklı kaydet"), k("Kaydet")])).toEqual(["Kaydet", "Farklı kaydet"]);
  });

  it("(2) kelime başı > (3) bitişik", () => {
    expect(basliklar("sim", [k("Asimetri"), k("Torna sim")])).toEqual(["Torna sim", "Asimetri"]);
  });

  it("(3) bitişik > (4) alt dizi", () => {
    expect(basliklar("cep", [k("Akçe kapı"), k("Recep")])).toEqual(["Recep", "Akçe kapı"]);
  });

  it("dört basamak birlikte", () => {
    const komutlar = [k("Akçe kapı"), k("Recep"), k("Yeni cep"), k("Cep aç")];
    expect(basliklar("cep", komutlar)).toEqual(["Cep aç", "Yeni cep", "Recep", "Akçe kapı"]);
  });

  it("eşitlikte daha kısa toplam boşluk önce", () => {
    expect(basliklar("cep", [k("xcexxxp"), k("xcxexp")])).toEqual(["xcxexp", "xcexxxp"]);
  });

  it("eşitlikte son kullanılan önce, sonra başlık alfabetik", () => {
    const komutlar = [k("Torna ayari"), k("Freze ayari")];
    expect(basliklar("ayar", komutlar)).toEqual(["Freze ayari", "Torna ayari"]);
    expect(basliklar("ayar", komutlar, ["Torna ayari"])).toEqual(["Torna ayari", "Freze ayari"]);
    const uc = [k("Cc ayar"), k("Bb ayar"), k("Aa ayar")];
    expect(basliklar("ayar", uc, ["Cc ayar", "Bb ayar"])).toEqual(["Cc ayar", "Bb ayar", "Aa ayar"]);
  });

  it("boş sorgu: önce son (en fazla 8, sırasıyla), sonra kalanlar alfabetik", () => {
    const adlar = ["k01", "k02", "k03", "k04", "k05", "k06", "k07", "k08", "k09", "k10", "k11", "k12"];
    const komutlar = adlar.map((a) => k(a));
    const son = ["k10", "k03", "k12", "k01", "k05", "k07", "k09", "k02", "k11", "k04"];
    expect(basliklar("", komutlar, son)).toEqual([
      "k10", "k03", "k12", "k01", "k05", "k07", "k09", "k02",
      "k04", "k06", "k08", "k11",
    ]);
    expect(basliklar("", [k("b"), k("c"), k("a")])).toEqual(["a", "b", "c"]);
  });

  it("parametreli komut: desene uyan sorgu komutu ilk sıraya çıkarır", () => {
    const komutlar = [k("Ladin"), k("Kaydet"), k("Mil boyu", { desen: "L <sayı>" })];
    expect(basliklar("L 9.5", komutlar)[0]).toBe("Mil boyu");
    expect(basliklar("l 9,5", komutlar)[0]).toBe("Mil boyu");
    const paso = [k("Paso ayarı"), k("Freze paso", { desen: "paso <sayı>" })];
    expect(basliklar("paso 2", paso)[0]).toBe("Freze paso");
  });
});

describe("desenSayisi", () => {
  const D = "L <sayı>";
  it("nokta ya da virgül ondalık ayırıcı", () => {
    expect(desenSayisi(D, "L 9.5")).toBe(9.5);
    expect(desenSayisi(D, "l 9,5")).toBe(9.5);
    expect(desenSayisi(D, "L 20")).toBe(20);
    expect(desenSayisi("genişlik <sayı>", "GENISLIK 110")).toBe(110);
  });
  it("geçersiz: sayı değil, fazladan metin, nan, inf, boş, desene uymayan", () => {
    for (const s of ["L abc", "L 9.5x", "L nan", "L NaN", "L inf", "L Infinity", "L", "L ", "D 9.5", "9.5", ""]) {
      expect(desenSayisi(D, s), s).toBeNull();
    }
  });
});

describe("rozetMetni", () => {
  it("ekranın ozet sırasındaki ilk sayısal farkı işaretiyle gösterir", () => {
    const satir: EtkiSatiri = {
      bolum: "torna_isleri",
      ekran: "torna",
      once: { durum: "tamam", sure_s: 60.0, gcode_satir: 212 },
      sonra: { durum: "tamam", sure_s: 55.8, gcode_satir: 208 },
      fark: { sure_s: -4.2, gcode_satir: -4 },
    };
    const m = rozetMetni(satir);
    expect(m).not.toBeNull();
    expect(m as string).toMatch(/4[.,]2/);
    expect(m as string).toMatch(/[−-]/);
  });
  it("sayısal fark yoksa null", () => {
    const satir: EtkiSatiri = { bolum: "b", ekran: "e", once: { d: "a" }, sonra: { d: "b" }, fark: {} };
    expect(rozetMetni(satir)).toBeNull();
  });
});
