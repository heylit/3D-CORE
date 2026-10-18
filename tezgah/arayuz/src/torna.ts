// SPEC 25 — torna ekranının saf fonksiyonları (K17). Arayüz hesap yapmaz: devir, kesit ve hedef
// sunucudan gelir; burada yalnızca biçimleme, arama ve iki sunucu değerinin farkı var.

/** Torna kesit olay listesi (tezgah/torna.py `sim_ikili`). */
export interface TornaSim {
  nz: number;
  z0: number;
  dz: number;
  rDis0: number;
  rIc0: number;
  ofset: Uint32Array;
  k: Int32Array;
  rDis: Float32Array;
  rIc: Float32Array;
  islem: Int16Array;
  hedef: Float32Array;
}

/**
 * DRO metni: çap modunda 2·x, yarıçap modunda x; `ondalik` basamak, G-code yazıcısıyla aynı yuvarlama
 * (−0 → 0). x sonlu değilse Error.
 */
export function capBicim(x: number, cap: boolean, ondalik: number): string {
  if (!Number.isFinite(x)) throw new Error(`capBicim: sonlu olmayan sayı (${x})`);
  const v = cap ? 2 * x : x;
  let s = v.toFixed(ondalik);
  if (s.includes(".")) s = s.replace(/0+$/, "");
  else s += ".";
  if (/^-0\.?$/.test(s)) s = "0.";
  return s;
}

/**
 * Devir şeridinde n = nMax olan kapalı zaman aralıkları [t0, t1] (|n − nMax| ≤ 1e-9·nMax).
 * T azalmayan, T ve n aynı uzunlukta; değilse Error.
 */
export function devirSinirBolgeleri(T: ArrayLike<number>, n: ArrayLike<number>, nMax: number): [number, number][] {
  if (T.length !== n.length) throw new Error(`devirSinirBolgeleri: T (${T.length}) ve n (${n.length}) uzunluğu farklı`);
  for (let i = 1; i < T.length; i++) {
    if (!(T[i] >= T[i - 1])) throw new Error(`devirSinirBolgeleri: T azalıyor (indeks ${i})`);
  }
  const tol = 1e-9 * Math.abs(nMax);
  const out: [number, number][] = [];
  let bas = -1;
  for (let i = 0; i <= T.length; i++) {
    const sinirda = i < T.length && Math.abs(n[i] - nMax) <= tol;
    if (sinirda && bas < 0) bas = i;
    else if (!sinirda && bas >= 0) {
      out.push([T[bas], T[i - 1]]);
      bas = -1;
    }
  }
  return out;
}

const SIM_SEMA = 1;
const hiza = (n: number) => Math.ceil(n / 8) * 8;

/** `sim_ikili` baytları → TornaSim. Sürüm ya da uzunluk tutmuyorsa Error. */
export function tornaSimCoz(veri: ArrayBuffer): TornaSim {
  if (veri.byteLength < 48) throw new Error("Torna sim dizisi kısa");
  const dv = new DataView(veri);
  const sema = dv.getUint32(0, true);
  if (sema !== SIM_SEMA) throw new Error(`Torna sim sürümü ${sema}, beklenen ${SIM_SEMA}`);
  const nz = dv.getUint32(4, true);
  const m = dv.getUint32(8, true);
  const boy = 48 + hiza(4 * (nz + 1)) + 3 * hiza(4 * m) + hiza(2 * m) + hiza(4 * nz);
  if (veri.byteLength !== boy) throw new Error(`Torna sim dizisi boyu ${veri.byteLength}, beklenen ${boy}`);
  let yer = 48;
  const al = <A>(Tur: { new (b: ArrayBuffer, o: number, n: number): A; BYTES_PER_ELEMENT: number }, n: number): A => {
    const a = new Tur(veri, yer, n);
    yer += hiza(Tur.BYTES_PER_ELEMENT * n);
    return a;
  };
  const S: TornaSim = {
    nz,
    z0: dv.getFloat64(16, true),
    dz: dv.getFloat64(24, true),
    rDis0: dv.getFloat64(32, true),
    rIc0: dv.getFloat64(40, true),
    ofset: al(Uint32Array, nz + 1),
    k: al(Int32Array, m),
    rDis: al(Float32Array, m),
    rIc: al(Float32Array, m),
    islem: al(Int16Array, m),
    hedef: al(Float32Array, nz),
  };
  if (S.ofset[0] !== 0 || S.ofset[nz] !== m) throw new Error("Torna sim ofset dizisi tutarsız");
  return S;
}

/** Hücre h'de k'si ≤ k olan son olayın indeksi; yoksa −1 (hücre içi k artan: ikili arama). */
function sonOlay(S: TornaSim, h: number, k: number): number {
  let a = S.ofset[h];
  let b = S.ofset[h + 1];
  if (a === b || S.k[a] > k) return -1;
  while (b - a > 1) {
    const m = (a + b) >>> 1;
    if (S.k[m] <= k) a = m;
    else b = m;
  }
  return a;
}

/** k anındaki kesit: her hücrede k'si ≤ k olan son olay; yoksa (rDis0, rIc0). */
export function kesitAt(sim: TornaSim, k: number): { dis: Float32Array; ic: Float32Array } {
  const dis = new Float32Array(sim.nz);
  const ic = new Float32Array(sim.nz);
  for (let h = 0; h < sim.nz; h++) {
    const e = sonOlay(sim, h, k);
    dis[h] = e < 0 ? sim.rDis0 : sim.rDis[e];
    ic[h] = e < 0 ? sim.rIc0 : sim.rIc[e];
  }
  return { dis, ic };
}

/** k anında her hücreyi son kesen işlem; kesilmemişse −1 (kesit yüzü rengi için). */
export function kesitIslem(sim: TornaSim, k: number): Int16Array {
  const out = new Int16Array(sim.nz);
  for (let h = 0; h < sim.nz; h++) {
    const e = sonOlay(sim, h, k);
    out[h] = e < 0 ? -1 : sim.islem[e];
  }
  return out;
}

/**
 * Torna hareketinde u ∈ [0, 1] noktası (yalnız çizim ve görsel ara değer). Hareketler (x, 0, z), yay merkezi
 * c = (x, z); G18 düzleminde u = z, v = x, +Y'den bakınca G3 saat yönü tersi (cam.model kuralı).
 */
export function tornaHareketKonum(
  h: { g: number; a: [number, number, number]; b: [number, number, number]; c?: [number, number] },
  u: number,
): [number, number, number] {
  const y = h.a[1] + (h.b[1] - h.a[1]) * u;
  if ((h.g === 2 || h.g === 3) && h.c) {
    const { r, th0, dth } = tornaYayAci(h);
    const th = th0 + dth * u;
    // u = z, v = x
    return [h.c[0] + r * Math.sin(th), y, h.c[1] + r * Math.cos(th)];
  }
  return [h.a[0] + (h.b[0] - h.a[0]) * u, y, h.a[2] + (h.b[2] - h.a[2]) * u];
}

/** Torna yayının (u = z, v = x) düzlemindeki yarıçapı, başlangıç açısı ve işaretli süpürmesi. */
export function tornaYayAci(h: {
  g: number;
  a: [number, number, number];
  b: [number, number, number];
  c?: [number, number];
}): { r: number; th0: number; dth: number } {
  const [cx, cz] = h.c as [number, number];
  const r = Math.hypot(h.a[2] - cz, h.a[0] - cx);
  const th0 = Math.atan2(h.a[0] - cx, h.a[2] - cz);
  const th1 = Math.atan2(h.b[0] - cx, h.b[2] - cz);
  const tam = 2 * Math.PI;
  let d = th1 - th0;
  if (h.g === 3) {
    d = ((d % tam) + tam) % tam;
    if (d < 1e-12) d = tam;
  } else {
    d = ((-d % tam) + tam) % tam;
    if (d < 1e-12) d = tam;
    d = -d;
  }
  return { r, th0, dth: d };
}
