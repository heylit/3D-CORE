// SPEC 62 §4 — ölçü sürükleme: gecikmeli (debounce) istek ve sıra numarası. Sürüklendikçe POST /surukle
// önizleme isteği gider; yalnız en son gönderilen isteğin yanıtı kullanılır (komut.ts yanitGecerliMi).
// Bırakınca model /api/ekran/model/ PUT ile yazılır (geri al SPEC 37 kabuğunda). Saf kısımlar vitest ile
// sınanır; zamanlayıcı dışarıdan verilebilir.

export const GECIKME_MS = 150;

export interface Zamanlayici {
  kur(f: () => void, ms: number): number;
  sil(kimlik: number): void;
}

/** setTimeout / clearTimeout ile varsayılan zamanlayıcı. */
export const PENCERE_ZAMANLAYICI: Zamanlayici = {
  kur: (f, ms) => setTimeout(f, ms) as unknown as number,
  sil: (k) => clearTimeout(k),
};

/**
 * Gecikmeli çağrı: `cagir(x)` her seferinde bekleyen çağrıyı iptal eder; son çağrıdan `ms` sonra yalnız son
 * argümanla `f` bir kez çalışır. `hemen()` bekleyeni beklemeden çalıştırır (bırakma anı), `iptal()` siler.
 */
export interface Geciktirilmis<A> {
  cagir(a: A): void;
  hemen(): void;
  iptal(): void;
  readonly bekliyor: boolean;
}

export function geciktir<A>(
  _f: (a: A) => void,
  _ms: number = GECIKME_MS,
  _z: Zamanlayici = PENCERE_ZAMANLAYICI,
): Geciktirilmis<A> {
  throw new Error("SPEC 62: geciktir uygulanmadı");
}

/** Sıra sayacı: `yeni()` artan sıra numarası verir; `gecerli(s)` s en son verilen numara mı. */
export class SiraSayaci {
  yeni(): number {
    throw new Error("SPEC 62: SiraSayaci uygulanmadı");
  }
  gecerli(_s: number): boolean {
    throw new Error("SPEC 62: SiraSayaci uygulanmadı");
  }
}
