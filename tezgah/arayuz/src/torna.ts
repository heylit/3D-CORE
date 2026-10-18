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
export function capBicim(_x: number, _cap: boolean, _ondalik: number): string {
  throw new Error("SPEC 25: capBicim uygulanmadı");
}

/**
 * Devir şeridinde n = nMax olan kapalı zaman aralıkları [t0, t1] (|n − nMax| ≤ 1e-9·nMax).
 * T azalmayan, T ve n aynı uzunlukta; değilse Error.
 */
export function devirSinirBolgeleri(_T: ArrayLike<number>, _n: ArrayLike<number>, _nMax: number): [number, number][] {
  throw new Error("SPEC 25: devirSinirBolgeleri uygulanmadı");
}

/** `sim_ikili` baytları → TornaSim. Sürüm ya da uzunluk tutmuyorsa Error. */
export function tornaSimCoz(_veri: ArrayBuffer): TornaSim {
  throw new Error("SPEC 25: tornaSimCoz uygulanmadı");
}

/** k anındaki kesit: her hücrede k'si ≤ k olan son olay; yoksa (rDis0, rIc0). */
export function kesitAt(_sim: TornaSim, _k: number): { dis: Float32Array; ic: Float32Array } {
  throw new Error("SPEC 25: kesitAt uygulanmadı");
}
