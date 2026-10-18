// SPEC 24 — G-code satır vurgusu ve satır ↔ hareket eşlemesi. Saf fonksiyonlar (K7).

import type { Hareket, Nokta3 } from "./tipler";

export type JetonTuru = "g" | "m" | "eksen" | "ilerleme" | "devir" | "takim" | "sayi" | "yorum" | "diger";

export interface Jeton {
  tur: JetonTuru;
  metin: string;
}

/**
 * Bir G-code satırını vurgu jetonlarına böler. Jetonların metinleri art arda eklenince satırın kendisi
 * (boşluklar dahil, `diger` jetonu olarak) çıkar. Parantezli yorum tek `yorum` jetonudur.
 * Harf + sayı kelimeleri: G → g, M → m, X/Y/Z/I/J/K/R/Q → eksen, F → ilerleme, S → devir, T/H → takim,
 * N → sayi.
 */
export function vurgula(satir: string): Jeton[] {
  void satir;
  throw new Error("SPEC 24: uygulanmadı");
}

/**
 * satir_hareket'in tersi: hareket indeksi → onu üreten G-code satırı (yoksa −1). Uzunluk nHareket.
 * Aralıklar çakışırsa ya da nHareket dışına taşarsa Error.
 */
export function hareketSatir(satirHareket: ([number, number] | null)[], nHareket: number): Int32Array {
  void satirHareket;
  void nHareket;
  throw new Error("SPEC 24: uygulanmadı");
}

/** G-code satırının uç noktası: satir_hareket aralığının son hareketinin `b`'si; hareket yoksa null. */
export function satirUcNoktasi(
  satir: number,
  satirHareket: ([number, number] | null)[],
  hareketler: Hareket[],
): Nokta3 | null {
  void satir;
  void satirHareket;
  void hareketler;
  throw new Error("SPEC 24: uygulanmadı");
}
