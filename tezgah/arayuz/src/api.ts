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
  const r = await fetch(`${yol(ad)}/parametre`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ islem, anahtar, deger }),
  });
  return (await yanit(r)).json();
}

// ------------------------------------------------------------------ A3 ekran kaydı (specs/24a-ekran-kaydi.md)

/**
 * Başarılı her durum değiştiren istekten (POST / PUT / PATCH / DELETE) sonra `cb(etiket)` çağrılır.
 * Dönen fonksiyon aboneliği kaldırır.
 */
export function degisiklikSonrasi(cb: (etiket: string | null) => void): () => void {
  void cb;
  throw new Error("A3: uygulanmadı");
}

/** `/api/ekran/<ad>/` önekli istemci; postJson `X-Tezgah-Etiket` başlığı taşır, GET taşımaz. */
export function ekranApi(ad: string): EkranApi {
  void ad;
  throw new Error("A3: uygulanmadı");
}
