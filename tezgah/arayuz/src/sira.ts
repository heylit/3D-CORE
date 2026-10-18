// SPEC 25 — montaj sırası: adım ↔ u eşlemesi, poz ara değeri, serbestlik çipi (K17). Saf fonksiyonlar.
// Dönüşümler sunucudan gelir (4x4, satır öncelikli, 16 sayı); burada yalnızca görsel ara değer var.

export type Mat4 = number[]; // 16 eleman, satır öncelikli

export interface Serbestlik {
  sayi: number;
  oteleme: [number, number, number][];
  vida: { yon: [number, number, number]; nokta: [number, number, number]; hatve: number }[];
  etiketler: string[];
}

export interface Adim {
  i: number;
  yol: string;
  ad: string;
  yaklasma: [number, number, number];
  mesafe: number;
  T_once: Record<string, Mat4>;
  T_sonra: Record<string, Mat4>;
  dof_toplam: number;
  serbestlik: Record<string, Serbestlik>;
}

/** u ∈ [0, N] → (adım i, adım içi s ∈ [0, 1]); u = N → (N − 1, 1). u kırpılır; N < 1 ise Error. */
export function adimU(u: number, N: number): { i: number; s: number } {
  if (!(N >= 1) || !Number.isInteger(N)) throw new Error(`adimU: N ≥ 1 tam sayı olmalı (${N})`);
  if (Number.isNaN(u)) throw new Error("adimU: u sayı değil");
  const v = Math.min(Math.max(u, 0), N);
  if (v >= N) return { i: N - 1, s: 1 };
  const i = Math.floor(v);
  return { i, s: v - i };
}

/**
 * u anında `yol` bileşeninin pozu. Bileşen henüz gelmemişse (u < adımı) kendi adımının T_once'u;
 * kendi adımında T_once → T_sonra arasında yalnız öteleme yumuşatılır (dönme T_sonra'nınki);
 * sonraki adımlarda o adımın T_sonra'sı. u tam sayıda sunucunun T'si birebir döner.
 */
export function poz(sira: Adim[], yol: string, u: number): Mat4 {
  const j = sira.findIndex((a) => a.yol === yol);
  if (j < 0) throw new Error(`poz: bilinmeyen bileşen yolu ${JSON.stringify(yol)}`);
  const { i, s } = adimU(u, sira.length);
  const kendi = sira[j];
  if (i < j || (i === j && s === 0)) return [...kendi.T_once[yol]];
  if (i > j) {
    const T = sira[i].T_sonra[yol];
    if (!T) throw new Error(`poz: adım ${i}'de ${yol} için T_sonra yok`);
    return [...T];
  }
  const T1 = kendi.T_sonra[yol];
  if (s === 1) return [...T1];
  const T0 = kendi.T_once[yol];
  const M = [...T1];
  for (const q of [3, 7, 11]) M[q] = T0[q] + (T1[q] - T0[q]) * s;
  return M;
}

/** Serbestlik çipi: 6 kare; ilk `6 − sayi` dolu (kilitli), etiketler sunucudan sırasıyla. */
export function cip(s: Serbestlik): { kilitli: boolean; etiket: string }[] {
  const n = Math.min(Math.max(s.sayi, 0), 6);
  const kilit = 6 - n;
  return Array.from({ length: 6 }, (_, q) =>
    q < kilit ? { kilitli: true, etiket: "" } : { kilitli: false, etiket: s.etiketler[q - kilit] ?? "?" },
  );
}
