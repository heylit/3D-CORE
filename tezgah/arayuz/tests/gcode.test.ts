// SPEC 24 K7 — G-code satır vurgusu ve satır ↔ hareket eşlemesi (src/gcode.ts).

import { describe, expect, it } from "vitest";
import { hareketSatir, satirUcNoktasi, vurgula } from "../src/gcode";
import type { Hareket } from "../src/tipler";

/** Boşluk olmayan jetonlar: [tür, metin]. */
function anlamli(satir: string): [string, string][] {
  return vurgula(satir)
    .filter((j) => j.metin.trim() !== "")
    .map((j) => [j.tur, j.metin.trim()]);
}

describe("vurgula", () => {
  const ornekler = [
    "G1 X10.5 Y-2 F800",
    "N10 G0 Z5. (yorum burada) M3 S10000",
    "T2 M6",
    "G2 X50. Y30. I0. J5.",
    "G98 G83 X55. Y5. Z10. R21. Q4. F150.",
    "G0 G43 X10. Y20. Z25. H1",
    "  G3   K-1.5  ",
    "(sadece yorum)",
    "%",
    "",
  ];

  it("jeton metinleri art arda eklenince satırın kendisi", () => {
    for (const s of ornekler) {
      expect(vurgula(s).map((j) => j.metin).join("")).toBe(s);
    }
  });

  it("harf + sayı kelimelerinin türleri", () => {
    expect(anlamli("G1 X10.5 Y-2 F800")).toEqual([
      ["g", "G1"],
      ["eksen", "X10.5"],
      ["eksen", "Y-2"],
      ["ilerleme", "F800"],
    ]);
    expect(anlamli("N10 G0 Z5. M3 S10000 T2 H2")).toEqual([
      ["sayi", "N10"],
      ["g", "G0"],
      ["eksen", "Z5."],
      ["m", "M3"],
      ["devir", "S10000"],
      ["takim", "T2"],
      ["takim", "H2"],
    ]);
    expect(anlamli("G83 I1 J-1 K0 R21. Q4.").map((j) => j[0])).toEqual([
      "g",
      "eksen",
      "eksen",
      "eksen",
      "eksen",
      "eksen",
    ]);
  });

  it("parantezli yorum tek yorum jetonu", () => {
    const j = vurgula("G0 Z5. (yorum burada) M3").filter((x) => x.tur === "yorum");
    expect(j.map((x) => x.metin)).toEqual(["(yorum burada)"]);
    expect(vurgula("(sadece yorum)").filter((x) => x.tur === "yorum").map((x) => x.metin)).toEqual([
      "(sadece yorum)",
    ]);
  });

  it("boşluklar diger jetonudur", () => {
    for (const j of vurgula("  G3   K-1.5  ")) {
      if (j.metin.trim() === "") expect(j.tur).toBe("diger");
    }
  });
});

describe("hareketSatir", () => {
  it("satir_hareket'in tersi", () => {
    const SH: ([number, number] | null)[] = [null, [0, 1], null, [2, 2], [3, 5]];
    const H = hareketSatir(SH, 6);
    expect(H).toBeInstanceOf(Int32Array);
    expect(Array.from(H)).toEqual([1, 1, 3, 4, 4, 4]);
  });

  it("hiçbir satırın üretmediği hareket → −1", () => {
    expect(Array.from(hareketSatir([[0, 0], null, [2, 3]], 5))).toEqual([0, -1, 2, 2, -1]);
    expect(Array.from(hareketSatir([null, null], 3))).toEqual([-1, -1, -1]);
    expect(hareketSatir([], 0).length).toBe(0);
  });

  it("tersin tersi: her aralıktaki hareket kendi satırına döner", () => {
    const SH: ([number, number] | null)[] = [null, [0, 3], [4, 4], null, null, [5, 9], [10, 10]];
    const H = hareketSatir(SH, 11);
    SH.forEach((ar, i) => {
      if (ar === null) return;
      for (let k = ar[0]; k <= ar[1]; k++) expect(H[k]).toBe(i);
    });
  });

  it("çakışan ya da taşan aralık → Error", () => {
    expect(() => hareketSatir([[0, 2], [2, 3]], 4)).toThrow();
    expect(() => hareketSatir([[0, 6]], 6)).toThrow();
    expect(() => hareketSatir([[-1, 0]], 6)).toThrow();
  });
});

describe("satirUcNoktasi", () => {
  const h = (b: [number, number, number], satir: number): Hareket => ({
    g: 1,
    a: [0, 0, 0],
    b,
    F: 500,
    satir,
    islem: 0,
  });
  const H: Hareket[] = [h([1, 0, 0], 1), h([2, 0, 0], 1), h([2, 3, 0], 3), h([2, 3, -1], 4), h([5, 5, 5], 4)];
  const SH: ([number, number] | null)[] = [null, [0, 1], null, [2, 2], [3, 4]];

  it("aralığın son hareketinin b'si", () => {
    expect(satirUcNoktasi(1, SH, H)).toEqual([2, 0, 0]);
    expect(satirUcNoktasi(3, SH, H)).toEqual([2, 3, 0]);
    expect(satirUcNoktasi(4, SH, H)).toEqual([5, 5, 5]);
  });

  it("hareket üretmeyen satır → null", () => {
    expect(satirUcNoktasi(0, SH, H)).toBeNull();
    expect(satirUcNoktasi(2, SH, H)).toBeNull();
  });
});
