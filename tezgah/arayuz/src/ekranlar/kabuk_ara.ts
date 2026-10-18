// SPEC 37 — komut paleti eşleştirmesi: Türkçe katlama, puanlama, parametreli komut deseni. Saf (vitest).

import type { Komut } from "./tip";

const AKSAN: Record<string, string> = { ı: "i", ş: "s", ğ: "g", ü: "u", ö: "o", ç: "c", â: "a", î: "i", û: "u" };

/** Türkçe küçük harf, ardından ı→i, ş→s, ğ→g, ü→u, ö→o, ç→c, â→a, î→i, û→u. */
export function katla(s: string): string {
  return s.toLocaleLowerCase("tr").replace(/[ışğüöçâîû]/g, (c) => AKSAN[c]);
}

/** Puan: basamak (0 desen, 1 başlıkla başlar, 2 kelime başı, 3 bitişik, 4 alt dizi) ve toplam boşluk. */
interface Puan {
  basamak: number;
  bosluk: number;
}

function kelimeBasi(metin: string, i: number): boolean {
  return i === 0 || !/[\p{L}\p{N}]/u.test(metin[i - 1]);
}

/** `q`'nun `metin` içindeki en dar alt dizi eşleşmesinin boşluğu (aralık − |q|); yoksa null. */
function altDiziBoslugu(q: string, metin: string): number | null {
  let enIyi: number | null = null;
  for (let bas = metin.indexOf(q[0]); bas >= 0; bas = metin.indexOf(q[0], bas + 1)) {
    let j = bas;
    let k = 0;
    for (; j < metin.length && k < q.length; j++) if (metin[j] === q[k]) k++;
    if (k < q.length) break;
    const bosluk = j - bas - q.length;
    if (enIyi === null || bosluk < enIyi) enIyi = bosluk;
  }
  return enIyi;
}

function metinPuani(q: string, metin: string, baslikMi: boolean): Puan | null {
  if (baslikMi && metin.startsWith(q)) return { basamak: 1, bosluk: 0 };
  let bitisik = false;
  for (let i = metin.indexOf(q); i >= 0; i = metin.indexOf(q, i + 1)) {
    if (kelimeBasi(metin, i)) return { basamak: 2, bosluk: 0 };
    bitisik = true;
  }
  if (bitisik) return { basamak: 3, bosluk: 0 };
  const bosluk = altDiziBoslugu(q, metin);
  return bosluk === null ? null : { basamak: 4, bosluk };
}

function daha_iyi(a: Puan, b: Puan): boolean {
  return a.basamak < b.basamak || (a.basamak === b.basamak && a.bosluk < b.bosluk);
}

function puanla(q: string, k: Komut): Puan | null {
  if (k.desen && desenSayisi(k.desen, q) !== null) return { basamak: 0, bosluk: 0 };
  let enIyi = metinPuani(q, katla(k.baslik), true);
  for (const a of k.anahtar_kelimeler ?? []) {
    const p = metinPuani(q, katla(a), false);
    if (p && (!enIyi || daha_iyi(p, enIyi))) enIyi = p;
  }
  return enIyi;
}

function alfabetik(a: Komut, b: Komut): number {
  const x = katla(a.baslik);
  const y = katla(b.baslik);
  return x < y ? -1 : x > y ? 1 : 0;
}

/**
 * Alt dizi eşleşmesi ve dört puan basamağı (başlıkla başlar > kelime başı > bitişik > alt dizi);
 * eşitlikte daha kısa toplam boşluk, `son` sırası, başlık alfabetik. Boş sorgu: `son` (en fazla 8), sonra alfabetik.
 * Desene uyan parametreli komut ilk sıraya çıkar.
 */
export function eslestir(sorgu: string, komutlar: Komut[], son: string[]): Komut[] {
  const q = katla(sorgu).trim();
  const sira = (k: Komut) => {
    const i = son.indexOf(k.kimlik);
    return i < 0 ? Number.POSITIVE_INFINITY : i;
  };
  if (q === "") {
    const yakin = son
      .slice(0, 8)
      .map((s) => komutlar.find((k) => k.kimlik === s))
      .filter((k): k is Komut => k !== undefined);
    const kalan = komutlar.filter((k) => !yakin.includes(k)).sort(alfabetik);
    return [...yakin, ...kalan];
  }
  const puanli: { k: Komut; p: Puan }[] = [];
  for (const k of komutlar) {
    const p = puanla(q, k);
    if (p) puanli.push({ k, p });
  }
  puanli.sort(
    (a, b) =>
      a.p.basamak - b.p.basamak || a.p.bosluk - b.p.bosluk || sira(a.k) - sira(b.k) || alfabetik(a.k, b.k),
  );
  return puanli.map((x) => x.k);
}

function kacis(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Sorgu `desen`'e ("L <sayı>") uyuyorsa sayı ("." ya da "," ondalık); uymuyorsa ya da sayı geçersizse
 * (nan, inf, boş, fazladan metin) null.
 */
export function desenSayisi(desen: string, sorgu: string): number | null {
  const parca = desen.split("<sayı>");
  if (parca.length !== 2) return null;
  const onek = katla(parca[0]).trim();
  const sonek = katla(parca[1]).trim();
  const ifade = new RegExp(
    `^${kacis(onek)}${onek ? "\\s+" : ""}([+-]?(?:\\d+(?:[.,]\\d+)?|[.,]\\d+))${sonek ? `\\s*${kacis(sonek)}` : ""}$`,
  );
  const m = ifade.exec(katla(sorgu).trim());
  if (!m) return null;
  const sayi = Number(m[1].replace(",", "."));
  return Number.isFinite(sayi) ? sayi : null;
}
