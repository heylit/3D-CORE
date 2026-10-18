// A3 — Tezgah ekran kaydı: ortak arayüz (specs/24a-ekran-kaydi.md). Değişikliği ayrı PR + kullanıcı onayı.
// Her ekran src/ekranlar/<ad>.ts dosyasında `export default` bir EkranModulu verir.

import type { Sahne } from "../sahne";
import type { Serit } from "../serit";
import type { Kontrol } from "../tipler";

/** Kabuğa ait kısayollar: ekranlar bunları kaydedemez (§3). */
export const KABUK_KISAYOLLARI: readonly string[] = [
  "Ctrl+K",
  "Ctrl+Z",
  "Ctrl+Shift+Z",
  "Ctrl+Y",
  "Ctrl+S",
  "Ctrl+Shift+S",
  "Ctrl+O",
];

export interface EkranModulu {
  /** Sunucudaki Ekran.ad ile aynı. */
  ad: string;
  baslik: string;
  /** Sekme kısayolu, tek rakam. */
  tus?: string;
  /** Sekmeye girince; `secim`: adresteki `?…` kısmı (ör. "is=plan-3"). */
  ac(alan: HTMLElement, kabuk: Kabuk, secim?: string): Promise<void>;
  /** Sekmeden çıkınca: dinleyiciler ve sahne katmanı temizlenir. */
  kapat(): void;
  /** Sunucu durumu dışarıdan değişti (geri al, proje aç). */
  tazele?(): Promise<void>;
  /** Ctrl K paletine (ekran etkinken). */
  komutlar?(): Komut[];
  /** Dışarıdan seçim (ör. etki kartından bir işleme git). */
  sec?(oge: string): void;
  /** Animasyon karesi; t [s]. */
  kare?(t: number): void;
}

export interface EkranApi {
  /** Yollar ekranın /api/ekran/<ad>/ önekine görelidir; 4xx/5xx → SunucuHatasi. */
  getJson<T>(yol: string): Promise<T>;
  getIkili(yol: string): Promise<ArrayBuffer>;
  /** Durum değiştirir: `X-Tezgah-Etiket` başlığı taşır (geri al listesindeki ad). */
  postJson<T>(yol: string, govde: unknown, etiket?: string): Promise<T>;
}

export interface Kabuk {
  /** katman(ad): THREE.Group — ekran yalnız kendi grubuna çizer. */
  sahne: Sahne;
  /** Zaman şeridi; alt şerit ve olay işareti dahil. */
  serit: Serit;
  /** Sağ paneldeki kontrol kartları (SPEC 24 biçimi). */
  kanitlar(k: Kontrol[]): void;
  /** Sağ paneli ekranın müfettişine ver. */
  mufettis(alan: HTMLElement): void;
  /** Dinamik komut ekleme (ekran kapanınca kalkar). Kabuk kısayolu → Error. */
  komut(k: Komut): void;
  /** Adrese git, ör. "#/freze?is=plan-3". */
  git(adres: string): void;
  /** Sekme rozeti (ör. "3 uyarı"); null → kaldır. */
  rozet(ekran: string, metin: string | null): void;
  /** window.__tezgah.<ad> (e2e kancası). */
  kanca: Record<string, unknown>;
  api: EkranApi;
}

export interface Komut {
  kimlik: string;
  baslik: string;
  anahtar_kelimeler?: string[];
  ekran?: string;
  kisayol?: string;
  /** Ör. "L <sayı>": yazılan sayı calistir / yama'ya gelir. */
  desen?: string;
  calistir(sayi?: number): void | Promise<void>;
  /** Önizleme / geri al için: hangi değer değişecek. */
  yama?(sayi: number): Yama[];
}

/** isaretci: JSON Pointer (RFC 6901) — bölüm belgesinin içinde. */
export interface Yama {
  bolum: string;
  isaretci: string;
  deger: unknown;
}

/** GET /api/ekranlar satırı. */
export interface SunucuEkrani {
  ad: string;
  baslik: string;
  sira: number;
  tus: string | null;
  hazir: boolean;
  neden: string | null;
  bolum: string | null;
  bagimli: string[];
}

/** Kabuğun çizdiği sekme: sunucu ∩ ön yüz. */
export interface Sekme {
  ad: string;
  baslik: string;
  tus: string | null;
  /** false: kapalı sekme (sunucuda hazır değil ya da ön yüzü yok); ipucu `neden`. */
  acik: boolean;
  neden: string | null;
  modul: EkranModulu | null;
}
