// A3 — Tezgah kabuğu: üst sekmeler (/api/ekranlar ∩ src/ekranlar/*.ts), adres (#/<ad>?secim),
// sekme tuşları, Ctrl K komut paleti, animasyon döngüsü ve test kancası. Ekrana özgü kod src/ekranlar/'dadır.

import "./stil.css";

import { SunucuHatasi, degisiklikSonrasi, ekranApi } from "./api";
import { ekranlariSirala, kayitliModuller, kisayolDogrula } from "./ekranlar/kayit";
import type { EkranModulu, Kabuk, Komut, Sekme, SunucuEkrani } from "./ekranlar/tip";
import type { TezgahKanca } from "./kanca";
import { kanitlarCiz } from "./paneller";
import { Sahne } from "./sahne";
import { Serit } from "./serit";
import type { Nokta3 } from "./tipler";

const $ = <T extends HTMLElement = HTMLElement>(s: string) => document.querySelector<T>(s)!;

const sahne = new Sahne($("#gorunum"));
const serit = new Serit($<HTMLCanvasElement>("#seritTuval"));

let sekmeler: Sekme[] = [];
let etkin: Sekme | null = null;
let aciliyor = false; // etkin ekranın ac()'ı sürüyor
let acilis = 0; // yarışan sekme değişimlerinde yalnız sonuncusu geçerli
let kabukHazir = false;
let dinamikKomutlar: Komut[] = [];
/** SPEC 37 kabuğu (src/ekranlar/kabuk.ts) yüklendiyse paleti ve Ctrl kısayollarını o üstlenir. */
let projeKabugu = false;

interface KabukModulu {
  baslat(kabuk: Kabuk, komutlar: () => Komut[], tazele: () => Promise<void>): void;
  ekranDegisti(): Promise<void>;
}

// Dosya yoksa (SPEC 37 birleşmeden) eşleme boştur: kabuk yüklenmez, eski komut çubuğu çalışır.
const KABUK_DOSYASI = import.meta.glob<KabukModulu>("./ekranlar/kabuk.ts");
const rozetler = new Map<string, string>();

// --------------------------------------------------------------------- test kancası

/** SPEC 24 kanca alanları freze ekranının kancasına (window.__tezgah.freze) gider. */
function freze<T>(alan: string, yedek: T): T {
  const f = (kanca.freze as Record<string, unknown> | undefined)?.[alan];
  return typeof f === "function" ? (f as () => T)() : yedek;
}

const kanca: TezgahKanca = {
  get hazir() {
    if (!kabukHazir || !etkin || aciliyor) return false;
    // Adres başka ekranı gösteriyorsa (hashchange henüz işlenmedi) önceki ekranın sinyali geçmez.
    const a = adresCoz();
    if (a && a.ad !== etkin.ad) return false;
    const h = (kanca[etkin.ad] as Record<string, unknown> | undefined)?.hazir;
    return h === undefined ? true : h === true;
  },
  hayaletKonum: () => freze<Nokta3 | null>("hayaletKonum", null),
  dro: () => freze<Nokta3>("dro", [0, 0, 0]),
  zaman: () => freze("zaman", 0),
  gcodeSatirSayisi: () => freze("gcodeSatirSayisi", 0),
  toplamSure: () => freze("toplamSure", 0),
  yuzey: () => freze<Float32Array | null>("yuzey", null),
  katmanlar: () => sahne.katmanlar(),
};
window.__tezgah = kanca;

/** Ekranın e2e kancası (window.__tezgah.<ad>). */
function ekranKancasi(ad: string): Record<string, unknown> {
  let k = kanca[ad] as Record<string, unknown> | undefined;
  if (!k) {
    k = {};
    kanca[ad] = k;
  }
  return k;
}

// --------------------------------------------------------------------- kabuk servisleri

function kabukFor(ad: string): Kabuk {
  return {
    sahne,
    serit,
    kanitlar: (k) => kanitlarCiz($("#bolme"), k),
    mufettis: (alan) => $("#mufettis").replaceChildren(alan),
    komut: (k) => {
      if (k.kisayol) kisayolDogrula(k.kisayol);
      dinamikKomutlar = dinamikKomutlar.filter((d) => d.kimlik !== k.kimlik).concat({ ...k, ekran: k.ekran ?? ad });
    },
    git: (adres) => {
      location.hash = adres.startsWith("#") ? adres : `#${adres}`;
    },
    rozet: (ekran, metin) => {
      if (metin === null) rozetler.delete(ekran);
      else rozetler.set(ekran, metin);
      sekmeleriCiz();
    },
    kanca: ekranKancasi(ad),
    api: ekranApi(ad),
  };
}

/** Ekranın kendi kısayolları kabuğunkilerle çakışamaz (§3: yüklemede Error). */
function komutKisayollari(m: EkranModulu): void {
  for (const k of m.komutlar?.() ?? []) if (k.kisayol) kisayolDogrula(k.kisayol);
}

// --------------------------------------------------------------------- sekmeler ve adres

function sekmeleriCiz(): void {
  const nav = $("#alanlar");
  nav.replaceChildren();
  for (const s of sekmeler) {
    const b = document.createElement("button");
    b.setAttribute("role", "tab");
    b.setAttribute("data-testid", "ekran-sekmesi");
    b.dataset.ekran = s.ad;
    b.setAttribute("aria-selected", String(etkin?.ad === s.ad));
    // SPEC 37 e2e işaretleri: içteki `sekme` (data-ekran) ve onun içindeki `rozet`.
    const ic = document.createElement("span");
    ic.setAttribute("data-testid", "sekme");
    ic.dataset.ekran = s.ad;
    ic.textContent = s.baslik;
    const rozet = rozetler.get(s.ad);
    if (rozet) {
      const r = document.createElement("span");
      r.className = "rozet";
      r.setAttribute("data-testid", "rozet");
      r.textContent = rozet;
      ic.append(" ", r);
    }
    b.append(ic);
    if (s.tus) b.title = `${s.baslik} (${s.tus})`;
    if (!s.acik) {
      b.setAttribute("aria-disabled", "true");
      b.title = s.neden ?? "Kullanılamıyor";
    } else b.addEventListener("click", () => git(s.ad));
    nav.append(b);
  }
}

function git(ad: string, secim?: string): void {
  location.hash = `#/${ad}${secim ? `?${secim}` : ""}`;
}

function adresCoz(): { ad: string; secim?: string } | null {
  const m = /^#\/([a-z][a-z0-9_]*)(?:\?(.*))?$/.exec(location.hash);
  return m ? { ad: m[1], secim: m[2] } : null;
}

/** Ekran alanlarını boşaltır (bir ekranın çizdiği paneller sonrakine kalmasın). */
function alanlariBosalt(): void {
  for (const id of ["sol", "mufettis", "sekmeler", "bolme", "hudBaslik", "hudKatman", "hudDro", "hudUyari"]) {
    $(`#${id}`).replaceChildren();
  }
  $("#saat").innerHTML = "0:00 <span>/ 0:00</span>";
}

function hataGoster(metin: string): void {
  const d = document.createElement("div");
  d.className = "yukleniyor";
  d.setAttribute("role", "alert");
  d.textContent = metin;
  $("#sol").replaceChildren(d);
}

async function adresiUygula(): Promise<void> {
  const a = adresCoz();
  const hedef = a ? sekmeler.find((s) => s.ad === a.ad && s.acik) : undefined;
  if (!hedef) {
    const ilk = sekmeler.find((s) => s.acik);
    if (!ilk) return;
    history.replaceState(null, "", `#/${ilk.ad}`);
    if (etkin?.ad !== ilk.ad) await ac(ilk);
    return;
  }
  if (etkin?.ad === hedef.ad) {
    if (a?.secim) hedef.modul?.sec?.(new URLSearchParams(a.secim).get("is") ?? a.secim);
    return;
  }
  await ac(hedef, a?.secim);
}

async function ac(s: Sekme, secim?: string): Promise<void> {
  const no = ++acilis;
  if (etkin) {
    etkin.modul?.kapat();
    sahne.katmanBirak(etkin.ad); // ekran unutsa da katmanı kalkar
    const onceki = etkin.ad;
    dinamikKomutlar = dinamikKomutlar.filter((k) => k.ekran !== onceki);
  }
  alanlariBosalt();
  etkin = s;
  sekmeleriCiz();
  aciliyor = true;
  try {
    await s.modul!.ac($("#sol"), kabukFor(s.ad), secim);
  } catch (e) {
    if (no !== acilis) return;
    hataGoster(`${s.baslik} açılamadı: ${e instanceof SunucuHatasi ? e.message : String(e)}`);
  } finally {
    if (no === acilis) aciliyor = false; // yalnız son açılış bayrağı indirir
  }
}

// --------------------------------------------------------------------- komut paleti

interface Satir {
  baslik: string;
  aciklama: string;
  dinamik: boolean;
  calistir: () => void | Promise<void>;
}

const kucuk = (s: string) => s.toLocaleLowerCase("tr");

function paletKomutlari(): Komut[] {
  return [...(etkin?.modul?.komutlar?.() ?? []), ...dinamikKomutlar.filter((k) => k.ekran === etkin?.ad)];
}

/** "çap 12": desenli komutun sözcüğü ya da anahtar kelimesi + sayı → sayıyla çalışan satır. */
function satirlar(sorgu: string): Satir[] {
  const K = paletKomutlari();
  const out: Satir[] = [];
  const m = /^\s*(.*?)\s*(-?\d+(?:[.,]\d+)?)\s*$/.exec(kucuk(sorgu));
  if (m && m[1]) {
    const soz = m[1];
    const sayi = Number(m[2].replace(",", "."));
    for (const k of K) {
      if (!k.desen) continue;
      const desenSoz = kucuk(k.desen.replace("<sayı>", "").trim());
      if (desenSoz === soz || (k.anahtar_kelimeler ?? []).some((a) => kucuk(a) === soz)) {
        out.push({
          baslik: `${k.baslik.replace(/ \(.*\)$/, "")} = ${sayi}`,
          aciklama: k.baslik,
          dinamik: true,
          calistir: () => k.calistir(sayi),
        });
      }
    }
  }
  const q = kucuk(sorgu.trim());
  for (const k of K) {
    if (k.desen) continue; // sayı ister: yalnız sayıyla yazılınca listelenir
    const ek = k.anahtar_kelimeler ?? [];
    const metin = kucuk([k.baslik, ...ek, k.kisayol ?? ""].join(" "));
    if (!q || metin.includes(q)) {
      out.push({ baslik: k.baslik, aciklama: k.kisayol ?? ek[ek.length - 1] ?? "", dinamik: false, calistir: () => k.calistir() });
    }
  }
  return out;
}

let paletSecili = 0;
let paletListe: Satir[] = [];
let paletOnceki: HTMLElement | null = null;

const paletAcik = () => !$("#perde").hidden;

function paletAc(): void {
  paletOnceki = document.activeElement as HTMLElement | null;
  $("#perde").hidden = false;
  const g = $<HTMLInputElement>("#paletGirdi");
  g.value = "";
  g.placeholder = "Komut yaz: çap 12 · paso 2 · ilerleme 900 · cep · sona git";
  paletSecili = 0;
  paletDoldur();
  g.focus();
}

function paletKapat(): void {
  $("#perde").hidden = true;
  paletOnceki?.focus();
}

function paletDoldur(): void {
  paletListe = satirlar($<HTMLInputElement>("#paletGirdi").value);
  paletSecili = Math.min(paletSecili, Math.max(paletListe.length - 1, 0));
  const ul = $("#paletListe");
  ul.replaceChildren(
    ...paletListe.map((k, i) => {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.dataset.i = String(i);
      li.setAttribute("aria-selected", String(i === paletSecili));
      if (k.dinamik) li.className = "dinamik";
      const b = document.createElement("b");
      b.textContent = k.baslik;
      const s = document.createElement("span");
      s.textContent = k.aciklama;
      li.append(b, s);
      return li;
    }),
  );
  ul.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
}

function paletCalistir(i: number): void {
  const k = paletListe[i];
  paletKapat();
  if (k) void Promise.resolve(k.calistir()).catch((e) => console.warn("Komut çalışmadı:", e));
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
$("#komutDugme").addEventListener("click", () => {
  if (projeKabugu) window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }));
  else paletAc();
});

// --------------------------------------------------------------------- klavye (kabuk)

// Kabuk dinleyicisi ekranlarınkinden önce kurulur: palet açıkken tuşlar ekranlara gitmez.
document.addEventListener("keydown", (e) => {
  if (projeKabugu && (e.ctrlKey || e.metaKey)) return; // Ctrl K/Z/Y/S/O kabuğundur
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "k") {
    e.preventDefault();
    e.stopImmediatePropagation();
    if (paletAcik()) paletKapat();
    else paletAc();
    return;
  }
  if (paletAcik()) {
    if (e.key === "Escape") paletKapat();
    e.stopImmediatePropagation();
    return;
  }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const hedef = e.target as HTMLElement;
  if (hedef.matches("input, textarea, select") || hedef.isContentEditable) return;
  if (/^[0-9]$/.test(e.key)) {
    const s = sekmeler.find((x) => x.tus === e.key);
    if (s?.acik) {
      e.preventDefault();
      e.stopImmediatePropagation();
      git(s.ad);
    }
  }
});

// --------------------------------------------------------------------- döngü ve kurulum

function dongu(simdi: number): void {
  etkin?.modul?.kare?.(simdi / 1000);
  requestAnimationFrame(dongu);
}

/** SPEC 37 kabuğu varsa bir kez başlatılır; ekranların değişiklikleri ona bildirilir. */
async function projeKabugunuBaslat(): Promise<void> {
  const yukle = KABUK_DOSYASI["./ekranlar/kabuk.ts"];
  if (!yukle) return;
  const m = await yukle();
  projeKabugu = true;
  m.baslat(kabukFor("kabuk"), paletKomutlari, async () => {
    await etkin?.modul?.tazele?.();
  });
  degisiklikSonrasi(() => void m.ekranDegisti());
}

async function basla(): Promise<void> {
  setTimeout(() => $("#ipucu").style.setProperty("opacity", "0"), 7000);
  try {
    const moduller = kayitliModuller();
    for (const m of moduller) komutKisayollari(m);
    const r = await fetch("/api/ekranlar");
    if (!r.ok) throw new SunucuHatasi(r.status, `${r.status} ${r.statusText}`);
    const sunucu: SunucuEkrani[] = (await r.json()).ekranlar;
    const adlar = new Set(sunucu.map((s) => s.ad));
    for (const m of moduller) {
      if (!adlar.has(m.ad) && m.ad !== "kabuk") console.warn(`Tezgah: '${m.ad}' ekranının ön yüzü var ama sunucuda yok; gösterilmiyor.`);
    }
    sekmeler = ekranlariSirala(sunucu, moduller);
    sekmeleriCiz();
    addEventListener("hashchange", () => void adresiUygula());
    await projeKabugunuBaslat();
    await adresiUygula();
    kabukHazir = true;
  } catch (e) {
    hataGoster(`Sunucuya ulaşılamadı: ${String(e)}`);
  }
  requestAnimationFrame(dongu);
}

void basla();
