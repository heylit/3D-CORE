// SPEC 25 — torna ve montaj ekranlarının sunucu tipleri ve ikili dizi çözücüleri (tezgah/sunucu_25.py).
// SPEC 24 tipleri (tipler.ts) ve ikili biçimi (ikili.ts) ile aynı kurallar: little-endian, her blok 8 baytın
// katına sıfırla tamamlanmış.

import type { Mat4, Adim } from "./sira";
import type { Is, Islem, Kontrol, Nokta3, Noktalar } from "./tipler";

/** Torna takımı (tezgah/torna.py `islemler[].takim`). q: hayali uçtan burun merkezine [q_z, q_x]. */
export interface TornaTakim {
  T: number;
  ad: string;
  r: number;
  uc: number | string;
  q: [number, number];
  tur: string;
}

export interface TornaIslem extends Omit<Islem, "takim"> {
  takim: TornaTakim;
  plane?: string;
  feed_mode?: string;
  css?: number | boolean | null;
  rpm?: number | null;
}

export interface Silindir {
  tur: string;
  D: number;
  d: number;
  zmin: number;
  zmax: number;
}

/** Torna işi (`tur: "torna"`): SPEC 24 `Is` + torna alanları. Hareketler (x, 0, z), x yarıçap. */
export interface TornaIs extends Omit<Is, "islemler" | "kurulum" | "gcode" | "sure"> {
  tur: "torna";
  kurulum: { stok: Silindir; aynalar?: Silindir[]; wcs?: string; malzeme?: string };
  islemler: TornaIslem[];
  gcode: { metin: string; islem: number | null; dro?: { X: number; Z: number } | null }[];
  sure: { toplam: number; islem: number[]; kumulatif_url: string; n_max: number | null };
}

/** Torna nokta dizisi: SPEC 24 alanları + devir [dev/dk]. */
export interface TornaNoktalar extends Noktalar {
  devir: Float32Array;
}

/** POST /api/ekran/torna/is/kademeli_mil/parametre yanıtı. */
export interface TornaParametreYaniti {
  sema: number;
  is: TornaIs;
  sure_farki: number;
}

export interface Ag {
  V: Float32Array; // nv·3
  F: Uint32Array; // nt·3
}

export interface MontajDugum {
  name: string;
  T: number[][];
  part: string | null;
  children: MontajDugum[];
  ref?: string | null;
}

export interface MontajParca {
  kimlik: string;
  ad: string;
  malzeme: string;
  rho: number;
  kaynak: { is: string; tur: string } | null;
  hacim: number;
}

export interface Bag {
  parametre: { is: string; anahtar: string; deger: number; min: number; max: number };
  parcalar: string[];
}

export interface Girisim {
  i?: number;
  a: string;
  b: string;
  hacim: number;
  bosluk: number | null;
  /** Kesişim ağının mutlak adresi ("/api/ekran/montaj/<ad>/ag/girisim/<i>"). */
  ag: string;
}

export interface Montaj {
  sema: number;
  ad: string;
  agac: MontajDugum;
  parcalar: MontajParca[];
  bilesenler: { yol: string; parca: string; T: Mat4; sabit: boolean }[];
  bom: { item: string; kind: string; qty: number; unit_mass: number | null; total_mass: number | null }[];
  kutle: { toplam: number; merkez: Nokta3 };
  sira: Adim[];
  girisimler: Girisim[];
  kontroller: Kontrol[];
  baglar: Bag[];
}

export interface MontajParametreYaniti {
  montaj: Montaj;
  is: TornaIs;
  sure_farki: number;
}

export type Oneri = { deger: number; hacim: number } | { deger: null; neden: string };

// --------------------------------------------------------------------- ikili çözücüler

const SEMA = 1;

/** Sırayla blok okur; her blok 8 baytın katına tamamlanmıştır (ikili.ts ile aynı kural). */
class Okuyucu {
  constructor(
    readonly buf: ArrayBuffer,
    public ofs: number,
  ) {}
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

/** SPEC 25 torna nokta dizisi: SPEC 24 biçimi + son blok float32[n] devir. */
export function tornaNoktalariCoz(buf: ArrayBuffer): TornaNoktalar {
  const v = new DataView(buf);
  sema(v);
  const n = v.getUint32(4, true);
  const o = new Okuyucu(buf, 8);
  const out: TornaNoktalar = {
    n,
    konum: o.al(Float32Array, 3 * n),
    zaman: o.al(Float64Array, n),
    satir: o.al(Int32Array, n),
    islem: o.al(Int16Array, n),
    hizli: o.al(Uint8Array, n),
    yuk: o.al(Float32Array, n),
    hareket: o.al(Int32Array, n),
    devir: o.al(Float32Array, n),
  };
  if (o.ofs !== buf.byteLength) throw new Error("Torna nokta dizisi boyu tutmuyor");
  return out;
}

/** SPEC 25 üçgen ağ: uint32 sema, nv, nt, 0; float32[nv·3]; uint32[nt·3]. */
export function agCoz(buf: ArrayBuffer): Ag {
  const v = new DataView(buf);
  sema(v);
  const nv = v.getUint32(4, true);
  const nt = v.getUint32(8, true);
  const o = new Okuyucu(buf, 16);
  const out = { V: o.al(Float32Array, 3 * nv), F: o.al(Uint32Array, 3 * nt) };
  if (o.ofs !== buf.byteLength) throw new Error("Ağ dizisi boyu tutmuyor");
  return out;
}
