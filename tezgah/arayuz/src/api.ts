// SPEC 24 — sunucu istemcisi. Tüm mühendislik sayıları buradan gelir.

import type { EkranApi } from "./ekranlar/tip";
import { noktalariCoz, simCoz } from "./ikili";
import type { Is, Noktalar, ParametreYaniti, SimVeri } from "./tipler";

export class SunucuHatasi extends Error {
  constructor(
    readonly durum: number,
    mesaj: string,
  ) {
    super(mesaj);
  }
}

async function yanit(r: Response): Promise<Response> {
  if (r.ok) return r;
  let mesaj = `${r.status} ${r.statusText}`;
  try {
    const j = await r.json();
    if (typeof j.detail === "string") mesaj = j.detail;
    else if (Array.isArray(j.detail)) mesaj = j.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    /* gövde JSON değil */
  }
  throw new SunucuHatasi(r.status, mesaj);
}

const yol = (ad: string) => `/api/is/${encodeURIComponent(ad)}`;

export async function isListesi(): Promise<string[]> {
  return (await (await yanit(await fetch("/api/isler"))).json()).isler;
}

export async function isAl(ad: string): Promise<Is> {
  return (await yanit(await fetch(yol(ad)))).json();
}

export async function noktalarAl(ad: string): Promise<Noktalar> {
  return noktalariCoz(await (await yanit(await fetch(`${yol(ad)}/noktalar`))).arrayBuffer());
}

export async function simAl(ad: string): Promise<SimVeri> {
  return simCoz(await (await yanit(await fetch(`${yol(ad)}/sim`))).arrayBuffer());
}

export async function parametreGonder(ad: string, islem: number, anahtar: string, deger: number): Promise<ParametreYaniti> {
  return degistir(`${yol(ad)}/parametre`, { islem, anahtar, deger }, `${ad}: işlem ${islem} ${anahtar} → ${deger}`);
}

// ------------------------------------------------------------------ A3 ekran kaydı (specs/24a-ekran-kaydi.md)

const aboneler = new Set<(etiket: string | null) => void>();

/**
 * Başarılı her durum değiştiren istekten (POST / PUT / PATCH / DELETE) sonra `cb(etiket)` çağrılır.
 * Dönen fonksiyon aboneliği kaldırır.
 */
export function degisiklikSonrasi(cb: (etiket: string | null) => void): () => void {
  // Aynı fonksiyon iki kez abone olabilsin diye sarılır.
  const sarili = (etiket: string | null) => cb(etiket);
  aboneler.add(sarili);
  return () => {
    aboneler.delete(sarili);
  };
}

/** Durum değiştiren POST: JSON gövde + `X-Tezgah-Etiket` (URI kodlu; başlıklar Latin-1 olmalı). */
async function degistir<T>(adres: string, govde: unknown, etiket?: string): Promise<T> {
  const basliklar: Record<string, string> = { "Content-Type": "application/json" };
  if (etiket !== undefined) basliklar["X-Tezgah-Etiket"] = encodeURIComponent(etiket);
  const r = await yanit(await fetch(adres, { method: "POST", headers: basliklar, body: JSON.stringify(govde) }));
  const j = (await r.json()) as T;
  for (const cb of [...aboneler]) cb(etiket ?? null);
  return j;
}

/** `/api/ekran/<ad>/` önekli istemci; postJson `X-Tezgah-Etiket` başlığı taşır, GET taşımaz. */
export function ekranApi(ad: string): EkranApi {
  const onek = `/api/ekran/${encodeURIComponent(ad)}/`;
  const tam = (y: string) => onek + y.replace(/^\/+/, "");
  return {
    getJson: async <T>(y: string) => (await (await yanit(await fetch(tam(y)))).json()) as T,
    getIkili: async (y: string) => (await yanit(await fetch(tam(y)))).arrayBuffer(),
    postJson: <T>(y: string, govde: unknown, etiket?: string) => degistir<T>(tam(y), govde, etiket),
  };
}
