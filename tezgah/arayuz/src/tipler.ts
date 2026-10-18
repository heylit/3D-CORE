// SPEC 24 — sunucunun döndürdüğü veri biçimleri (tezgah/kopru.py belgesiyle aynı).

export type Nokta3 = [number, number, number];

export interface Hareket {
  g: 0 | 1 | 2 | 3;
  a: Nokta3;
  b: Nokta3;
  c?: [number, number];
  F: number | null;
  satir: number;
  islem: number;
}

export interface Kontrol {
  kimlik: string;
  baslik: string;
  deger: number | string | null;
  birim: string;
  durum: "tamam" | "uyari" | "hata";
  aciklama: string;
  spec: string;
}

export interface Islem {
  i: number;
  anahtar: string;
  ad: string;
  takim: { T: number; ad: string; R: number; tur: string };
  t0: number;
  t1: number;
  k0: number;
  k1: number;
  parametreler: Record<string, number>;
}

export interface Is {
  sema: number;
  ad: string;
  kurulum: {
    stok: { x0: number; x1: number; y0: number; y1: number; z0: number; z1: number };
    wcs: string;
    malzeme: string;
  };
  islemler: Islem[];
  hareketler: Hareket[];
  gcode: { metin: string; islem: number | null }[];
  satir_hareket: ([number, number] | null)[];
  sure: { toplam: number; islem: number[]; kumulatif_url: string };
  kontroller: Kontrol[];
}

/** Çözülmüş ikili nokta dizisi (kopru.noktalar_ikili). */
export interface Noktalar {
  n: number;
  konum: Float32Array; // n·3
  zaman: Float64Array; // n, kümülatif s
  satir: Int32Array;
  islem: Int16Array;
  hizli: Uint8Array;
  yuk: Float32Array;
  hareket: Int32Array; // noktaya getiren hareket (bağlantıda −1)
}

/** Çözülmüş sim olay listesi (kopru.sim_ikili). Hücre c = j·nx + i. */
export interface SimVeri {
  nx: number;
  ny: number;
  x0: number;
  y0: number;
  dx: number;
  dy: number;
  zUst: number;
  zAlt: number;
  ofset: Uint32Array; // nx·ny + 1
  k: Int32Array;
  z: Float32Array;
  islem: Int16Array;
}

/** Parametre ucu yanıtı. */
export interface ParametreYaniti {
  sema: number;
  is: Is;
  sure_farki: number;
}

// --------------------------------------------------------------------- SPEC 25: torna ve montaj

export type EkranAdi = "freze" | "torna" | "montaj";

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
  ag: string;
}

export interface Montaj {
  sema: number;
  ad: string;
  agac: MontajDugum;
  parcalar: MontajParca[];
  bilesenler: { yol: string; parca: string; T: number[]; sabit: boolean }[];
  bom: { item: string; kind: string; qty: number; unit_mass: number | null; total_mass: number | null }[];
  kutle: { toplam: number; merkez: Nokta3 };
  sira: import("./sira").Adim[];
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
