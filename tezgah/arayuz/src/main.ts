// SPEC 24 — ön yüz giriş noktası: durum, oynatma döngüsü, klavye, komut çubuğu, test kancası.
// SPEC 25 — kabuk: Freze / Torna / Montaj sekmeleri (1/2/3, #/freze #/torna #/montaj); torna ve montaj
// ekranları ekran_torna.ts ve ekran_montaj.ts'de. Freze ekranının durumu bu dosyada (SPEC 24).

import "./stil.css";

import { SunucuHatasi, isAl, isListesi, noktalarAl, parametreGonder, simAl } from "./api";
import { hareketSatir, satirUcNoktasi } from "./gcode";
import { MontajEkrani } from "./ekran_montaj";
import { TornaEkrani } from "./ekran_torna";
import type { TezgahKanca } from "./kanca";
import { DURAKLAT_SVG, type Komut, OYNAT_SVG, anahtarSayi } from "./komut";
import { GcodePaneli, PARAMETRE, islemRengi, kanitlarCiz, mufettisCiz, sayi, solCiz } from "./paneller";
import { type Katman, Sahne } from "./sahne";
import { Serit, sureYaz } from "./serit";
import type { EkranAdi, Is, Nokta3, Noktalar, SimVeri } from "./tipler";
import { hareketKonum } from "./yol";
import { idxAt } from "./zaman";

const $ = <T extends HTMLElement = HTMLElement>(s: string) => document.querySelector<T>(s)!;

const ALANLAR = [
  { kimlik: "freze", ad: "Freze", hazir: true, tus: "1" },
  { kimlik: "torna", ad: "Torna", hazir: true, tus: "2" },
  { kimlik: "montaj", ad: "Montaj", hazir: true, tus: "3" },
  { kimlik: "modelleme", ad: "Modelleme", hazir: false, not: "eskiz → ekstrüzyon", tus: "" },
];
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

const sahne = new Sahne($("#gorunum"));
const serit = new Serit($<HTMLCanvasElement>("#seritTuval"), (t) => zamanAyarla(t, true));
const gcode = new GcodePaneli($("#bolme"), satirUstunde, satiraGit);

// --------------------------------------------------------------------- yükleme

async function yukle(ad: string, kameraKoru = false, hazirIs?: Is): Promise<void> {
  D.mesgul = true;
  const [is, nk, sim] = await Promise.all([hazirIs ?? isAl(ad), noktalarAl(ad), simAl(ad).catch(() => null)]);
  D.ad = ad;
  D.is = is;
  D.nk = nk;
  D.sim = sim;
  D.renkler = is.islemler.map(islemRengi);
  D.hareketSatiri = hareketSatir(is.satir_hareket, is.hareketler.length);
  D.t = Math.min(D.t, is.sure.toplam);
  D.secili = Math.min(D.secili, is.islemler.length - 1);
  sahne.isKur(is, nk, sim, D.renkler, kameraKoru);
  const hatalar = is.kontroller.filter((k) => k.durum === "hata").map((k) => kontrolNoktasi(k.aciklama));
  serit.kur(is, nk, D.renkler, hatalar.filter((k): k is number => k !== null));
  if (gosterilen === "freze") {
    if (D.sekme === "gcode") gcode.kur(is);
    panelleriCiz();
  }
  guncelle(true);
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
  if (!D.is || gosterilen !== "freze") return;
  sekmeleriCiz();
  if (sekme === "gcode") gcode.kur(D.is!);
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
  sahne.katman(k);
  hudCiz();
  guncelle(true);
}

/** t anına göre takım, yüzey, DRO, saat, G-code vurgusu. */
function guncelle(zorla = false): void {
  const is = D.is;
  const nk = D.nk;
  if (!is || !nk) return;
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
  sahne.takimKonum(p, islem);
  sahne.ilerleme(k);
  serit.zaman(D.t);
  const satir = k + 1 < nk.n && nk.satir[k + 1] >= 0 ? nk.satir[k + 1] : nk.satir[k];
  if (D.sekme === "gcode" && gosterilen === "freze") gcode.vurgula(satir, D.oynuyor || zorla);
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
  D.uzerindeSatir = satir;
  gcode.ustundeki(satir);
  const is = D.is;
  if (!is) return;
  const p = satir >= 0 ? satirUcNoktasi(satir, is.satir_hareket, is.hareketler) : null;
  const ar = satir >= 0 ? is.satir_hareket[satir] : null;
  sahne.hayalet(p, ar ? is.hareketler[ar[1]].islem : 0);
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
    if (gosterilen === "freze") mufettisCiz($("#mufettis"), D.is!, D.secili, D.hata, parametreDegistir);
  }
}


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

let onceki = performance.now();
function dongu(simdi: number): void {
  const dt = Math.min((simdi - onceki) / 1000, 0.1);
  onceki = simdi;
  torna.kare(dt);
  montaj.kare(dt);
  if (D.oynuyor && D.is) {
    D.t += dt * D.hiz;
    if (D.t >= D.is.sure.toplam) {
      D.t = D.is.sure.toplam;
      oynat(false);
    }
    guncelle();
  }
  requestAnimationFrame(dongu);
}

// --------------------------------------------------------------------- komut çubuğu


const ESANLAMLI: Record<string, string> = {
  cap: "D",
  çap: "D",
  takim: "D",
  takım: "D",
  d: "D",
  paso: "ap",
  derinlik: "ap",
  ap: "ap",
  ilerleme: "F",
  f: "F",
  devir: "rpm",
  s: "rpm",
  rpm: "rpm",
  adim: "stepover",
  adım: "stepover",
  stepover: "stepover",
  gagalama: "q",
  q: "q",
};

/** Kabuk komutları (her ekranda): ekran geçişi, bağlı parametre ("L 9.5"), "patlat", "kesit". */
function kabukKomutlari(sorgu: string): Komut[] {
  const out: Komut[] = [];
  const as = anahtarSayi(sorgu);
  if (as && as.anahtar === "l") {
    out.push({
      ad: `L = ${as.deger}`,
      aciklama: "kademeli_mil uç boyu · montaj bağıyla torna işi ve montaj yeniden hesaplanır",
      calistir: () => void montaj.parametreAyarla("L", as.deger),
      dinamik: true,
    });
  }
  const sabit: Komut[] = [
    ...ALANLAR.filter((a) => a.hazir).map((a) => ({
      ad: a.ad,
      aciklama: `çalışma alanı · ${a.tus}`,
      calistir: () => ekranIste(a.kimlik as EkranAdi),
    })),
    {
      ad: "Patlat",
      aciklama: "montaj · E",
      calistir: () => {
        ekranIste("montaj");
        void ekranHazir("montaj").then(() => montaj.patlat());
      },
    },
    {
      ad: "Kesit",
      aciklama: "torna · S · 270° kesit / tam",
      calistir: () => {
        if (gosterilen === "torna") torna.kesitDegistir();
        else {
          ekranIste("torna");
          void ekranHazir("torna").then(() => torna.kesitDegistir());
        }
      },
    },
  ];
  const q = sorgu.trim().toLocaleLowerCase("tr");
  return out.concat(sabit.filter((k) => !q || `${k.ad} ${k.aciklama}`.toLocaleLowerCase("tr").includes(q)));
}

function komutlar(sorgu: string): Komut[] {
  const q = sorgu.trim().toLocaleLowerCase("tr");
  const suz = (ks: Komut[]) =>
    ks.filter((k) => k.dinamik || !q || `${k.ad} ${k.aciklama}`.toLocaleLowerCase("tr").includes(q));
  const ekran =
    gosterilen === "torna" ? suz(torna.komutlar(sorgu)) : gosterilen === "montaj" ? suz(montaj.komutlar()) : frezeKomutlari(sorgu);
  const dinamik = ekran.filter((k) => k.dinamik);
  return dinamik.concat(kabukKomutlari(sorgu), ekran.filter((k) => !k.dinamik));
}

function frezeKomutlari(sorgu: string): Komut[] {
  const is = D.is;
  if (!is) return [];
  const out: Komut[] = [];
  const m = /^\s*([^\d\s-]+)\s*(-?\d+(?:[.,]\d+)?)\s*$/.exec(sorgu.toLocaleLowerCase("tr"));
  const isl = is.islemler[D.secili];
  if (m) {
    const anahtar = ESANLAMLI[m[1]];
    const deger = Number(m[2].replace(",", "."));
    if (anahtar && isl && anahtar in isl.parametreler) {
      out.push({
        ad: `${PARAMETRE[anahtar]?.ad ?? anahtar} = ${deger}`,
        aciklama: `${isl.ad} · şu an ${isl.parametreler[anahtar]}`,
        calistir: () => parametreDegistir(anahtar, deger),
        dinamik: true,
      });
    }
  }
  const sabit: Komut[] = [
    { ad: D.oynuyor ? "Duraklat" : "Oynat", aciklama: "Boşluk", calistir: () => oynat(!D.oynuyor) },
    { ad: "Başa dön", aciklama: "Home", calistir: () => zamanAyarla(0, true) },
    { ad: "Sona git", aciklama: "End · son yüzey", calistir: () => zamanAyarla(is.sure.toplam, true) },
    { ad: "Katman: işlem", aciklama: "yüzey işlem rengiyle", calistir: () => katmanSec("islem") },
    { ad: "Katman: takım yükü", aciklama: "talaş kaldırma hızı", calistir: () => katmanSec("yuk") },
    { ad: "G-code", aciklama: "sekme", calistir: () => sekmeSec("gcode") },
    { ad: "Kanıtlar", aciklama: "sekme", calistir: () => sekmeSec("kanit") },
    ...is.islemler.map((i) => ({
      ad: `İşlem: ${i.ad}`,
      aciklama: `${sureYaz(i.t0)} · T${i.takim.T}`,
      calistir: () => islemSec(i.i),
    })),
  ];
  const q = sorgu.trim().toLocaleLowerCase("tr");
  return out.concat(sabit.filter((k) => !q || `${k.ad} ${k.aciklama}`.toLocaleLowerCase("tr").includes(q)));
}

let paletSecili = 0;
let paletListe: Komut[] = [];
let paletOnceki: HTMLElement | null = null;

function paletAc(): void {
  paletOnceki = document.activeElement as HTMLElement | null;
  $("#perde").hidden = false;
  const g = $<HTMLInputElement>("#paletGirdi");
  g.value = "";
  g.placeholder = "Komut yaz: torna · montaj · L 9.5 · paso 2 · patlat · kesit · sona git";
  paletDoldur();
  g.focus();
}

function paletKapat(): void {
  $("#perde").hidden = true;
  paletOnceki?.focus();
}

function paletDoldur(): void {
  paletListe = komutlar($<HTMLInputElement>("#paletGirdi").value);
  paletSecili = Math.min(paletSecili, Math.max(paletListe.length - 1, 0));
  const ul = $("#paletListe");
  ul.innerHTML = paletListe
    .map(
      (k, i) =>
        `<li role="option" data-i="${i}" aria-selected="${i === paletSecili}" class="${k.dinamik ? "dinamik" : ""}"><b>${k.ad}</b><span>${k.aciklama}</span></li>`,
    )
    .join("");
  ul.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
}

function paletCalistir(i: number): void {
  const k = paletListe[i];
  paletKapat();
  k?.calistir();
}

$("#paletGirdi").addEventListener("input", () => {
  paletSecili = 0;
  paletDoldur();
});
$("#paletGirdi").addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    const n = paletListe.length;
    if (n) paletSecili = (paletSecili + (e.key === "ArrowDown" ? 1 : n - 1)) % n;
    paletDoldur();
  } else if (e.key === "Enter") {
    e.preventDefault();
    paletCalistir(paletSecili);
  }
});
$("#paletListe").addEventListener("click", (e) => {
  const li = (e.target as HTMLElement).closest<HTMLElement>("[data-i]");
  if (li) paletCalistir(Number(li.dataset.i));
});
$("#perde").addEventListener("click", (e) => e.target === $("#perde") && paletKapat());
$("#komutDugme").addEventListener("click", paletAc);

// --------------------------------------------------------------------- klavye

document.addEventListener("keydown", (e) => {
  const paletAcik = !$("#perde").hidden;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    if (paletAcik) paletKapat();
    else paletAc();
    return;
  }
  if (e.key === "Escape" && paletAcik) {
    paletKapat();
    return;
  }
  if (paletAcik) return;
  const hedef = e.target as HTMLElement;
  if (hedef.matches("input, textarea, select") || hedef.isContentEditable) return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const alan = ALANLAR.find((a) => a.hazir && a.tus === e.key);
  if (alan) {
    ekranIste(alan.kimlik as EkranAdi);
    return;
  }
  if (gosterilen === "torna") {
    torna.tus(e, hedef);
    return;
  }
  if (gosterilen === "montaj") {
    montaj.tus(e, hedef);
    return;
  }
  if (e.key === "Escape") satirUstunde(-1);
  else if (e.key === " ") {
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
});

// --------------------------------------------------------------------- kurulum

// --------------------------------------------------------------------- kabuk: ekranlar

const torna = new TornaEkrani();
const montaj = new MontajEkrani(torna);

/** DOM'da gösterilen ekran ve yüklenip kancaya bildirilen ekran (yükleme bitince `gosterilen`e eşitlenir). */
let gosterilen: EkranAdi = "freze";
let aktif: EkranAdi = "freze";
let gecis: Promise<void> = Promise.resolve();

function hashEkran(): EkranAdi {
  const m = /^#\/(freze|torna|montaj)\b/.exec(location.hash);
  return m ? (m[1] as EkranAdi) : "freze";
}

/** Ekran geçişi adres üzerinden: #/ad (geri tuşu da çalışır). */
function ekranIste(ad: EkranAdi): void {
  if (hashEkran() === ad && location.hash.startsWith("#/")) return;
  location.hash = `#/${ad}`;
}

/** `ad` ekranı açılıp yüklenince çözülür. */
async function ekranHazir(ad: EkranAdi): Promise<void> {
  for (let i = 0; i < 600 && !(aktif === ad && gosterilen === ad && ekranYuklendi(ad)); i++) {
    await new Promise((r) => setTimeout(r, 50));
  }
}

function ekranYuklendi(ad: EkranAdi): boolean {
  if (ad === "torna") return torna.hazir;
  if (ad === "montaj") return montaj.hazir;
  return D.hazir && !D.mesgul;
}

function ekranAc(ad: EkranAdi): void {
  if (ad === gosterilen) {
    alanlariCiz();
    return;
  }
  const onceki = gosterilen;
  gosterilen = ad;
  // eskiyi kapat (dinamik paneller boşalır: test kimlikleri tek kalır), yeniyi göster
  if (onceki === "freze") frezeKapat();
  else if (onceki === "torna") torna.kapat();
  else montaj.kapat();
  document.querySelectorAll<HTMLElement>("[data-ekran]").forEach((el) => (el.hidden = el.dataset.ekran !== ad));
  alanlariCiz();
  gecis = gecis.then(async () => {
    if (gosterilen !== ad) return;
    if (ad === "torna") await torna.ac();
    else if (ad === "montaj") await montaj.ac();
    else frezeAc();
    if (gosterilen === ad) aktif = ad;
  });
}

function frezeKapat(): void {
  oynat(false);
  satirUstunde(-1);
  for (const s of ["#sol", "#mufettis", "#sekmeler", "#bolme"]) $(s).innerHTML = "";
}

function frezeAc(): void {
  if (!D.is) return;
  panelleriCiz();
  sekmeSec(D.sekme);
}

function alanlariCiz(): void {
  $("#alanlar").innerHTML = ALANLAR.map(
    (a) =>
      `<button role="tab" data-testid="sekme" data-sekme="${a.kimlik}" aria-selected="${a.kimlik === gosterilen}" ${
        a.hazir ? `title="${a.ad} (${a.tus})"` : `disabled title="Sonraki adım: ${a.not}"`
      }>${a.ad}${a.tus ? ` <kbd>${a.tus}</kbd>` : ""}</button>`,
  ).join("");
  $("#alanlar")
    .querySelectorAll<HTMLButtonElement>("button[data-sekme]")
    .forEach((b) => b.addEventListener("click", () => ekranIste(b.dataset.sekme as EkranAdi)));
}

const tk = torna.kanca();
const mk = montaj.kanca();
const kanca: TezgahKanca = {
  get hazir() {
    return D.hazir && !D.mesgul && hashEkran() === gosterilen && aktif === gosterilen && ekranYuklendi(aktif);
  },
  ekran: () => aktif,
  kesitAcik: tk.kesitAcik,
  capModu: tk.capModu,
  seciliIslem: tk.seciliIslem,
  montajU: mk.montajU,
  montajPoz: mk.montajPoz,
  hayaletKonum: () => (aktif === "torna" ? tk.hayaletKonum() : sahne.hayaletKonum()),
  dro: () => (aktif === "torna" ? tk.dro() : ([...D.dro] as Nokta3)),
  zaman: () => (aktif === "torna" ? tk.zaman() : D.t),
  gcodeSatirSayisi: () => (aktif === "torna" ? tk.gcodeSatirSayisi() : ((D.gelenIs ?? D.is)?.gcode.length ?? 0)),
  toplamSure: () => (aktif === "torna" ? tk.toplamSure() : ((D.gelenIs ?? D.is)?.sure.toplam ?? 0)),
  yuzey: () => sahne.yuzey(),
};
window.__tezgah = kanca;
window.addEventListener("hashchange", () => ekranAc(hashEkran()));

async function basla(): Promise<void> {
  alanlariCiz();
  hizCiz();
  oynat(false);
  $("#oynat").addEventListener("click", () => oynat(!D.oynuyor));
  setTimeout(() => $("#ipucu").style.setProperty("opacity", "0"), 7000);
  ekranAc(hashEkran());
  try {
    const isler = await isListesi();
    if (!isler.length) throw new Error("Sunucuda iş yok");
    await yukle(isler[0]);
  } catch (e) {
    $("#gorunum").innerHTML = `<div class="yukleniyor" role="alert">Sunucuya ulaşılamadı: ${String(e)}</div>`;
  }
  requestAnimationFrame(dongu);
}

void basla();
