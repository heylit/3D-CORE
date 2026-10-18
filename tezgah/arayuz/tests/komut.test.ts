// SPEC 62 K9 (birinci aşama) — komut ekranı (src/ekranlar/komut.ts) ve sarma ikilisi çözücüsü (src/sarma.ts).
// Palet kancası (paletAc / paletKapat / paletAcik, varsayılan dışa aktarım yok) DOM ister; burada sınanmaz.
// Yalnız onaylı SPEC 62 metnine ve iskeletin arayüz açıklamalarına dayanır; uygulama gövdeleri okunmadı.
// /sarma ikilisi SPEC 24 sim_ikili biçimindedir (tezgah/kopru.py); sarmaCoz(veri, k) k anındaki yüzeyi çözer.
// SarmaOnbellek(getir, boyut) sözleşmesi metinde tanımlı olmadığı için burada sınanmaz.

import { describe, expect, it } from "vitest";
import { komutSuz, yanitGecerliMi } from "../src/ekranlar/komut";
import type { Komut } from "../src/ekranlar/tip";
import { sarmaCoz } from "../src/sarma";

// ------------------------------------------------------------------ yanitGecerliMi

describe("yanitGecerliMi", () => {
  it("en son gönderilen isteğin yanıtı kullanılır", () => {
    expect(yanitGecerliMi(1, 1)).toBe(true);
    expect(yanitGecerliMi(7, 7)).toBe(true);
  });

  it("eski sıra numaralı (uçuşta kalmış) yanıt atılır", () => {
    expect(yanitGecerliMi(1, 2)).toBe(false);
    expect(yanitGecerliMi(6, 7)).toBe(false);
    expect(yanitGecerliMi(0, 100)).toBe(false);
  });

  it("yalnız eşitse true", () => {
    expect(yanitGecerliMi(8, 7)).toBe(false);
  });

  it("sıra dışı gelen yanıtlar: yalnız sonuncusu geçerli", () => {
    // 1, 2, 3 gönderildi; yanıtlar 3, 1, 2 sırasıyla geldi.
    const son = 3;
    expect([3, 1, 2].map((s) => yanitGecerliMi(s, son))).toEqual([true, false, false]);
  });
});

// ------------------------------------------------------------------ komutSuz

function komut(kimlik: string, baslik: string, anahtar_kelimeler?: string[]): Komut {
  return { kimlik, baslik, anahtar_kelimeler, calistir: () => {} };
}

describe("komutSuz", () => {
  const K = [komut("delik", "Delik aç", ["matkap", "Ø"]), komut("cep", "Cep işle"), komut("izgara", "Işık ızgarası")];
  const ad = (m: string) => komutSuz(K, m).map((k) => k.kimlik);

  it("başlıkta arar, büyük/küçük harf duyarsız (Türkçe)", () => {
    expect(ad("delik")).toEqual(["delik"]);
    expect(ad("DELİK")).toEqual(["delik"]);
    expect(ad("IŞIK")).toEqual(["izgara"]); // I → ı
    expect(ad("İŞLE")).toEqual(["cep"]); // İ → i
  });

  it("anahtar sözcükte arar", () => {
    expect(ad("matkap")).toEqual(["delik"]);
  });

  it("eşleşme yoksa boş", () => {
    expect(ad("torna")).toEqual([]);
  });
});

// ------------------------------------------------------------------ sarmaCoz

/** SPEC 24 sim_ikili biçimi, little-endian; bloklar 8 baytın katına sıfırla tamamlanır. */
function simIkili(
  nx: number,
  ny: number,
  izgara: number[],
  olaylar: { hucre: number; k: number; z: number }[],
): ArrayBuffer {
  const sirali = [...olaylar].sort((a, b) => a.hucre - b.hucre || a.k - b.k);
  const m = sirali.length;
  const pad = (n: number) => Math.ceil(n / 8) * 8;
  const boylar = [16, 48, pad(4 * (nx * ny + 1)), pad(4 * m), pad(4 * m), pad(2 * m)];
  const buf = new ArrayBuffer(boylar.reduce((a, b) => a + b, 0));
  const dv = new DataView(buf);
  [1, nx, ny, m].forEach((v, i) => dv.setUint32(4 * i, v, true));
  izgara.forEach((v, i) => dv.setFloat64(16 + 8 * i, v, true));
  let o = 64;
  let say = 0;
  for (let c = 0; c <= nx * ny; c++) {
    dv.setUint32(o + 4 * c, say, true);
    say += sirali.filter((e) => e.hucre === c).length;
  }
  o += boylar[2];
  sirali.forEach((e, i) => dv.setInt32(o + 4 * i, e.k, true));
  o += boylar[3];
  sirali.forEach((e, i) => dv.setFloat32(o + 4 * i, e.z, true));
  o += boylar[4];
  sirali.forEach((_, i) => dv.setInt16(o + 2 * i, 0, true));
  return buf;
}

describe("sarmaCoz", () => {
  // nx = 3, ny = 2; z_ust = 20. Hücre 0: k=2 → 15, k=5 → 10; hücre 4: k=3 → 12.5; diğerleri olaysız.
  const izgara = [-1.5, 2.25, 0.5, 0.75, 20.0, -19.5];
  const veri = simIkili(3, 2, izgara, [
    { hucre: 0, k: 5, z: 10 },
    { hucre: 4, k: 3, z: 12.5 },
    { hucre: 0, k: 2, z: 15 },
  ]);

  it("başlık ve ızgara", () => {
    const s = sarmaCoz(veri, 0);
    expect(s.nx).toBe(3);
    expect(s.ny).toBe(2);
    expect(s.k).toBe(0);
    expect(s.izgara).toBeInstanceOf(Float64Array);
    expect(Array.from(s.izgara)).toEqual(izgara);
    expect(s.z).toBeInstanceOf(Float32Array);
    expect(s.z.length).toBe(6);
  });

  it("k anındaki yüzey: her hücrede k'si ≤ k olan son olay, yoksa z_ust", () => {
    expect(Array.from(sarmaCoz(veri, 0).z)).toEqual([20, 20, 20, 20, 20, 20]);
    expect(Array.from(sarmaCoz(veri, 2).z)).toEqual([15, 20, 20, 20, 20, 20]);
    expect(Array.from(sarmaCoz(veri, 3).z)).toEqual([15, 20, 20, 20, 12.5, 20]);
    expect(Array.from(sarmaCoz(veri, 4).z)).toEqual([15, 20, 20, 20, 12.5, 20]);
    expect(Array.from(sarmaCoz(veri, 5).z)).toEqual([10, 20, 20, 20, 12.5, 20]);
    expect(Array.from(sarmaCoz(veri, 99).z)).toEqual([10, 20, 20, 20, 12.5, 20]);
  });

  it("geri sarma ileri sarmayla aynı yüzeyi verir", () => {
    const ileri = Array.from(sarmaCoz(veri, 3).z);
    sarmaCoz(veri, 5);
    expect(Array.from(sarmaCoz(veri, 3).z)).toEqual(ileri);
  });
});
