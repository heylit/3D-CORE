// SPEC 24 — G-code satır vurgusu ve satır ↔ hareket eşlemesi. Saf fonksiyonlar (K7).

import type { Hareket, Nokta3 } from "./tipler";

export type JetonTuru = "g" | "m" | "eksen" | "ilerleme" | "devir" | "takim" | "sayi" | "yorum" | "diger";

export interface Jeton {
  tur: JetonTuru;
  metin: string;
}

const HARF: Record<string, JetonTuru> = {
  G: "g",
  M: "m",
  X: "eksen",
  Y: "eksen",
  Z: "eksen",
  I: "eksen",
  J: "eksen",
  K: "eksen",
  R: "eksen",
  Q: "eksen",
  F: "ilerleme",
  S: "devir",
  T: "takim",
  H: "takim",
  N: "sayi",
};

// parantezli yorum | harf + sayı kelimesi | diğer her şey (boşluklar dahil, tek karakter)
const DESEN = /(\([^)]*\)?)|([A-Za-z])([+-]?(?:\d+\.?\d*|\.\d+))|([\s\S])/g;

/**
 * Bir G-code satırını vurgu jetonlarına böler. Jetonların metinleri art arda eklenince satırın kendisi
 * (boşluklar dahil, `diger` jetonu olarak) çıkar. Parantezli yorum tek `yorum` jetonudur.
 * Harf + sayı kelimeleri: G → g, M → m, X/Y/Z/I/J/K/R/Q → eksen, F → ilerleme, S → devir, T/H → takim,
 * N → sayi.
 */
export function vurgula(satir: string): Jeton[] {
  const out: Jeton[] = [];
  const ekle = (tur: JetonTuru, metin: string) => {
    const son = out[out.length - 1];
    if (tur === "diger" && son && son.tur === "diger") son.metin += metin;
    else out.push({ tur, metin });
  };
  for (const m of satir.matchAll(DESEN)) {
    if (m[1] !== undefined) ekle("yorum", m[1]);
    else if (m[2] !== undefined) ekle(HARF[m[2].toUpperCase()] ?? "diger", m[0]);
    else ekle("diger", m[4]);
  }
  return out;
}

/**
 * satir_hareket'in tersi: hareket indeksi → onu üreten G-code satırı (yoksa −1). Uzunluk nHareket.
 * Aralıklar çakışırsa ya da nHareket dışına taşarsa Error.
 */
export function hareketSatir(satirHareket: ([number, number] | null)[], nHareket: number): Int32Array {
  const out = new Int32Array(nHareket).fill(-1);
  satirHareket.forEach((ar, s) => {
    if (ar === null) return;
    const [a, b] = ar;
    if (!(Number.isInteger(a) && Number.isInteger(b) && 0 <= a && a <= b && b < nHareket)) {
      throw new Error(`hareketSatir: satır ${s} aralığı [${a}, ${b}] geçersiz (hareket sayısı ${nHareket})`);
    }
    for (let h = a; h <= b; h++) {
      if (out[h] !== -1) throw new Error(`hareketSatir: hareket ${h} hem satır ${out[h]} hem satır ${s}'de`);
      out[h] = s;
    }
  });
  return out;
}

/** G-code satırının uç noktası: satir_hareket aralığının son hareketinin `b`'si; hareket yoksa null. */
export function satirUcNoktasi(
  satir: number,
  satirHareket: ([number, number] | null)[],
  hareketler: Hareket[],
): Nokta3 | null {
  const ar = satirHareket[satir];
  if (ar === null || ar === undefined) return null;
  const h = hareketler[ar[1]];
  if (h === undefined) throw new Error(`satirUcNoktasi: satır ${satir} hareket ${ar[1]}'e eşli ama hareket yok`);
  return [h.b[0], h.b[1], h.b[2]];
}
