// SPEC 24 — sunucu istemcisi. Tüm mühendislik sayıları buradan gelir.

import { agCoz, noktalariCoz, simCoz, tornaNoktalariCoz } from "./ikili";
import type {
  Ag,
  Is,
  Montaj,
  MontajParametreYaniti,
  Noktalar,
  Oneri,
  ParametreYaniti,
  SimVeri,
  TornaIs,
  TornaNoktalar,
} from "./tipler";
import { type TornaSim, tornaSimCoz } from "./torna";

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

// --------------------------------------------------------------------- SPEC 25: torna ve montaj

export async function tornaIsAl(ad: string): Promise<TornaIs> {
  return (await yanit(await fetch(yol(ad)))).json();
}

export async function tornaNoktalarAl(ad: string): Promise<TornaNoktalar> {
  return tornaNoktalariCoz(await (await yanit(await fetch(`${yol(ad)}/noktalar`))).arrayBuffer());
}

export async function tornaSimAl(ad: string): Promise<TornaSim> {
  return tornaSimCoz(await (await yanit(await fetch(`${yol(ad)}/sim`))).arrayBuffer());
}

/** Torna işleminin parametresi (SPEC 24 parametre ucu biçimi). */
export async function tornaParametreGonder(
  ad: string,
  islem: number,
  anahtar: string,
  deger: number,
): Promise<{ is: TornaIs; sure_farki: number }> {
  return parametreGonder(ad, islem, anahtar, deger) as unknown as Promise<{ is: TornaIs; sure_farki: number }>;
}

const myol = (ad: string) => `/api/montaj/${encodeURIComponent(ad)}`;

export async function montajAl(ad: string): Promise<Montaj> {
  return (await yanit(await fetch(myol(ad)))).json();
}

/** Ağ adresi: tam yol ("/api/...") ya da montaja göre göreli ("girisim/0", parça kimliği). */
export async function agAl(ad: string, ag: string): Promise<Ag> {
  const url = ag.startsWith("/") ? ag : `${myol(ad)}/ag/${ag.split("/").map(encodeURIComponent).join("/")}`;
  return agCoz(await (await yanit(await fetch(url))).arrayBuffer());
}

export async function montajParametre(ad: string, is: string, anahtar: string, deger: number): Promise<MontajParametreYaniti> {
  const r = await fetch(`${myol(ad)}/parametre`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is, anahtar, deger }),
  });
  return (await yanit(r)).json();
}

export async function oneriAl(ad: string, is: string, anahtar: string, cift: [string, string]): Promise<Oneri> {
  const q = new URLSearchParams({ is, anahtar, cift: cift.join(",") });
  return (await yanit(await fetch(`${myol(ad)}/oneri?${q}`))).json();
}
