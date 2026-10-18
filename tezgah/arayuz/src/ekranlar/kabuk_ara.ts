// SPEC 37 — komut paleti eşleştirmesi: Türkçe katlama, puanlama, parametreli komut deseni. Saf (vitest).

import type { Komut } from "./tip";

/** Türkçe küçük harf, ardından ı→i, ş→s, ğ→g, ü→u, ö→o, ç→c, â→a, î→i, û→u. */
export function katla(s: string): string {
  void s;
  throw new Error("SPEC 37: uygulanmadı");
}

/**
 * Alt dizi eşleşmesi ve dört puan basamağı (başlıkla başlar > kelime başı > bitişik > alt dizi);
 * eşitlikte daha kısa toplam boşluk, `son` sırası, başlık alfabetik. Boş sorgu: `son` (en fazla 8), sonra alfabetik.
 * Desene uyan parametreli komut ilk sıraya çıkar.
 */
export function eslestir(sorgu: string, komutlar: Komut[], son: string[]): Komut[] {
  void sorgu;
  void komutlar;
  void son;
  throw new Error("SPEC 37: uygulanmadı");
}

/**
 * Sorgu `desen`'e ("L <sayı>") uyuyorsa sayı ("." ya da "," ondalık); uymuyorsa ya da sayı geçersizse
 * (nan, inf, boş, fazladan metin) null.
 */
export function desenSayisi(desen: string, sorgu: string): number | null {
  void desen;
  void sorgu;
  throw new Error("SPEC 37: uygulanmadı");
}
