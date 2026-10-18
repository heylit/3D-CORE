// SPEC 62 — zaman çizelgesinde sarma: k → stok yüzeyi çözümü ve önbelleği (sunucu: /api/ekran/komut/sarma).
// Sunucu yanıtı SPEC 24 `sim_ikili` biçimidir (k anındaki yüzey, değişen hücre başına tek olay); burada
// `simCoz` + `yuzeyAt` ile düz yüzeye açılır. Saf fonksiyonlar vitest ile sınanır.

import { simCoz, yuzeyAt } from "./ikili";

/** /sarma/{is}/{k} ikilisi → {nx, ny, k, izgara: [x0, y0, dx, dy, zmax, zmin], z: Float32Array(ny·nx)}. */
export interface SarmaKaresi {
  nx: number;
  ny: number;
  k: number;
  izgara: Float64Array;
  z: Float32Array;
}

export function sarmaCoz(veri: ArrayBuffer, k: number): SarmaKaresi {
  const s = simCoz(veri);
  const n = s.nx * s.ny;
  const z = new Float32Array(n);
  yuzeyAt(s, k, z, new Int16Array(n), new Int32Array(n));
  const izgara = Float64Array.from([s.x0, s.y0, s.dx, s.dy, s.zUst, s.zAlt]);
  return { nx: s.nx, ny: s.ny, k, izgara, z };
}

/** En son kullanılan `boyut` kareyi tutan önbellek (kaydırıcı ileri-geri giderken istek tekrarlanmaz). */
export class SarmaOnbellek {
  private readonly kareler = new Map<number, SarmaKaresi>();
  constructor(
    private readonly getir: (k: number) => Promise<ArrayBuffer>,
    readonly boyut = 32,
  ) {
    if (!Number.isInteger(boyut) || boyut < 1) throw new Error(`Önbellek boyutu pozitif tamsayı olmalı (${boyut})`);
  }

  async al(k: number): Promise<SarmaKaresi> {
    const var_ = this.kareler.get(k);
    if (var_ !== undefined) {
      this.kareler.delete(k);
      this.kareler.set(k, var_);
      return var_;
    }
    const kare = sarmaCoz(await this.getir(k), k);
    this.kareler.set(k, kare);
    if (this.kareler.size > this.boyut) this.kareler.delete(this.kareler.keys().next().value as number);
    return kare;
  }

  get sayi(): number {
    return this.kareler.size;
  }
}
