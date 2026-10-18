// SPEC 24 — sunucunun ikili dizilerini (kopru.noktalar_ikili, kopru.sim_ikili) typed array'lere çözer.
// Biçim little-endian, her blok 8 baytın katına sıfırla tamamlanmış; tarayıcılar little-endian olduğundan
// diziler kopyasız görünüm olarak okunur.

import type { Noktalar, SimVeri } from "./tipler";

const SEMA = 1;

class Okuyucu {
  ofs: number;
  constructor(
    readonly buf: ArrayBuffer,
    ofs: number,
  ) {
    this.ofs = ofs;
  }
  al<T>(Tur: { new (b: ArrayBuffer, o: number, n: number): T; BYTES_PER_ELEMENT: number }, n: number): T {
    const boy = Tur.BYTES_PER_ELEMENT * n;
    if (this.ofs + boy > this.buf.byteLength) throw new Error("İkili dizi kısa");
    const a = new Tur(this.buf, this.ofs, n);
    this.ofs += boy + ((8 - (boy % 8)) % 8);
    return a;
  }
}

function sema(v: DataView): void {
  const s = v.getUint32(0, true);
  if (s !== SEMA) throw new Error(`İkili dizi sürümü ${s}, beklenen ${SEMA}`);
}

export function noktalariCoz(buf: ArrayBuffer): Noktalar {
  const v = new DataView(buf);
  sema(v);
  const n = v.getUint32(4, true);
  const o = new Okuyucu(buf, 8);
  const out: Noktalar = {
    n,
    konum: o.al(Float32Array, 3 * n),
    zaman: o.al(Float64Array, n),
    satir: o.al(Int32Array, n),
    islem: o.al(Int16Array, n),
    hizli: o.al(Uint8Array, n),
    yuk: o.al(Float32Array, n),
    hareket: o.al(Int32Array, n),
  };
  if (o.ofs !== buf.byteLength) throw new Error("Nokta dizisi boyu tutmuyor");
  return out;
}

export function simCoz(buf: ArrayBuffer): SimVeri {
  const v = new DataView(buf);
  sema(v);
  const nx = v.getUint32(4, true);
  const ny = v.getUint32(8, true);
  const m = v.getUint32(12, true);
  const o = new Okuyucu(buf, 16);
  const g = o.al(Float64Array, 6);
  const out: SimVeri = {
    nx,
    ny,
    x0: g[0],
    y0: g[1],
    dx: g[2],
    dy: g[3],
    zUst: g[4],
    zAlt: g[5],
    ofset: o.al(Uint32Array, nx * ny + 1),
    k: o.al(Int32Array, m),
    z: o.al(Float32Array, m),
    islem: o.al(Int16Array, m),
  };
  if (o.ofs !== buf.byteLength) throw new Error("Sim dizisi boyu tutmuyor");
  return out;
}

/**
 * k anındaki yüzey: her hücrede k'si ≤ k olan son olayın z'si (yoksa zUst); `islem` hücreyi son kesen işlem
 * (yoksa −1), `olay` o olayın nokta indeksi (yoksa −1). Dizileri yerinde doldurur.
 */
export function yuzeyAt(s: SimVeri, k: number, z: Float32Array, islem: Int16Array, olay: Int32Array): void {
  const { ofset } = s;
  for (let c = 0; c < s.nx * s.ny; c++) {
    let a = ofset[c];
    let b = ofset[c + 1];
    if (a === b || s.k[a] > k) {
      z[c] = s.zUst;
      islem[c] = -1;
      olay[c] = -1;
      continue;
    }
    // hücre içi k artan: k'si ≤ k olan son olay
    while (b - a > 1) {
      const m = (a + b) >>> 1;
      if (s.k[m] <= k) a = m;
      else b = m;
    }
    z[c] = s.z[a];
    islem[c] = s.islem[a];
    olay[c] = s.k[a];
  }
}
