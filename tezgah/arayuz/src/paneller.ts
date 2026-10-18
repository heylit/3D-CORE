// SPEC 24 — paneller: iş özeti ve işlem yığını, müfettiş, G-code, kanıtlar, komut çubuğu.
// Sayıların hepsi sunucu yanıtından; burada yalnız biçimlendirme.

import { vurgula } from "./gcode";
import { sureYaz } from "./serit";
import type { Is, Islem, Kontrol, Noktalar } from "./tipler";
import { kivilcim } from "./zaman";

export const ISLEM_RENKLERI: Record<string, string> = {
  yuzey: "#93a6ba",
  kontur: "#5cb8dc",
  cep: "#d6a54e",
  delik: "#b98ae0",
};
export const TAKIM_TURU: Record<string, string> = { duz: "düz parmak", kuresel: "küresel uç", matkap: "matkap" };
const YEDEK = ["#e3795d", "#55c08f", "#93a6ba", "#5cb8dc"];

export const islemRengi = (isl: Islem): string => ISLEM_RENKLERI[isl.anahtar] ?? YEDEK[isl.i % YEDEK.length];

const kacis = (s: string) =>
  s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

export function sayi(v: number, ondalik = 3): string {
  const r = Number(v.toFixed(ondalik));
  return (Object.is(r, -0) ? 0 : r).toFixed(ondalik);
}

// --------------------------------------------------------------------- sol: iş + işlem yığını

export function solCiz(
  kap: HTMLElement,
  is: Is,
  nk: Noktalar,
  secili: number,
  fark: number | null,
  sec: (i: number) => void,
): void {
  const s = is.kurulum.stok;
  const kontrolHata = is.kontroller.filter((k) => k.durum === "hata").length;
  kap.innerHTML = `
    <section class="bolum">
      <h2 class="ust-baslik">İş <span>${kacis(is.kurulum.wcs)}</span></h2>
      <dl class="kv">
        <dt>Ad</dt><dd>${kacis(is.ad)}</dd>
        <dt>Malzeme</dt><dd>${kacis(is.kurulum.malzeme)}</dd>
        <dt>Stok</dt><dd>${sayi(s.x1 - s.x0, 1)} × ${sayi(s.y1 - s.y0, 1)} × ${sayi(s.z1 - s.z0, 1)} mm</dd>
        <dt>Hareket</dt><dd>${is.hareketler.length} · ${is.gcode.length} satır</dd>
        <dt>Kanıt</dt><dd>${is.kontroller.length - kontrolHata}/${is.kontroller.length} tamam</dd>
      </dl>
      <div class="cevrim">
        <div><small>Çevrim süresi</small><span class="buyuk" data-test="toplam-sure">${sureYaz(is.sure.toplam)}</span></div>
        <span class="fark ${fark === null ? "" : "acik"} ${fark !== null && fark <= 0 ? "iyi" : "kotu"}" id="sureFarki">${
          fark === null ? "" : `${fark <= 0 ? "−" : "+"}${Math.abs(fark).toFixed(1)} s`
        }</span>
      </div>
    </section>
    <section class="bolum">
      <h2 class="ust-baslik">İşlemler <span>${is.islemler.length}</span></h2>
      <div class="islemler" id="islemListe"></div>
    </section>`;
  const liste = kap.querySelector<HTMLElement>("#islemListe")!;
  for (const isl of is.islemler) {
    const b = document.createElement("button");
    b.className = "islem";
    b.dataset.testid = "islem";
    b.dataset.islem = String(isl.i);
    b.style.setProperty("--r", islemRengi(isl));
    b.setAttribute("aria-current", String(isl.i === secili));
    b.innerHTML = `<span class="serit-renk"></span>
      <span class="ad"><i>${String(isl.i + 1).padStart(2, "0")}</i>${kacis(isl.ad)}</span>
      <span class="sure">${sureYaz(isl.t1 - isl.t0)}</span>
      <span class="alt"><span>T${isl.takim.T} · Ø${sayi(2 * isl.takim.R, 1)}</span><canvas aria-hidden="true"></canvas></span>`;
    b.addEventListener("click", () => sec(isl.i));
    liste.appendChild(b);
    kivilcimCiz(b.querySelector("canvas")!, nk, isl, islemRengi(isl));
  }
}

function kivilcimCiz(tv: HTMLCanvasElement, nk: Noktalar, isl: Islem, renk: string): void {
  const W = 72;
  const H = 16;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  tv.width = W * dpr;
  tv.height = H * dpr;
  const c = tv.getContext("2d");
  if (!c || isl.k1 <= isl.k0) return;
  c.scale(dpr, dpr);
  const y = kivilcim(nk.zaman.subarray(isl.k0, isl.k1 + 1), nk.yuk.subarray(isl.k0, isl.k1 + 1), W / 2);
  c.fillStyle = renk;
  y.forEach((v, i) => v > 0 && c.fillRect(i * 2, H * (1 - v), 1.5, H * v));
}

// --------------------------------------------------------------------- müfettiş

interface Aralik {
  ad: string;
  min: number;
  max: number;
  adim: number;
  birim: string;
}

export const PARAMETRE: Record<string, Aralik> = {
  D: { ad: "Takım çapı", min: 1, max: 50, adim: 0.5, birim: "mm" },
  ap: { ad: "Paso derinliği", min: 0.2, max: 6, adim: 0.1, birim: "mm" },
  stepover: { ad: "Yan adım", min: 0.5, max: 25, adim: 0.1, birim: "mm" },
  q: { ad: "Gagalama", min: 0.5, max: 10, adim: 0.5, birim: "mm" },
  F: { ad: "İlerleme", min: 50, max: 4000, adim: 10, birim: "mm/dk" },
  rpm: { ad: "Devir", min: 500, max: 24000, adim: 100, birim: "dev/dk" },
};

function takimSimgesi(tur: string): string {
  const uc =
    tur === "matkap"
      ? `<path d="M15 26 L21 34 L27 26" />`
      : tur === "kuresel"
        ? `<path d="M15 26 A6 6 0 0 0 27 26" />`
        : `<path d="M15 26 L15 30 L27 30 L27 26" />`;
  return `<svg viewBox="0 0 42 42" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
    <rect x="12" y="2" width="18" height="8" rx="1" /><rect x="17" y="10" width="8" height="8" />
    <path d="M15 18 L15 26 M27 18 L27 26 M15 18 L27 18 M15 22 L27 20" />${uc}</svg>`;
}

export function mufettisCiz(
  kap: HTMLElement,
  is: Is,
  secili: number,
  hata: string | null,
  degistir: (anahtar: string, deger: number) => void,
): void {
  const isl = is.islemler[secili];
  if (!isl) {
    kap.innerHTML = "";
    return;
  }
  const t = isl.takim;
  kap.innerHTML = `<section class="bolum">
      <h2 class="ust-baslik">Müfettiş <span style="color:${islemRengi(isl)}">${kacis(isl.ad)}</span></h2>
      <div class="takim-kart">${takimSimgesi(t.tur)}<div><b>T${t.T} · ${kacis(t.ad)}</b>
        <span>${kacis(TAKIM_TURU[t.tur] ?? t.tur)} · R ${sayi(t.R, 2)} mm · ${sureYaz(isl.t0)}–${sureYaz(isl.t1)}</span></div></div>
      ${hata ? `<div class="hata-kutu" role="alert"><b>Çekirdek reddetti</b>${kacis(hata)}</div>` : ""}
      <div id="kaydiricilar"></div>
    </section>`;
  const k = kap.querySelector<HTMLElement>("#kaydiricilar")!;
  for (const [anahtar, deger] of Object.entries(isl.parametreler)) {
    const a = PARAMETRE[anahtar] ?? { ad: anahtar, min: 0, max: deger * 3 || 1, adim: 0.1, birim: "" };
    const kimlik = `p-${anahtar}`;
    const d = document.createElement("div");
    d.className = "kaydirici";
    d.innerHTML = `<label for="${kimlik}">${a.ad} <small>(${anahtar})</small></label>
      <output for="${kimlik}">${deger} ${a.birim}</output>
      <input type="range" id="${kimlik}" data-testid="parametre" data-anahtar="${anahtar}" min="${a.min}" max="${Math.max(a.max, deger)}" step="${a.adim}" value="${deger}">`;
    const girdi = d.querySelector("input")!;
    const cikti = d.querySelector("output")!;
    girdi.addEventListener("input", () => (cikti.textContent = `${girdi.value} ${a.birim}`));
    girdi.addEventListener("change", () => degistir(anahtar, Number(girdi.value)));
    k.appendChild(d);
  }
}

// --------------------------------------------------------------------- G-code

export class GcodePaneli {
  private satirlar: HTMLDivElement[] = [];
  private etkin = -1;
  private uzerinde = -1;

  constructor(
    private kap: HTMLElement,
    private ustune: (satir: number) => void,
    private tikla: (satir: number) => void,
  ) {}

  kur(is: Is): void {
    const g = document.createElement("div");
    g.className = "gc";
    g.setAttribute("role", "list");
    this.satirlar = is.gcode.map((s, i) => {
      const d = document.createElement("div");
      d.setAttribute("role", "listitem");
      d.dataset.satir = String(i);
      d.dataset.testid = "gcode-satir";
      const n = document.createElement("span");
      n.className = "n";
      n.textContent = String(i + 1);
      const m = document.createElement("span");
      for (const j of vurgula(s.metin)) {
        const e = document.createElement("span");
        e.className = `j-${j.tur}`;
        e.textContent = j.metin;
        m.appendChild(e);
      }
      d.append(n, m);
      return d;
    });
    g.append(...this.satirlar);
    g.addEventListener("pointerover", (e) => {
      const d = (e.target as HTMLElement).closest<HTMLElement>("[data-satir]");
      if (d) this.ustune(Number(d.dataset.satir));
    });
    g.addEventListener("pointerleave", () => this.ustune(-1));
    g.addEventListener("click", (e) => {
      const d = (e.target as HTMLElement).closest<HTMLElement>("[data-satir]");
      if (d) this.tikla(Number(d.dataset.satir));
    });
    this.kap.replaceChildren(g);
    this.etkin = -1;
  }

  vurgula(etkin: number, kaydir: boolean): void {
    if (etkin === this.etkin) return;
    this.satirlar[this.etkin]?.classList.remove("etkin");
    this.etkin = etkin;
    const d = this.satirlar[etkin];
    if (!d) return;
    d.classList.add("etkin");
    if (kaydir && this.uzerinde < 0) d.scrollIntoView({ block: "nearest" });
  }

  ustundeki(satir: number): void {
    this.satirlar[this.uzerinde]?.classList.remove("uzerinde");
    this.uzerinde = satir;
    this.satirlar[satir]?.classList.add("uzerinde");
  }
}

// --------------------------------------------------------------------- kanıtlar

export function kanitlarCiz(kap: HTMLElement, kontroller: Kontrol[]): void {
  const ik = { tamam: "✓", uyari: "!", hata: "×" };
  kap.innerHTML = `<div class="kanitlar">${kontroller
    .map(
      (k) => `<div class="kanit" data-kimlik="${kacis(k.kimlik)}" data-durum="${k.durum}">
        <span class="ik ${k.durum}">${ik[k.durum]}</span><b>${kacis(k.baslik)}</b>
        <span class="d">${k.deger === null ? "—" : typeof k.deger === "number" ? `${sayi(k.deger, 4)} ${kacis(k.birim)}` : kacis(String(k.deger))}</span>
        <span class="a">${kacis(k.aciklama)} · <em>${kacis(k.spec)}</em></span></div>`,
    )
    .join("")}</div>
    <p class="not">Her kanıt çekirdekteki testli bir fonksiyonun çıktısıdır; arayüz hesap yapmaz.</p>`;
}
