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
function nokta(a: Nokta3, b: Nokta3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function vektorel(a: Nokta3, b: Nokta3): Nokta3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

export function isinDuzlemUv(o: Nokta3, d: Nokta3, duzlem: Duzlem): Nokta2 | null {
  const n = duzlem.normal;
  const dn = nokta(d, n);
  if (Math.abs(dn) <= 1e-12 * Math.hypot(...d)) return null;
  const w: Nokta3 = [duzlem.origin[0] - o[0], duzlem.origin[1] - o[1], duzlem.origin[2] - o[2]];
  const t = nokta(w, n) / dn;
  if (t < 0) return null;
  // r = P − origin = t·d − w
  const r: Nokta3 = [t * d[0] - w[0], t * d[1] - w[1], t * d[2] - w[2]];
  const y = vektorel(n, duzlem.xdir);
  return [nokta(r, duzlem.xdir), nokta(r, y)];
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
  const out: Oneri[] = [];
  const dx = imlecPx[0] - basPx[0];
  const dy = imlecPx[1] - basPx[1];
  if (Math.hypot(dx, dy) > 0) {
    const aci = (Math.atan2(Math.abs(dy), Math.abs(dx)) * 180) / Math.PI; // 0 yatay, 90 dikey
    if (aci <= esik.aciDerece) out.push({ tur: "yatay" });
    else if (90 - aci <= esik.aciDerece) out.push({ tur: "dikey" });
  }
  let en: { kimlik: string; d: number } | null = null;
  for (const u of uclar) {
    const d = Math.hypot(u.px[0] - imlecPx[0], u.px[1] - imlecPx[1]);
    if (d <= esik.piksel && (en === null || d < en.d)) en = { kimlik: u.kimlik, d };
  }
  if (en !== null) out.push({ tur: "cakisik", kimlik: en.kimlik });
  return out;
}
