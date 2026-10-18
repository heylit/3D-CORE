// SPEC 25 — torna ekranı (A3: src/ekranlar/torna.ts). Kademeli mil işi; yol, çap programlı G-code, devir
// şeridi, dönel kesit, kanıtlar. Sayıların hepsi sunucudan (/api/ekran/torna/…); burada yalnız biçim, görsel
// ara değer ve iki sunucu sayısının farkı var. Sahneye yalnız "torna" katmanına çizer.

import { SunucuHatasi } from "../api";
import { DevirSeridi } from "../devir_serit";
import { satirUcNoktasi } from "../gcode";
import { GcodePaneli, sayi } from "../paneller";
import { TornaSahne } from "../sahne_torna";
import { sureYaz } from "../serit";
import type { Is, Nokta3 } from "../tipler";
import { type TornaIs, type TornaIslem, type TornaNoktalar, type TornaParametreYaniti, tornaNoktalariCoz } from "../tipler_25";
import { type TornaSim, capBicim, kesitAt, tornaHareketKonum, tornaSimCoz } from "../torna";
import { idxAt } from "../zaman";
import type { EkranModulu, Kabuk, Komut } from "./tip";

const AD = "torna";
const TORNA_IS = "kademeli_mil";
const YOL = `is/${TORNA_IS}`;
const ONDALIK = 3; // G-code yazıcısının ondalığı (SPEC 21)
const HIZLAR = [1, 5, 20, 60];

const $ = <T extends HTMLElement = HTMLElement>(s: string) => document.querySelector<T>(s)!;
const kacis = (s: string) =>
  s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

const OYNAT_SVG = `<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M4 2.5v11l9-5.5z"/></svg>`;
const DURAKLAT_SVG = `<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M3.5 2.5h3v11h-3zM9.5 2.5h3v11h-3z"/></svg>`;

const ISLEM_RENKLERI: Record<string, string> = {
  alin: "#93a6ba",
  kaba: "#d6a54e",
  ince: "#5cb8dc",
  kanal: "#b98ae0",
  dis: "#e3795d",
  boy: "#55c08f",
};
const YEDEK = ["#e3795d", "#55c08f", "#93a6ba", "#5cb8dc"];
const islemRengi = (isl: TornaIslem) => ISLEM_RENKLERI[isl.anahtar] ?? YEDEK[isl.i % YEDEK.length];

interface Aralik {
  ad: string;
  min: number;
  max: number;
  adim: number;
  birim: string;
}

const PARAMETRE: Record<string, Aralik> = {
  a_p: { ad: "Paso derinliği", min: 0.2, max: 6, adim: 0.1, birim: "mm" },
  ap: { ad: "Paso derinliği", min: 0.2, max: 6, adim: 0.1, birim: "mm" },
  f: { ad: "İlerleme", min: 0.02, max: 0.8, adim: 0.01, birim: "mm/dev" },
  Vc: { ad: "Kesme hızı", min: 20, max: 500, adim: 5, birim: "m/dk" },
  n_max: { ad: "Devir sınırı (G50)", min: 300, max: 6000, adim: 50, birim: "dev/dk" },
  rpm: { ad: "Devir (G97)", min: 100, max: 6000, adim: 50, birim: "dev/dk" },
  r: { ad: "Burun yarıçapı", min: 0.1, max: 2.4, adim: 0.1, birim: "mm" },
};

/** Parametre anahtarı → komut paletinde yazılabilecek eş anlamlılar (ilki desenin sözcüğü: "paso 2"). */
const ESANLAMLI: Record<string, string[]> = {
  a_p: ["paso", "derinlik", "ap", "a_p"],
  ap: ["paso", "derinlik", "ap"],
  f: ["ilerleme", "f"],
  Vc: ["vc", "hız", "hiz"],
  n_max: ["nmax", "n_max"],
  rpm: ["devir", "rpm"],
};

// --------------------------------------------------------------------- durum

interface Durum {
  is: TornaIs | null;
  nk: TornaNoktalar | null;
  sim: TornaSim | null;
  renkler: string[];
  t: number;
  oynuyor: boolean;
  hiz: number;
  secili: number | null;
  sekme: "gcode" | "kanit";
  cap: boolean;
  uzerindeSatir: number;
  /** Mufettişteki parametre hatası (çekirdek reddetti). */
  hata: string | null;
  /** İş yüklenemedi (ör. sunucu 500). */
  yukHata: string | null;
  fark: number | null;
  dro: Nokta3;
  mesgul: boolean;
  yuklendi: boolean;
}

const D: Durum = {
  is: null,
  nk: null,
  sim: null,
  renkler: [],
  t: 0,
  oynuyor: false,
  hiz: 20,
  secili: null,
  sekme: "gcode",
  cap: true,
  uzerindeSatir: -1,
  hata: null,
  yukHata: null,
  fark: null,
  dro: [0, 0, 0],
  mesgul: false,
  yuklendi: false,
};

let K: Kabuk | null = null;
let alan: HTMLElement | null = null;
let sahne: TornaSahne | null = null;
let gcode: GcodePaneli | null = null;
let devir: DevirSeridi | null = null;
let devirTuval: HTMLCanvasElement | null = null;
let buyutecKutu: HTMLDivElement | null = null;
let mufettisKap: HTMLDivElement | null = null;
let onceki: number | null = null;
let yuklemeNo = 0; // yarışan yüklemelerde yalnız sonuncusu geçerli
const temizlik: (() => void)[] = [];

const acik = () => K !== null;

// --------------------------------------------------------------------- yükleme

/**
 * İki aşama: (1) `TornaIs` gelince durum, paneller ve yol hazır; (2) nokta ve sim dizileri gelince zaman şeridi,
 * devir şeridi ve dönel kesit güncellenir. Diziler gelmezse ekran yolu ve G-code ile çalışır.
 */
async function yukle(hazirIs?: TornaIs, kameraKoru = false, islem: number | null = null): Promise<void> {
  const no = ++yuklemeNo;
  D.mesgul = true;
  let is: TornaIs;
  try {
    is = hazirIs ?? (await K!.api.getJson<TornaIs>(YOL));
  } catch (e) {
    if (no !== yuklemeNo) return;
    D.yukHata = e instanceof SunucuHatasi ? e.message : String(e);
    D.yuklendi = true;
    D.mesgul = false;
    if (acik()) panelleriCiz();
    return;
  }
  if (no !== yuklemeNo || !K) return; // bu arada başka yükleme başladı ya da ekran kapandı
  D.is = is;
  D.nk = null;
  D.sim = null;
  D.yukHata = null;
  D.renkler = is.islemler.map(islemRengi);
  const n = is.islemler.length;
  if (islem !== null && islem >= 0 && islem < n) D.secili = islem;
  else if (D.secili === null || D.secili >= n) D.secili = n ? 0 : null;
  D.t = islem !== null && D.secili !== null ? is.islemler[D.secili].t0 : Math.min(D.t, is.sure.toplam);
  sahne!.isKur(is, null, null, D.renkler, kameraKoru);
  devir!.kur(is, null);
  K.serit.bosalt();
  K.serit.dinle((t) => zamanAyarla(t, true));
  const uyari = is.kontroller.filter((k) => k.durum !== "tamam").length;
  K.rozet(AD, uyari ? `${uyari} uyarı` : null);
  D.yuklendi = true;
  D.mesgul = false;
  panelleriCiz();
  guncelle(true);
  void dizilerYukle(is);
}

/** (2) nokta ve sim dizileri; yüklenmeyen dizi null kalır. */
async function dizilerYukle(is: TornaIs): Promise<void> {
  const k = K!;
  const [nk, sim] = await Promise.all([
    k.api.getIkili(`${YOL}/noktalar`).then(tornaNoktalariCoz).catch(() => null),
    k.api.getIkili(`${YOL}/sim`).then(tornaSimCoz).catch(() => null),
  ]);
  if (D.is !== is || K !== k) return; // bu arada başka iş geldi ya da ekran kapandı
  D.nk = nk && nk.n > 0 ? nk : null;
  D.sim = sim;
  sahne!.isKur(is, D.nk, sim, D.renkler, true);
  if (D.nk) {
    const hatalar = is.kontroller
      .filter((x) => x.durum === "hata")
      .map((x) => /nokta (\d+)/.exec(x.aciklama))
      .filter((m): m is RegExpExecArray => m !== null)
      .map((m) => Number(m[1]));
    k.serit.kur(is as unknown as Is, D.nk, D.renkler, hatalar);
  }
  devir!.kur(is, D.nk);
  if (D.uzerindeSatir >= 0) satirUstunde(D.uzerindeSatir);
  else guncelle(true);
}

// --------------------------------------------------------------------- çizim

function panelleriCiz(): void {
  if (!K || !alan) return;
  const is = D.is;
  if (!is) {
    alan.innerHTML = `<section class="bolum"><h2 class="ust-baslik">Torna</h2>
      <div class="hata-kutu" role="alert"><b>Torna işi yüklenemedi</b>${kacis(D.yukHata ?? "")}</div></section>`;
    return;
  }
  solCiz();
  mufettisCiz();
  sekmeleriCiz();
  if (D.sekme === "gcode") gcode!.kur(is as unknown as Is);
  else K.kanitlar(is.kontroller);
  hudCiz();
}

function solCiz(): void {
  const is = D.is!;
  const s = is.kurulum.stok;
  const tamam = is.kontroller.filter((k) => k.durum === "tamam").length;
  const fark = D.fark;
  const kap = alan!;
  kap.innerHTML = `
    <section class="bolum">
      <h2 class="ust-baslik">Torna işi <span>${kacis(is.kurulum.wcs ?? "")}</span></h2>
      ${D.yukHata ? `<div class="hata-kutu" role="alert"><b>Sunucu</b>${kacis(D.yukHata)}</div>` : ""}
      <dl class="kv">
        <dt>Ad</dt><dd>${kacis(is.ad)}</dd>
        <dt>Malzeme</dt><dd>${kacis(is.kurulum.malzeme ?? "—")}</dd>
        <dt>Ham</dt><dd>Ø${sayi(s.D, 1)}${s.d > 0 ? ` / Ø${sayi(s.d, 1)}` : ""} × ${sayi(s.zmax - s.zmin, 1)} mm</dd>
        <dt>Devir sınırı</dt><dd>${is.sure.n_max === null || is.sure.n_max === undefined ? "—" : `G50 S${is.sure.n_max}`}</dd>
        <dt>Hareket</dt><dd>${is.hareketler.length} · ${is.gcode.length} satır</dd>
        <dt>Kanıt</dt><dd>${tamam}/${is.kontroller.length} tamam</dd>
      </dl>
      <div class="cevrim">
        <div><small>Çevrim süresi</small><span class="buyuk">${sureYaz(is.sure.toplam)}</span></div>
        <span class="fark ${fark === null ? "" : "acik"} ${fark !== null && fark <= 0 ? "iyi" : "kotu"}">${
          fark === null ? "" : `${fark <= 0 ? "−" : "+"}${Math.abs(fark).toFixed(1)} s`
        }</span>
      </div>
    </section>
    <section class="bolum">
      <h2 class="ust-baslik">İşlemler <span>${is.islemler.length}</span></h2>
      <div class="islemler"></div>
    </section>`;
  const liste = kap.querySelector<HTMLElement>(".islemler")!;
  for (const isl of is.islemler) {
    const b = document.createElement("button");
    b.className = "islem";
    b.dataset.testid = "torna-islem";
    b.dataset.islem = String(isl.i);
    b.style.setProperty("--r", islemRengi(isl));
    b.setAttribute("aria-current", String(isl.i === D.secili));
    const kip = isl.css ? `G96 Vc ${isl.css === true ? "" : isl.css}` : isl.rpm ? `G97 S${isl.rpm}` : "";
    b.innerHTML = `<span class="serit-renk"></span>
      <span class="ad"><i>${String(isl.i + 1).padStart(2, "0")}</i>${kacis(isl.ad)}</span>
      <span class="sure">${sureYaz(is.sure.islem[isl.i] ?? isl.t1 - isl.t0)}</span>
      <span class="alt"><span>T${isl.takim.T} · r ${sayi(isl.takim.r, 1)}</span><span>${kacis(kip)}</span></span>`;
    b.addEventListener("click", () => islemSec(isl.i));
    liste.appendChild(b);
  }
}

function mufettisCiz(): void {
  if (!K) return;
  const kap = (mufettisKap ??= document.createElement("div"));
  const is = D.is!;
  const isl = D.secili === null ? undefined : is.islemler[D.secili];
  if (!isl) {
    kap.innerHTML = "";
    K.mufettis(kap);
    return;
  }
  const t = isl.takim;
  const kip = isl.css ? `G96 · Vc ${isl.css === true ? "—" : isl.css} m/dk` : `G97 · ${isl.rpm ?? "—"} dev/dk`;
  kap.innerHTML = `<section class="bolum">
      <h2 class="ust-baslik">Müfettiş <span style="color:${islemRengi(isl)}">${kacis(isl.ad)}</span></h2>
      <div class="takim-kart"><svg viewBox="0 0 42 42" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
        <path d="M8 34 L20 22 L34 26 L22 38 Z" /><circle cx="10" cy="33" r="3" /><path d="M20 22 L30 6 L38 10 L34 26" /></svg>
        <div><b>T${t.T} · ${kacis(t.ad)}</b>
        <span>uç ${kacis(String(t.uc))} · burun r ${sayi(t.r, 2)} mm · ${kacis(kip)} · ${sureYaz(isl.t0)}–${sureYaz(isl.t1)}</span></div></div>
      ${D.hata ? `<div class="hata-kutu" role="alert"><b>Çekirdek reddetti</b>${kacis(D.hata)}</div>` : ""}
      <div class="kaydiricilar"></div>
    </section>`;
  const k = kap.querySelector<HTMLElement>(".kaydiricilar")!;
  for (const [anahtar, deger] of Object.entries(isl.parametreler)) {
    const a = PARAMETRE[anahtar] ?? { ad: anahtar, min: 0, max: deger * 3 || 1, adim: 0.01, birim: "" };
    const kimlik = `tp-${anahtar}`;
    const d = document.createElement("div");
    d.className = "kaydirici";
    d.innerHTML = `<label for="${kimlik}">${a.ad} <small>(${kacis(anahtar)})</small></label>
      <output for="${kimlik}">${deger} ${a.birim}</output>
      <input type="range" id="${kimlik}" data-testid="torna-parametre" data-anahtar="${kacis(anahtar)}" min="${Math.min(a.min, deger)}" max="${Math.max(a.max, deger)}" step="${a.adim}" value="${deger}">`;
    const girdi = d.querySelector("input")!;
    const cikti = d.querySelector("output")!;
    girdi.addEventListener("input", () => (cikti.textContent = `${girdi.value} ${a.birim}`));
    girdi.addEventListener("change", () => void parametreDegistir(anahtar, Number(girdi.value)));
    k.appendChild(d);
  }
  K.mufettis(kap);
}

function sekmeleriCiz(): void {
  const is = D.is!;
  const sorun = is.kontroller.filter((k) => k.durum !== "tamam").length;
  const s = $("#sekmeler");
  s.innerHTML = `<button role="tab" data-sekme="gcode" aria-selected="${D.sekme === "gcode"}">G-code <span class="sayi">${is.gcode.length}</span></button>
    <button role="tab" data-sekme="kanit" aria-selected="${D.sekme === "kanit"}">Kanıtlar <span class="sayi">${sorun ? `${sorun} sorun` : "tamam"}</span></button>`;
  s.querySelectorAll<HTMLButtonElement>("button").forEach((b) =>
    b.addEventListener("click", () => sekmeSec(b.dataset.sekme as Durum["sekme"])),
  );
}

function sekmeSec(sekme: Durum["sekme"]): void {
  D.sekme = sekme;
  if (!D.is || !K) return;
  sekmeleriCiz();
  if (sekme === "gcode") gcode!.kur(D.is as unknown as Is);
  else K.kanitlar(D.is.kontroller);
  guncelle(true);
}

function hudCiz(): void {
  const is = D.is!;
  const isl = D.secili === null ? undefined : is.islemler[D.secili];
  $("#hudBaslik").innerHTML = `<b>${kacis(isl ? isl.ad : is.ad)}</b><span>${kacis(is.ad)} · ${kacis(is.kurulum.malzeme ?? "")} · torna</span>`;
  const kesit = sahne!.kesit();
  $("#hudKatman").innerHTML = `<div class="parca" role="group" aria-label="Görünüm">
      <button data-k="kesit" aria-pressed="${kesit}" title="S">Kesit 270° <kbd>S</kbd></button>
      <button data-k="cap" aria-pressed="${D.cap}" title="R">${D.cap ? "Ø çap" : "R yarıçap"} <kbd>R</kbd></button>
    </div><div class="lejant"><span class="cizgi-ornek hedef"></span> hedef profil · <span class="cizgi-ornek"></span> ham</div>`;
  $("#hudKatman")
    .querySelectorAll<HTMLButtonElement>("button")
    .forEach((b) => b.addEventListener("click", () => (b.dataset.k === "kesit" ? kesitDegistir() : capDegistir())));
  const hatalar = is.kontroller.filter((k) => k.durum === "hata");
  $("#hudUyari").innerHTML = hatalar.length
    ? hatalar.map((k) => `<div class="uyari-kutu hata"><b>${kacis(k.baslik)}</b>${kacis(k.aciklama)}</div>`).join("")
    : `<div class="uyari-kutu tamam"><b>Kanıtlar tamam</b>${is.kontroller.length} kontrol, ihlal yok</div>`;
}

/** t anına göre takım, kesit, DRO, saat, G-code vurgusu. */
function guncelle(zorla = false): void {
  const is = D.is;
  if (!is || !K) return;
  const nk = D.nk;
  let p: Nokta3;
  let islem = D.secili ?? 0;
  let satir = -1;
  let n: number | null = null;
  if (nk) {
    const k = idxAt(D.t, nk.zaman);
    p = [nk.konum[3 * k], nk.konum[3 * k + 1], nk.konum[3 * k + 2]];
    islem = nk.islem[k];
    n = nk.devir[k];
    if (k + 1 < nk.n && nk.zaman[k + 1] > nk.zaman[k]) {
      const u = (D.t - nk.zaman[k]) / (nk.zaman[k + 1] - nk.zaman[k]);
      const hk = nk.hareket[k + 1];
      islem = nk.islem[k + 1];
      if (hk >= 0) p = tornaHareketKonum(is.hareketler[hk], u);
      else p = [0, 1, 2].map((i) => nk.konum[3 * k + i] + (nk.konum[3 * (k + 1) + i] - nk.konum[3 * k + i]) * u) as Nokta3;
    }
    satir = k + 1 < nk.n && nk.satir[k + 1] >= 0 ? nk.satir[k + 1] : nk.satir[k];
    sahne!.ilerleme(k);
    K.serit.zaman(D.t);
    devir!.zaman(D.t);
  } else {
    const h = is.hareketler[is.hareketler.length - 1];
    p = h ? [...h.b] : [0, 0, 0];
    sahne!.ilerleme(0);
  }
  sahne!.takimKonum(p, islem);
  if (D.sekme === "gcode") gcode!.vurgula(satir, D.oynuyor || zorla);
  if (D.uzerindeSatir < 0) {
    D.dro = [D.cap ? 2 * p[0] : p[0], p[1], p[2]];
    droCiz(p, satir, islem, n);
  }
  $("#saat").innerHTML = `${sureYaz(D.t)} <span>/ ${sureYaz(is.sure.toplam)}</span>`;
}

/** DRO: X çap (G-code sözcüğüyle aynı sayı) ya da yarıçap; Z; satır, ilerleme, devir. */
function droCiz(p: Nokta3, satir: number, islem: number, n: number | null, xMetin?: string): void {
  if (!K || !D.is) return;
  const is = D.is;
  const X = xMetin ?? capBicim(p[0], D.cap, ONDALIK);
  const hk = D.nk ? D.nk.hareket[Math.min(idxAt(D.t, D.nk.zaman) + 1, D.nk.n - 1)] : -1;
  const F = hk >= 0 ? is.hareketler[hk].F : null;
  $("#hudDro").innerHTML = `<div class="dro" data-test="dro">
    <div><i>${D.cap ? "XØ" : "XR"}</i><span>${X}</span></div><div><i>Z</i><span>${capBicim(p[2], false, ONDALIK)}</span></div>
    <div><i>n</i><span>${n === null ? "—" : Math.round(n)}</span></div>
    <div class="alt">${satir >= 0 ? `N${satir + 1}` : "—"} · ${F === null ? "G0 hızlı" : `F${F} mm/dev`} · T${is.islemler[islem]?.takim.T ?? "-"} · ${D.cap ? "çap" : "yarıçap"}</div></div>`;
}

function zamanAyarla(t: number, durdur: boolean): void {
  if (!D.is) return;
  if (durdur) oynat(false);
  D.t = Math.min(Math.max(t, 0), D.is.sure.toplam);
  guncelle();
}

// --------------------------------------------------------------------- etkileşim

function islemSec(i: number): void {
  if (!D.is || !K) return;
  D.secili = i;
  D.hata = null;
  zamanAyarla(D.is.islemler[i].t0, true);
  panelleriCiz();
}

function satirUstunde(satir: number): void {
  D.uzerindeSatir = satir;
  gcode?.ustundeki(satir);
  const is = D.is;
  if (!is || !K) return;
  const p = satir >= 0 ? satirUcNoktasi(satir, is.satir_hareket, is.hareketler) : null;
  const ar = satir >= 0 ? is.satir_hareket[satir] : null;
  const islem = ar ? is.hareketler[ar[1]].islem : 0;
  sahne!.hayalet(p, islem);
  if (p) {
    // DRO satırın uç noktasını gösterir; çap modunda X sunucunun DRO değeri (G-code sözcüğüyle aynı sayı)
    const sd = is.gcode[satir]?.dro;
    const X = D.cap && sd ? sd.X : D.cap ? 2 * p[0] : p[0];
    D.dro = [X, p[1], p[2]];
    droCiz(p, satir, islem, null, D.cap && sd ? capBicim(sd.X, false, ONDALIK) : undefined);
  } else {
    D.uzerindeSatir = -1;
    guncelle();
  }
}

function satiraGit(satir: number): void {
  const is = D.is;
  const nk = D.nk;
  if (!is || !nk) return;
  const ar = is.satir_hareket[satir];
  if (!ar) return;
  for (let k = 0; k < nk.n; k++) {
    if (nk.hareket[k] === ar[1]) {
      zamanAyarla(nk.zaman[k], true);
      return;
    }
  }
}

async function parametreDegistir(anahtar: string, deger: number): Promise<void> {
  if (D.mesgul || !D.is || D.secili === null || !K) return;
  D.mesgul = true;
  const islem = D.secili;
  try {
    const y = await K.api.postJson<TornaParametreYaniti>(
      `${YOL}/parametre`,
      { islem, anahtar, deger },
      `${TORNA_IS}: işlem ${islem} ${anahtar} → ${deger}`,
    );
    D.fark = y.sure_farki;
    D.hata = null;
    D.mesgul = false;
    if (K) await yukle(y.is, true);
  } catch (e) {
    D.hata = e instanceof SunucuHatasi ? e.message : String(e);
    D.mesgul = false;
    if (K && D.is) mufettisCiz();
  }
}

function kesitDegistir(): void {
  if (!sahne) return;
  sahne.kesit(!sahne.kesit());
  if (D.is && K) hudCiz();
}

function capDegistir(): void {
  D.cap = !D.cap;
  if (!D.is || !K) return;
  hudCiz();
  if (D.uzerindeSatir >= 0) satirUstunde(D.uzerindeSatir);
  else guncelle();
}

function buyutec(x: number, y: number): void {
  const kutu = buyutecKutu;
  if (!kutu) return;
  const sim = D.sim;
  const is = D.is;
  if (!sim || !is || !D.nk || !sahne) {
    kutu.hidden = true;
    return;
  }
  const q = sahne.duzlemNokta(x, y);
  const h = q ? Math.floor((q.z - sim.z0) / sim.dz) : -1;
  if (!q || h < 0 || h >= sim.nz || q.r > is.kurulum.stok.D / 2 + 5) {
    kutu.hidden = true;
    return;
  }
  const k = idxAt(D.t, D.nk.zaman);
  const { dis } = kesitAt(sim, k);
  const hedef = sim.hedef[h];
  const zc = sim.z0 + (h + 0.5) * sim.dz;
  const r = (kutu.parentElement ?? document.body).getBoundingClientRect();
  kutu.hidden = false;
  kutu.style.left = `${Math.min(x - r.left + 14, r.width - 190)}px`;
  kutu.style.top = `${Math.max(y - r.top - 70, 4)}px`;
  kutu.innerHTML = `<b>z ${capBicim(zc, false, 2)}</b>
    <span>güncel Ø ${capBicim(dis[h], true, ONDALIK)}</span>
    <span>hedef Ø ${Number.isFinite(hedef) ? capBicim(hedef, true, ONDALIK) : "—"}</span>
    <span>fark ${Number.isFinite(hedef) ? capBicim(dis[h] - hedef, true, ONDALIK) : "—"} mm</span>`;
}

// --------------------------------------------------------------------- oynatma, klavye

function oynat(acikMi: boolean): void {
  if (acikMi && D.is && D.t >= D.is.sure.toplam) D.t = 0;
  D.oynuyor = acikMi;
  if (!K) return;
  const b = $("#oynat");
  b.innerHTML = acikMi ? DURAKLAT_SVG : OYNAT_SVG;
  b.setAttribute("aria-label", acikMi ? "Duraklat (Boşluk)" : "Oynat (Boşluk)");
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

/** Ekranın kısayolları (yalnız ekran açıkken dinlenir; kabuğun Ctrl tuşlarına ve rakamlarına dokunmaz). */
function tus(e: KeyboardEvent): void {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.key === "Escape") {
    satirUstunde(-1);
    return;
  }
  const hedef = e.target as HTMLElement;
  if (hedef.matches("input, textarea, select") || hedef.isContentEditable) return;
  const k = e.key;
  if (k === "s" || k === "S") kesitDegistir();
  else if (k === "r" || k === "R") capDegistir();
  else if (k === " ") {
    if (hedef.matches("button")) return; // odaklı düğmenin kendi Boşluk davranışı
    e.preventDefault();
    oynat(!D.oynuyor);
  } else if (k === "ArrowRight" || k === "ArrowLeft") {
    e.preventDefault();
    adim(k === "ArrowRight" ? 1 : -1);
  } else if (k === "Home") zamanAyarla(0, true);
  else if (k === "End" && D.is) zamanAyarla(D.is.sure.toplam, true);
}

function dinle(el: EventTarget, tur: string, f: (e: Event) => void): void {
  el.addEventListener(tur, f);
  temizlik.push(() => el.removeEventListener(tur, f));
}

// --------------------------------------------------------------------- komutlar

function komutlar(): Komut[] {
  const is = D.is;
  const gecis: Komut[] = [
    { kimlik: "torna.git.montaj", baslik: "Montaj ekranı", anahtar_kelimeler: ["montaj", "3"], calistir: () => K?.git("#/montaj") },
    { kimlik: "torna.git.freze", baslik: "Freze ekranı", anahtar_kelimeler: ["freze", "1"], calistir: () => K?.git("#/freze") },
  ];
  if (!is) return gecis;
  const secili = D.secili;
  const isl = secili === null ? undefined : is.islemler[secili];
  const parametre: Komut[] = isl
    ? Object.keys(isl.parametreler)
        .filter((a) => a in ESANLAMLI)
        .map((a) => ({
          kimlik: `torna.parametre.${a}`,
          baslik: `${PARAMETRE[a]?.ad ?? a} (${isl.ad} · şu an ${isl.parametreler[a]})`,
          anahtar_kelimeler: ESANLAMLI[a],
          desen: `${ESANLAMLI[a][0]} <sayı>`,
          calistir: (sayi?: number) => (sayi === undefined ? undefined : parametreDegistir(a, sayi)),
          yama: (sayi: number) => [
            { bolum: "torna_isleri", isaretci: `/islem_parametreleri/${TORNA_IS}/${isl.i}/${a}`, deger: sayi },
          ],
        }))
    : [];
  return [
    ...parametre,
    {
      kimlik: "torna.kesit",
      baslik: sahne?.kesit() ? "Kesit: tam görünüm" : "Kesit: 270°",
      anahtar_kelimeler: ["kesit", "dönel kesit"],
      kisayol: "S",
      calistir: kesitDegistir,
    },
    { kimlik: "torna.cap", baslik: D.cap ? "DRO: yarıçap" : "DRO: çap", anahtar_kelimeler: ["çap", "yarıçap"], kisayol: "R", calistir: capDegistir },
    { kimlik: "torna.oynat", baslik: D.oynuyor ? "Duraklat" : "Oynat", anahtar_kelimeler: ["boşluk"], calistir: () => oynat(!D.oynuyor) },
    { kimlik: "torna.basa", baslik: "Başa dön", anahtar_kelimeler: ["home"], calistir: () => zamanAyarla(0, true) },
    { kimlik: "torna.sona", baslik: "Sona git", anahtar_kelimeler: ["end", "son kesit"], calistir: () => zamanAyarla(is.sure.toplam, true) },
    { kimlik: "torna.gcode", baslik: "G-code", anahtar_kelimeler: ["sekme"], calistir: () => sekmeSec("gcode") },
    { kimlik: "torna.kanit", baslik: "Kanıtlar", anahtar_kelimeler: ["sekme"], calistir: () => sekmeSec("kanit") },
    ...is.islemler.map((i) => ({
      kimlik: `torna.islem.${i.i}`,
      baslik: `İşlem: ${i.ad}`,
      anahtar_kelimeler: [i.anahtar, `${sureYaz(i.t0)} · T${i.takim.T}`],
      calistir: () => islemSec(i.i),
    })),
    ...gecis,
  ];
}

// --------------------------------------------------------------------- EkranModulu

/** Adres seçimi: "islem=2&fark=-1.5" (montajın "Tornada göster"i) ya da yalın işlem indeksi ("2"). */
function secimCoz(secim?: string): { islem: number | null; fark: number | null } {
  if (!secim) return { islem: null, fark: null };
  const q = new URLSearchParams(secim);
  const sayiAl = (v: string | null) => (v === null || v.trim() === "" || !Number.isFinite(Number(v)) ? null : Number(v));
  const islem = q.has("islem") ? sayiAl(q.get("islem")) : sayiAl(secim);
  return { islem: islem !== null && Number.isInteger(islem) ? islem : null, fark: sayiAl(q.get("fark")) };
}

const torna: EkranModulu = {
  ad: AD,
  baslik: "Torna",
  tus: "2",

  async ac(a: HTMLElement, k: Kabuk, secim?: string): Promise<void> {
    K = k;
    alan = a;
    D.yuklendi = false;
    sahne ??= new TornaSahne(k.sahne);
    sahne.bagla(k.sahne.katman(AD));
    gcode ??= new GcodePaneli($("#bolme"), satirUstunde, satiraGit);
    // devir şeridi: kabuğun zaman şeridinin alt şeridi (ekran kapanınca kalkar)
    devirTuval ??= Object.assign(document.createElement("canvas"), { className: "devir-tuval" });
    devirTuval.setAttribute("aria-label", "Devir şeridi: iş mili devri n(t), taralı bölgeler n_max sınırı");
    devir ??= new DevirSeridi(devirTuval, (t) => zamanAyarla(t, true));
    $("#seritKap").append(devirTuval);
    buyutecKutu ??= Object.assign(document.createElement("div"), { className: "buyutec", hidden: true });
    $("#sahneKap").append(buyutecKutu);
    // Getter kopyalansın diye defineProperties (Object.assign değeri kopyalar).
    const kancaAlanlari = {
      get hazir() {
        return D.yuklendi && !D.mesgul;
      },
      kesitAcik: () => sahne?.kesit() ?? false,
      capModu: () => D.cap,
      seciliIslem: () => D.secili,
      dro: () => [...D.dro] as Nokta3,
      hayaletKonum: () => sahne?.hayaletKonum() ?? null,
      zaman: () => D.t,
      gcodeSatirSayisi: () => D.is?.gcode.length ?? 0,
      toplamSure: () => D.is?.sure.toplam ?? 0,
    };
    Object.defineProperties(k.kanca, Object.getOwnPropertyDescriptors(kancaAlanlari));
    hizCiz();
    oynat(false);
    dinle($("#oynat"), "click", () => oynat(!D.oynuyor));
    dinle(document, "keydown", (e) => tus(e as KeyboardEvent));
    dinle(k.sahne.renderer.domElement, "pointermove", (e) => buyutec((e as PointerEvent).clientX, (e as PointerEvent).clientY));
    dinle(k.sahne.renderer.domElement, "pointerleave", () => buyutecKutu && (buyutecKutu.hidden = true));
    const { islem, fark } = secimCoz(secim);
    if (fark !== null) D.fark = fark;
    D.uzerindeSatir = -1;
    await yukle(undefined, false, islem);
  },

  kapat(): void {
    oynat(false);
    for (const f of temizlik.splice(0)) f();
    sahne?.hayalet(null, 0);
    devirTuval?.remove();
    buyutecKutu?.remove();
    if (K) {
      K.sahne.katmanBirak(AD);
      K.serit.bosalt();
    }
    yuklemeNo++; // süren yükleme sonucu çizilmez
    K = null;
    alan = null;
    D.yuklendi = false;
    D.mesgul = false;
    D.uzerindeSatir = -1;
    onceki = null;
  },

  /** Sunucu durumu dışarıdan değişti (ör. montajın parametre bağı torna işini değiştirdi). */
  async tazele(): Promise<void> {
    if (K) await yukle(undefined, true);
  },

  komutlar,

  sec(oge: string): void {
    const { islem } = secimCoz(oge);
    if (D.is && islem !== null && islem >= 0 && islem < D.is.islemler.length) islemSec(islem);
  },

  kare(t: number): void {
    const dt = onceki === null ? 0 : Math.min(t - onceki, 0.1);
    onceki = t;
    if (!D.oynuyor || !D.is) return;
    D.t += dt * D.hiz;
    if (D.t >= D.is.sure.toplam) {
      D.t = D.is.sure.toplam;
      oynat(false);
    }
    guncelle();
  },
};

export default torna;
