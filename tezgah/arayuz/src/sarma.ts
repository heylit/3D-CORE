// SPEC 62 — zaman çizelgesinde sarma: kaydırıcı ve k → stok yüzeyi önbelleği (sunucu: /api/ekran/komut/sarma).
// Saf fonksiyonlar vitest ile sınanır.

/** /sarma/{is}/{k} ikilisi → {nx, ny, k, izgara: [x0, y0, dx, dy, zmax, zmin], z: Float32Array(ny·nx)}. */
export interface SarmaKaresi {
  nx: number;
  ny: number;
  k: number;
  izgara: Float64Array;
  z: Float32Array;
}

export function sarmaCoz(_veri: ArrayBuffer): SarmaKaresi {
  throw new Error("SPEC 62: sarmaCoz uygulanmadı");
}
