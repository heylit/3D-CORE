// SPEC 24 — hareketin görsel örneklemesi (yalnız çizim ve ara değer; mühendislik hesabı değil).
// Yay: G2 saat yönü, G3 saat yönü tersi (+Z'den bakınca), merkez mutlak (x, y); z doğrusal (helis).
// Başlangıç = bitiş (XY) ise tam daire.

import type { Hareket, Nokta3 } from "./tipler";

/** Yayın başlangıç açısı ve işaretli süpürmesi [rad]. */
export function yayAci(h: Hareket): { r: number; th0: number; dth: number } {
  const [cx, cy] = h.c as [number, number];
  const r = Math.hypot(h.a[0] - cx, h.a[1] - cy);
  const th0 = Math.atan2(h.a[1] - cy, h.a[0] - cx);
  const th1 = Math.atan2(h.b[1] - cy, h.b[0] - cx);
  let d = th1 - th0;
  if (h.g === 3) {
    d = ((d % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
    if (d < 1e-12) d = 2 * Math.PI;
  } else {
    d = ((-d % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
    if (d < 1e-12) d = 2 * Math.PI;
    d = -d;
  }
  return { r, th0, dth: d };
}

/** Hareket üzerinde u ∈ [0, 1] parametresindeki nokta (yayda açıya göre eşit adımlı). */
export function hareketKonum(h: Hareket, u: number): Nokta3 {
  const z = h.a[2] + (h.b[2] - h.a[2]) * u;
  if ((h.g === 2 || h.g === 3) && h.c) {
    const { r, th0, dth } = yayAci(h);
    const th = th0 + dth * u;
    return [h.c[0] + r * Math.cos(th), h.c[1] + r * Math.sin(th), z];
  }
  return [h.a[0] + (h.b[0] - h.a[0]) * u, h.a[1] + (h.b[1] - h.a[1]) * u, z];
}

/** Yayı çizmek için parça sayısı: en fazla 3° ya da 0.2 mm kiriş. Doğruda 1. */
export function parcaSayisi(h: Hareket): number {
  if (!((h.g === 2 || h.g === 3) && h.c)) return 1;
  const { r, dth } = yayAci(h);
  return Math.max(2, Math.ceil(Math.max(Math.abs(dth) / (Math.PI / 60), (Math.abs(dth) * r) / 0.2)));
}
