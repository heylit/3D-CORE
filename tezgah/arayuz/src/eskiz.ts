// SPEC 26 — eskiz katmanının saf fonksiyonları (K10): imleç ışını → düzlem uv, yakalama önerileri.
// Arayüz hesap yapmaz: buradaki sonuçlar yalnızca imleci düzleme oturtur ve kısıt önerir; çözüm sunucudadır.

import type { Nokta3 } from "./tipler";

export type Nokta2 = [number, number];

/** sketch.model.Plane JSON'u: origin, birim normal, birim xdir (ydir = normal × xdir). */
export interface Duzlem {
  origin: Nokta3;
  normal: Nokta3;
  xdir: Nokta3;
}

export type OneriTuru = "yatay" | "dikey" | "cakisik";

/** Yakalama önerisi; "cakisik"te kimlik yakalanan uç noktanın kimliği. */
export interface Oneri {
  tur: OneriTuru;
  kimlik?: string;
}

export interface Esikler {
  aciDerece: number; // yatay / dikey için açı eşiği
  piksel: number; // uç noktaya çakışma için ekran uzaklığı eşiği
}

export const VARSAYILAN_ESIK: Esikler = { aciDerece: 3, piksel: 8 };

/**
 * Işın (başlangıç o, yön d) ile düzlemin kesişimi, düzlemin uv'sinde: P = origin + u·xdir + v·ydir.
 * Işın düzleme paralelse (|d · n| ≤ 1e-12 |d|) ya da kesişim ışının gerisindeyse null.
 */
export function isinDuzlemUv(o: Nokta3, d: Nokta3, duzlem: Duzlem): Nokta2 | null {
  void [o, d, duzlem];
  throw new Error("SPEC 26: isinDuzlemUv uygulanmadı");
}

/**
 * Çizilen parçanın başı → imleç (ekran pikseli) için öneriler: doğrultu yataya / düşeye açı eşiği içindeyse
 * "yatay" / "dikey"; imleç bir uç noktaya piksel eşiği içindeyse en yakını için "cakisik". Öneri yoksa [].
 */
export function yakalamaOnerileri(
  basPx: Nokta2,
  imlecPx: Nokta2,
  uclar: { kimlik: string; px: Nokta2 }[],
  esik: Esikler = VARSAYILAN_ESIK,
): Oneri[] {
  void [basPx, imlecPx, uclar, esik];
  throw new Error("SPEC 26: yakalamaOnerileri uygulanmadı");
}
