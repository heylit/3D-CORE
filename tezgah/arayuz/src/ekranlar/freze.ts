// SPEC 24 — freze ekranı (A3: main.ts'deki freze'ye özgü kod). İş yığını, müfettiş, G-code / kanıt
// sekmeleri, HUD, oynatma ve komutlar. Sahneye yalnız "freze" katmanına çizer.

import { SunucuHatasi, isAl, isListesi, noktalarAl, parametreGonder, simAl } from "../api";
import { hareketSatir, satirUcNoktasi } from "../gcode";
import { GcodePaneli, PARAMETRE, islemRengi, kanitlarCiz, mufettisCiz, sayi, solCiz } from "../paneller";
import type { Katman } from "../sahne";
import { sureYaz } from "../serit";
import type { Is, Nokta3, Noktalar, SimVeri } from "../tipler";
import { hareketKonum } from "../yol";
import { idxAt } from "../zaman";
import type { EkranModulu, Kabuk, Komut } from "./tip";

const AD = "freze";
const $ = <T extends HTMLElement = HTMLElement>(s: string) => document.querySelector<T>(s)!;
const HIZLAR = [1, 5, 20, 60];

interface Durum {
  ad: string;
  is?: Is;
  nk?: Noktalar;
  sim: SimVeri | null;
  hareketSatiri: Int32Array;
  renkler: string[];
  t: number;
  oynuyor: boolean;
  hiz: number;
  secili: number;
  sekme: "gcode" | "kanit";
  katman: Katman;
  uzerindeSatir: number;
  fark: number | null;
  hata: string | null;
  dro: Nokta3;
  hazir: boolean;
  mesgul: boolean;
  /** Sunucunun kabul ettiği, sahnesi henüz yüklenmekte olan iş (kanca bunu raporlar). */
  gelenIs: Is | null;
}

const D: Durum = {
  ad: "",
  sim: null,
  hareketSatiri: new Int32Array(0),
  renkler: [],
  t: 0,
  oynuyor: false,
  hiz: 20,
  secili: 0,
  sekme: "gcode",
  katman: "islem",
  uzerindeSatir: -1,
  fark: null,
  hata: null,
  dro: [0, 0, 0],
  hazir: false,
  mesgul: false,
  gelenIs: null,
};

let K: Kabuk | null = null;
let gcode: GcodePaneli | null = null;
let onceki: number | null = null;
const temizlik: (() => void)[] = [];

function kabuk(): Kabuk {
  if (!K) throw new Error("freze ekranı açık değil");
  return K;
}

// --------------------------------------------------------------------- yükleme

async function yukle(ad: string, kameraKoru = false, hazirIs?: Is): Promise<void> {
  D.mesgul = true;
  const [is, nk, sim] = await Promise.all([hazirIs ?? isAl(ad), noktalarAl(ad), simAl(ad).catch(() => null)]);
  if (!K) return; // yükleme sürerken ekran kapandı
  if (ad !== D.ad) D.t = 0;
  D.ad = ad;
  D.is = is;
  D.nk = nk;
  D.sim = sim;
  D.renkler = is.islemler.map(islemRengi);
  D.hareketSatiri = hareketSatir(is.satir_hareket, is.hareketler.length);
  D.t = Math.min(D.t, is.sure.toplam);
  D.secili = Math.max(0, Math.min(D.secili, is.islemler.length - 1));
  K.sahne.isKur(is, nk, sim, D.renkler, kameraKoru);
  const hatalar = is.kontroller.filter((k) => k.durum === "hata").map((k) => kontrolNoktasi(k.aciklama));
  K.serit.kur(is, nk, D.renkler, hatalar.filter((k): k is number => k !== null));
  gcode!.kur(is);
  panelleriCiz();
  guncelle(true);
  const uyari = is.kontroller.filter((k) => k.durum !== "tamam").length;
  K.rozet(AD, uyari ? `${uyari} uyarı` : null);
  D.gelenIs = null;
  D.mesgul = false;
  D.hazir = true;
}

function kontrolNoktasi(aciklama: string): number | null {
  const m = /nokta (\d+)/.exec(aciklama);
  return m ? Number(m[1]) : null;
}

// --------------------------------------------------------------------- çizim

function panelleriCiz(): void {
  const is = D.is!;
  solCiz($("#sol"), is, D.nk!, D.secili, D.fark, islemSec);
  mufettisCiz($("#mufettis"), is, D.secili, D.hata, parametreDegistir);
  sekmeleriCiz();
  hudCiz();
}

function sekmeleriCiz(): void {
  const is = D.is!;
  const hata = is.kontroller.filter((k) => k.durum !== "tamam").length;
  const s = $("#sekmeler");
  s.innerHTML = `<button role="tab" data-sekme="gcode" aria-selected="${D.sekme === "gcode"}">G-code <span class="sayi">${is.gcode.length}</span></button>
    <button role="tab" data-sekme="kanit" aria-selected="${D.sekme === "kanit"}">Kanıtlar <span class="sayi">${hata ? `${hata} ⚠` : "✓"}</span></button>`;
  s.querySelectorAll<HTMLButtonElement>("button").forEach((b) =>
    b.addEventListener("click", () => sekmeSec(b.dataset.sekme as Durum["sekme"])),
  );
}

function sekmeSec(sekme: Durum["sekme"]): void {
  D.sekme = sekme;
  sekmeleriCiz();
  if (sekme === "gcode") gcode!.kur(D.is!);
  else kanitlarCiz($("#bolme"), D.is!.kontroller);
  guncelle(true);
}

function hudCiz(): void {
  const is = D.is!;
  const isl = is.islemler[D.secili];
  $("#hudBaslik").innerHTML = `<b>${isl ? isl.ad : is.ad}</b><span>${is.ad} · ${is.kurulum.malzeme} · ${is.kurulum.wcs}</span>`;
  const katmanlar: [Katman, string][] = [
    ["islem", "İşlem"],
    ["yuk", "Takım yükü"],
  ];
  $("#hudKatman").innerHTML = `<div class="parca" role="group" aria-label="Katman">${katmanlar
    .map(([k, ad]) => `<button data-katman="${k}" aria-pressed="${D.katman === k}">${ad}</button>`)
    .join("")}</div>${D.katman === "yuk" ? `<div class="lejant">düşük <span class="rampa"></span> yüksek</div>` : ""}`;
  $("#hudKatman")
    .querySelectorAll<HTMLButtonElement>("button")
    .forEach((b) => b.addEventListener("click", () => katmanSec(b.dataset.katman as Katman)));
  const hatalar = is.kontroller.filter((k) => k.durum === "hata");
  $("#hudUyari").innerHTML = hatalar.length
    ? hatalar.map((k) => `<div class="uyari-kutu hata"><b>${k.baslik}</b>${k.aciklama}</div>`).join("")
    : `<div class="uyari-kutu tamam"><b>Kanıtlar tamam</b>${is.kontroller.length} kontrol, ihlal yok</div>`;
}

function katmanSec(k: Katman): void {
  D.katman = k;
  kabuk().sahne.renkKatmani(k);
  hudCiz();
  guncelle(true);
}

/** t anına göre takım, yüzey, DRO, saat, G-code vurgusu. */
function guncelle(zorla = false): void {
  const is = D.is;
  const nk = D.nk;
  if (!is || !nk || !K) return;
  const k = idxAt(D.t, nk.zaman);
  // görsel ara değer: k ile k+1 arasında, hareket yaysa yay üstünde
  let p: Nokta3 = [nk.konum[3 * k], nk.konum[3 * k + 1], nk.konum[3 * k + 2]];
  let islem = nk.islem[k];
  if (k + 1 < nk.n && nk.zaman[k + 1] > nk.zaman[k]) {
    const u = (D.t - nk.zaman[k]) / (nk.zaman[k + 1] - nk.zaman[k]);
    const hk = nk.hareket[k + 1];
    islem = nk.islem[k + 1];
    if (hk >= 0) p = hareketKonum(is.hareketler[hk], u);
    else {
      const q = k + 1;
      p = [0, 1, 2].map((i) => nk.konum[3 * k + i] + (nk.konum[3 * q + i] - nk.konum[3 * k + i]) * u) as Nokta3;
    }
  }
  D.dro = p;
  K.sahne.takimKonum(p, islem);
  K.sahne.ilerleme(k);
  K.serit.zaman(D.t);
  const satir = k + 1 < nk.n && nk.satir[k + 1] >= 0 ? nk.satir[k + 1] : nk.satir[k];
  if (D.sekme === "gcode") gcode!.vurgula(satir, D.oynuyor || zorla);
  const hk = nk.hareket[Math.min(k + 1, nk.n - 1)];
  const F = hk >= 0 ? is.hareketler[hk].F : null;
  $("#hudDro").innerHTML = `<div class="dro" data-test="dro">
    <div><i>X</i><span>${sayi(p[0])}</span></div><div><i>Y</i><span>${sayi(p[1])}</span></div><div><i>Z</i><span>${sayi(p[2])}</span></div>
    <div class="alt">${satir >= 0 ? `N${satir + 1}` : "—"} · ${F === null ? "G0 hızlı" : `F${F}`} · T${is.islemler[islem]?.takim.T ?? "-"}</div></div>`;
  $("#saat").innerHTML = `${sureYaz(D.t)} <span>/ ${sureYaz(is.sure.toplam)}</span>`;
}

function zamanAyarla(t: number, durdur: boolean): void {
  if (!D.is) return;
  if (durdur) oynat(false);
  D.t = Math.min(Math.max(t, 0), D.is.sure.toplam);
  guncelle();
}

// --------------------------------------------------------------------- etkileşim

function islemSec(i: number): void {
  D.secili = i;
  D.hata = null;
  const isl = D.is!.islemler[i];
  zamanAyarla(isl.t0, true);
  panelleriCiz();
}

function satirUstunde(satir: number): void {
  if (!D.is || !K) return;
  D.uzerindeSatir = satir;
  gcode!.ustundeki(satir);
  const is = D.is;
  const p = satir >= 0 ? satirUcNoktasi(satir, is.satir_hareket, is.hareketler) : null;
  const ar = satir >= 0 ? is.satir_hareket[satir] : null;
  K.sahne.hayalet(p, ar ? is.hareketler[ar[1]].islem : 0);
}

function satiraGit(satir: number): void {
  const is = D.is!;
  const nk = D.nk!;
  const ar = is.satir_hareket[satir];
  if (!ar) return;
  // satırın son hareketinin bittiği nokta
  for (let k = 0; k < nk.n; k++) {
    if (nk.hareket[k] === ar[1]) {
      zamanAyarla(nk.zaman[k], true);
      return;
    }
  }
}

async function parametreDegistir(anahtar: string, deger: number): Promise<void> {
  if (D.mesgul) return;
  D.mesgul = true;
  try {
    const y = await parametreGonder(D.ad, D.secili, anahtar, deger);
    D.fark = y.sure_farki;
    D.hata = null;
    D.gelenIs = y.is;
    await yukle(D.ad, true, y.is);
  } catch (e) {
    D.hata = e instanceof SunucuHatasi ? e.message : String(e);
    D.gelenIs = null;
    D.mesgul = false;
    if (K && D.is) mufettisCiz($("#mufettis"), D.is, D.secili, D.hata, parametreDegistir);
  }
}

const OYNAT_SVG = `<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M4 2.5v11l9-5.5z"/></svg>`;
const DURAKLAT_SVG = `<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M3.5 2.5h3v11h-3zM9.5 2.5h3v11h-3z"/></svg>`;

function oynat(acik: boolean): void {
  if (acik && D.is && D.t >= D.is.sure.toplam) D.t = 0;
  D.oynuyor = acik;
  const b = $("#oynat");
  b.innerHTML = acik ? DURAKLAT_SVG : OYNAT_SVG;
  b.setAttribute("aria-label", acik ? "Duraklat (Boşluk)" : "Oynat (Boşluk)");
}

function hizCiz(): void {
  const h = $("#hiz");
  h.innerHTML = HIZLAR.map((v) => `<button data-hiz="${v}" aria-pressed="${D.hiz === v}">×${v}</button>`).join("");
  h.querySelectorAll<HTMLButtonElement>("button").forEach((b) =>
    b.addEventListener("click", () => {
      D.hiz = Number(b.dataset.hiz);
      hizCiz();
    }),
  );
}

function adim(yon: 1 | -1): void {
  const nk = D.nk;
  if (!nk) return;
  const k = idxAt(D.t, nk.zaman);
  let j = Math.min(Math.max(k + yon, 0), nk.n - 1);
  while (j > 0 && j < nk.n - 1 && nk.zaman[j] === nk.zaman[k]) j += yon;
  zamanAyarla(nk.zaman[j], true);
}

function tus(e: KeyboardEvent): void {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.key === "Escape") {
    satirUstunde(-1);
    return;
  }
  const hedef = e.target as HTMLElement;
  if (hedef.matches("input, textarea, select") || hedef.isContentEditable) return;
  if (e.key === " ") {
    if (hedef.matches("button")) return; // odaklı düğmenin kendi Boşluk davranışı
    e.preventDefault();
    oynat(!D.oynuyor);
  } else if (e.key === "ArrowRight") {
    e.preventDefault();
    adim(1);
  } else if (e.key === "ArrowLeft") {
    e.preventDefault();
    adim(-1);
  } else if (e.key === "Home") zamanAyarla(0, true);
  else if (e.key === "End" && D.is) zamanAyarla(D.is.sure.toplam, true);
}

function dinle(el: EventTarget, tur: string, f: (e: Event) => void): void {
  el.addEventListener(tur, f);
  temizlik.push(() => el.removeEventListener(tur, f));
}

// --------------------------------------------------------------------- komutlar

/** Parametre anahtarı → palette yazılabilecek eş anlamlılar (ör. "çap 12"). */
const ESANLAMLI: Record<string, string[]> = {
  D: ["çap", "cap", "takım", "takim", "d"],
  ap: ["paso", "derinlik", "ap"],
  F: ["ilerleme", "f"],
  rpm: ["devir", "s", "rpm"],
  stepover: ["adım", "adim", "stepover"],
  q: ["gagalama", "q"],
};

function komutlar(): Komut[] {
  const is = D.is;
  if (!is) return [];
  const isl = is.islemler[D.secili];
  const parametre: Komut[] = isl
    ? Object.keys(isl.parametreler)
        .filter((a) => a in ESANLAMLI)
        .map((a) => ({
          kimlik: `freze.parametre.${a}`,
          baslik: `${PARAMETRE[a]?.ad ?? a} (${isl.ad} · şu an ${isl.parametreler[a]})`,
          anahtar_kelimeler: ESANLAMLI[a],
          desen: `${ESANLAMLI[a][0]} <sayı>`,
          calistir: (sayi?: number) => (sayi === undefined ? undefined : parametreDegistir(a, sayi)),
          yama: (sayi: number) => [
            { bolum: "isler", isaretci: `/ornekler/0/parametreler/${D.secili}/${a}`, deger: sayi },
          ],
        }))
    : [];
  return [
    ...parametre,
    { kimlik: "freze.oynat", baslik: D.oynuyor ? "Duraklat" : "Oynat", anahtar_kelimeler: ["boşluk"], calistir: () => oynat(!D.oynuyor) },
    { kimlik: "freze.basa", baslik: "Başa dön", anahtar_kelimeler: ["home"], calistir: () => zamanAyarla(0, true) },
    { kimlik: "freze.sona", baslik: "Sona git", anahtar_kelimeler: ["end", "son yüzey"], calistir: () => zamanAyarla(is.sure.toplam, true) },
    { kimlik: "freze.katman.islem", baslik: "Katman: işlem", anahtar_kelimeler: ["yüzey işlem rengiyle"], calistir: () => katmanSec("islem") },
    { kimlik: "freze.katman.yuk", baslik: "Katman: takım yükü", anahtar_kelimeler: ["talaş kaldırma hızı"], calistir: () => katmanSec("yuk") },
    { kimlik: "freze.gcode", baslik: "G-code", anahtar_kelimeler: ["sekme"], calistir: () => sekmeSec("gcode") },
    { kimlik: "freze.kanit", baslik: "Kanıtlar", anahtar_kelimeler: ["sekme"], calistir: () => sekmeSec("kanit") },
    ...is.islemler.map((i) => ({
      kimlik: `freze.islem.${i.i}`,
      baslik: `İşlem: ${i.ad}`,
      anahtar_kelimeler: [i.anahtar, `${sureYaz(i.t0)} · T${i.takim.T}`],
      calistir: () => islemSec(i.i),
    })),
  ];
}

// --------------------------------------------------------------------- EkranModulu

function secimIs(secim?: string): string | null {
  return secim ? new URLSearchParams(secim).get("is") : null;
}

const freze: EkranModulu = {
  ad: AD,
  baslik: "Freze",
  tus: "1",

  async ac(_alan: HTMLElement, k: Kabuk, secim?: string): Promise<void> {
    K = k;
    D.hazir = false;
    gcode ??= new GcodePaneli($("#bolme"), satirUstunde, satiraGit);
    k.sahne.isKatmani(k.sahne.katman(AD));
    k.sahne.renkKatmani(D.katman);
    k.serit.dinle((t) => zamanAyarla(t, true));
    // Getter kopyalansın diye defineProperties (Object.assign değeri kopyalar).
    const kancaAlanlari = {
      get hazir() {
        return D.hazir && !D.mesgul;
      },
      hayaletKonum: () => (K ? K.sahne.hayaletKonum() : null),
      dro: () => [...D.dro] as Nokta3,
      zaman: () => D.t,
      gcodeSatirSayisi: () => (D.gelenIs ?? D.is)?.gcode.length ?? 0,
      toplamSure: () => (D.gelenIs ?? D.is)?.sure.toplam ?? 0,
      yuzey: () => (K ? K.sahne.yuzey() : null),
    };
    Object.defineProperties(k.kanca, Object.getOwnPropertyDescriptors(kancaAlanlari));
    hizCiz();
    oynat(false);
    dinle($("#oynat"), "click", () => oynat(!D.oynuyor));
    dinle(document, "keydown", (e) => tus(e as KeyboardEvent));
    const isler = await isListesi();
    if (!isler.length) throw new Error("Sunucuda iş yok");
    const istenen = secimIs(secim);
    await yukle(istenen && isler.includes(istenen) ? istenen : D.ad && isler.includes(D.ad) ? D.ad : isler[0]);
  },

  kapat(): void {
    oynat(false);
    for (const f of temizlik.splice(0)) f();
    if (K) {
      K.sahne.hayalet(null, 0);
      K.sahne.katmanBirak(AD);
      K.serit.bosalt();
    }
    K = null;
    D.hazir = false;
    onceki = null;
  },

  async tazele(): Promise<void> {
    if (K && D.ad) await yukle(D.ad, true);
  },

  komutlar,

  sec(oge: string): void {
    const i = Number(oge);
    if (D.is && Number.isInteger(i) && i >= 0 && i < D.is.islemler.length) islemSec(i);
  },

  kare(t: number): void {
    const dt = onceki === null ? 0 : Math.min(t - onceki, 0.1);
    onceki = t;
    if (D.oynuyor && D.is) {
      D.t += dt * D.hiz;
      if (D.t >= D.is.sure.toplam) {
        D.t = D.is.sure.toplam;
        oynat(false);
      }
      guncelle();
    }
  },
};

export default freze;
