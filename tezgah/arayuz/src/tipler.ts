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
}
