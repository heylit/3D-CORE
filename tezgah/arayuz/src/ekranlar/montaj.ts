// SPEC 25 — montaj ekranı (A3: src/ekranlar/montaj.ts). Ağaç + serbestlik çipleri, BOM ve kütle, montaj sırası
// şeridi (patlat / topla), girişim (iplik) kartı: Öner → Uygula → torna işinin süre farkı ve "Tornada göster".
// Dönüşümler, serbestlik, girişim, öneri sunucudan (/api/ekran/montaj/…); burada yalnız u ara değeri (sira.ts)
// ve biçim var. Torna ekranının modülünü import etmez: "Tornada göster" adresle (#/torna?islem=…) gider.

import { SunucuHatasi } from "../api";
import { sayi } from "../paneller";
import { MontajSahne } from "../sahne_montaj";
import { type Mat4, type Serbestlik, adimU, cip, poz } from "../sira";
import { type Ag, type Bag, type Montaj, type MontajDugum, type MontajParametreYaniti, type Oneri, type TornaIs, agCoz } from "../tipler_25";
import type { EkranModulu, Kabuk, Komut } from "./tip";

const AD = "montaj";
const MONTAJ = "yatak_grubu";
const ONEK = `/api/ekran/${AD}/`; // sunucunun mutlak ağ adresleri bu önekle gelir
const PATLAT_HIZ = 1.2; // tam şerit / s (E)
const OYNAT_HIZ = 0.8; // adım / s (Boşluk)

const $ = <T extends HTMLElement = HTMLElement>(s: string) => document.querySelector<T>(s)!;
const kacis = (s: string) =>
  s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

const OYNAT_SVG = `<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M4 2.5v11l9-5.5z"/></svg>`;
const DURAKLAT_SVG = `<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M3.5 2.5h3v11h-3zM9.5 2.5h3v11h-3z"/></svg>`;

/** Sunucu 4x4'ü düz (16) ya da iç içe gönderebilir: düz satır öncelikli diziye. */
const duz = (T: number[] | number[][]): Mat4 => (T as (number | number[])[]).flat() as number[];

/** Ekranın API'sine göre yol: mutlak "/api/ekran/montaj/…" adresinin öneki atılır. */
const goreli = (adres: string) => (adres.startsWith(ONEK) ? adres.slice(ONEK.length) : adres);

/** Torna işinde değişen ilk işlem: işlem süresi, parametreleri ya da G-code satırları farklı olan. */
function degisenIslem(eski: TornaIs | null, yeni: TornaIs): number | null {
  const n = yeni.islemler.length;
  if (!n) return null;
  if (!eski) return null;
  for (let i = 0; i < n; i++) {
    const a = eski.islemler[i];
    const b = yeni.islemler[i];
    if (!a || eski.sure.islem[i] !== yeni.sure.islem[i]) return i;
    if (JSON.stringify(a.parametreler) !== JSON.stringify(b.parametreler)) return i;
    const sa = eski.gcode.filter((g) => g.islem === i).map((g) => g.metin);
    const sb = yeni.gcode.filter((g) => g.islem === i).map((g) => g.metin);
    if (sa.join("\n") !== sb.join("\n")) return i;
  }
  return null;
}

/** Bağlı torna işinin güncel `Is`'i (yalnız okuma, salt veri: /api/ekran/torna/is/<ad>). Okunamazsa null. */
async function tornaIsiOku(ad: string): Promise<TornaIs | null> {
  try {
    const r = await fetch(`/api/ekran/torna/is/${encodeURIComponent(ad)}`);
    return r.ok ? ((await r.json()) as TornaIs) : null;
  } catch {
    return null;
  }
}

// --------------------------------------------------------------------- montaj sırası şeridi

/** Kabuğun zaman şeridinin üstüne açılan montaj sırası şeridi (u ∈ [0, N]); ekran kapanınca kalkar. */
class MontajSeridi {
  readonly tuval: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private suruk = false;
  private N = 0;
  private adlar: string[] = [];
  private u = 0;

  constructor(uDegisti: (u: number) => void) {
    const tuval = (this.tuval = document.createElement("canvas"));
    tuval.className = "montaj-tuval";
    tuval.dataset.testid = "montaj-seridi";
    tuval.tabIndex = 0;
    tuval.setAttribute("aria-label", "Montaj sırası şeridi");
    this.ctx = tuval.getContext("2d")!;
    new ResizeObserver(() => this.ciz()).observe(tuval);
    const tut = (e: PointerEvent) => {
      if (!this.N) return;
      const r = tuval.getBoundingClientRect();
      const w = r.width - 24;
      const u = ((e.clientX - r.left - 12) / w) * this.N;
      uDegisti(Math.min(Math.max(u, 0), this.N));
    };
    tuval.addEventListener("pointerdown", (e) => {
      this.suruk = true;
      tuval.setPointerCapture(e.pointerId);
      tut(e);
    });
    tuval.addEventListener("pointermove", (e) => this.suruk && tut(e));
    const bitir = () => (this.suruk = false);
    tuval.addEventListener("pointerup", bitir);
    tuval.addEventListener("pointercancel", bitir);
  }

  kur(adlar: string[]): void {
    this.adlar = adlar;
    this.N = adlar.length;
    this.ciz();
  }

  zaman(u: number): void {
    this.u = u;
    this.ciz();
  }

  ciz(): void {
    const tv = this.tuval;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const W = tv.clientWidth;
    const H = tv.clientHeight;
    if (!W || !H) return;
    if (tv.width !== Math.round(W * dpr) || tv.height !== Math.round(H * dpr)) {
      tv.width = Math.round(W * dpr);
      tv.height = Math.round(H * dpr);
    }
    const c = this.ctx;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    if (!this.N) return;
    const css = getComputedStyle(document.documentElement);
    const tok = (n: string) => css.getPropertyValue(n).trim();
    const x0 = 12;
    const w = W - 24;
    const X = (u: number) => x0 + (u / this.N) * w;
    const renkler = [tok("--celik"), tok("--pirinc"), tok("--camgobegi"), tok("--mor"), tok("--tamam"), tok("--mercan")];
    const yb = 26;
    const yh = Math.min(30, H - yb - 10);
    c.font = `600 10.5px ${tok("--mono")}`;
    c.textBaseline = "top";
    for (let i = 0; i <= this.N; i++) {
      c.fillStyle = tok("--cizgi");
      c.fillRect(Math.round(X(i)), 18, 1, H - 22);
      c.fillStyle = tok("--silik");
      c.fillText(String(i), X(i) + 3, 4);
    }
    c.font = `600 11px ${tok("--govde")}`;
    c.textBaseline = "middle";
    this.adlar.forEach((ad, i) => {
      const a = X(i);
      const b = X(i + 1);
      const r = renkler[i % renkler.length];
      c.fillStyle = r + "33";
      c.fillRect(a, yb, Math.max(b - a - 1, 1), yh);
      c.fillStyle = r;
      c.fillRect(a, yb, 3, yh);
      c.save();
      c.beginPath();
      c.rect(a, yb, Math.max(b - a - 4, 0), yh);
      c.clip();
      c.fillStyle = tok("--yazi");
      c.fillText(ad, a + 8, yb + yh / 2);
      c.restore();
    });
    const x = X(this.u);
    c.fillStyle = tok("--pirinc");
    c.fillRect(Math.round(x) - 1, 14, 2, H - 16);
    c.beginPath();
    c.moveTo(x - 6, 12);
    c.lineTo(x + 6, 12);
    c.lineTo(x, 19);
    c.fill();
  }
}

// --------------------------------------------------------------------- durum

interface Durum {
  M: Montaj | null;
  u: number;
  hedefU: number | null;
  hiz: number;
  secili: string | null;
  aglar: Map<string, Ag>; // parça kimliği → ağ
  oneri: Oneri | null;
  oneriBag: Bag | null;
  /** Son "Uygula"nın sonucu: süre farkı ve torna ekranında seçilecek işlem. */
  uygulama: { sure_farki: number; islem: number | null } | null;
  /** Son parametre yanıtındaki torna işi (sonraki uygulamada değişen işlemi bulmak için). */
  sonTorna: TornaIs | null;
  hata: string | null;
  yukHata: string | null;
  mesgul: boolean;
  yuklendi: boolean;
  poz: Map<string, Mat4>;
}

const D: Durum = {
  M: null,
  u: 0,
  hedefU: null,
  hiz: PATLAT_HIZ,
  secili: null,
  aglar: new Map(),
  oneri: null,
  oneriBag: null,
  uygulama: null,
  sonTorna: null,
  hata: null,
  yukHata: null,
  mesgul: false,
  yuklendi: false,
  poz: new Map(),
};

let K: Kabuk | null = null;
let alan: HTMLElement | null = null;
let sahne: MontajSahne | null = null;
let serit: MontajSeridi | null = null;
let sagKap: HTMLDivElement | null = null;
let onceki: number | null = null;
let yuklemeNo = 0;
const temizlik: (() => void)[] = [];

// --------------------------------------------------------------------- yükleme

/**
 * İki aşama: (1) Montaj JSON gelince durum, paneller ve pozlar hazır; (2) parça ve girişim ağları gelince sahne
 * kurulur. `yenidenAg`: ağı değişen parça kimlikleri (önbellekten silinir).
 */
async function yukle(hazir?: Montaj, yenidenAg: string[] = []): Promise<void> {
  const no = ++yuklemeNo;
  const k = K!;
  D.mesgul = true;
  let M: Montaj;
  try {
    M = hazir ?? (await k.api.getJson<Montaj>(encodeURIComponent(MONTAJ)));
  } catch (e) {
    if (no !== yuklemeNo) return;
    D.yukHata = e instanceof SunucuHatasi ? e.message : String(e);
    D.yuklendi = true;
    D.mesgul = false;
    panelleriCiz();
    return;
  }
  if (no !== yuklemeNo || K !== k) return;
  for (const b of M.bilesenler) b.T = duz(b.T);
  for (const a of M.sira) {
    for (const y of Object.keys(a.T_once)) a.T_once[y] = duz(a.T_once[y]);
    for (const y of Object.keys(a.T_sonra)) a.T_sonra[y] = duz(a.T_sonra[y]);
  }
  const ilk = D.M === null;
  D.M = M;
  D.yukHata = null;
  if (ilk) D.u = M.sira.length;
  D.u = Math.min(D.u, M.sira.length);
  if (D.secili && !M.bilesenler.some((b) => b.yol === D.secili)) D.secili = null;
  serit!.kur(M.sira.map((a) => a.ad));
  k.rozet(AD, M.girisimler.length ? `${M.girisimler.length} girişim` : null);
  D.yuklendi = true;
  D.mesgul = false;
  uAyarla(D.u);
  panelleriCiz();
  await aglarYukle(M, yenidenAg, !ilk);
}

async function aglarYukle(M: Montaj, yenidenAg: string[], kameraKoru: boolean): Promise<void> {
  const k = K!;
  const ag = (yol: string) =>
    k.api
      .getIkili(yol)
      .then(agCoz)
      .catch(() => null);
  for (const p of yenidenAg) D.aglar.delete(p);
  const eksik = [...new Set(M.bilesenler.map((b) => b.parca))].filter((p) => !D.aglar.has(p));
  const [gelen, girisim] = await Promise.all([
    Promise.all(eksik.map((p) => ag(`${encodeURIComponent(M.ad)}/ag/${encodeURIComponent(p)}`))),
    Promise.all(M.girisimler.map((g, i) => ag(g.ag ? goreli(g.ag) : `${encodeURIComponent(M.ad)}/ag/girisim/${g.i ?? i}`))),
  ]);
  eksik.forEach((p, i) => gelen[i] && D.aglar.set(p, gelen[i]!));
  if (D.M !== M || K !== k) return; // bu arada yeni montaj geldi ya da ekran kapandı
  sahne!.kur(M.bilesenler, D.aglar, kameraKoru);
  sahne!.girisimler(girisim.filter((a): a is Ag => a !== null));
  uAyarla(D.u);
}

// --------------------------------------------------------------------- u, poz

function uAyarla(u: number): void {
  const M = D.M;
  if (!M || !M.sira.length) return;
  const N = M.sira.length;
  D.u = Math.min(Math.max(u, 0), N);
  for (const b of M.bilesenler) {
    try {
      D.poz.set(b.yol, poz(M.sira, b.yol, D.u));
    } catch {
      D.poz.set(b.yol, b.T);
    }
  }
  if (!K) return;
  sahne!.pozlar(D.poz);
  sahne!.girisimGorunur(D.u >= N);
  seciliGlif();
  serit!.zaman(D.u);
  const { i, s } = adimU(D.u, N);
  const adim = D.u >= N ? N : s > 0 ? i + 1 : i;
  $("#saat").innerHTML = `Adım ${adim} <span>/ ${N}</span>`;
  $("#saat").title = D.u >= N ? "tam montaj" : M.sira[Math.min(i, N - 1)].ad;
}

/** E: patlat (u → 0) / topla (u → N). */
function patlatTopla(): void {
  const M = D.M;
  if (!M) return;
  const simdi = D.hedefU ?? D.u;
  hedefe(simdi > 0 ? 0 : M.sira.length);
}

/** u'yu PATLAT_HIZ ile hedefe götürür (komut "patlat": 0, "topla": N). */
function hedefe(u: number): void {
  const M = D.M;
  if (!M) return;
  D.hiz = PATLAT_HIZ * M.sira.length;
  D.hedefU = u;
  oynatDugmesi();
}

/** Boşluk: montaj sırasını oynat (sondaysa baştan). */
function oynat(): void {
  const M = D.M;
  if (!M) return;
  if (D.hedefU !== null) D.hedefU = null;
  else {
    if (D.u >= M.sira.length) uAyarla(0);
    D.hiz = OYNAT_HIZ;
    D.hedefU = M.sira.length;
  }
  oynatDugmesi();
}

function oynatDugmesi(): void {
  if (!K) return;
  const b = $("#oynat");
  const oynuyor = D.hedefU !== null;
  b.innerHTML = oynuyor ? DURAKLAT_SVG : OYNAT_SVG;
  b.setAttribute("aria-label", oynuyor ? "Durdur (Boşluk)" : "Montaj sırasını oynat (Boşluk)");
}

// --------------------------------------------------------------------- seçim

function sec(yol: string | null): void {
  D.secili = yol;
  seciliGlif();
  if (K && D.M) {
    agacCiz();
    sagCiz();
  }
}

/** Bir yaprağın serbestliği: son adımdaki (tam montaj) kayıt; yoksa kendi adımındaki. */
function serbestlik(yol: string): Serbestlik | null {
  const sira = D.M?.sira ?? [];
  for (let i = sira.length - 1; i >= 0; i--) if (sira[i].serbestlik[yol]) return sira[i].serbestlik[yol];
  return null;
}

function seciliGlif(): void {
  if (!sahne) return;
  const yol = D.secili;
  const T = yol ? D.poz.get(yol) : undefined;
  const ol = olcek();
  sahne.secili(yol, yol ? serbestlik(yol) : null, T ? [T[3], T[7], T[11]] : null, ol);
  sahne.kutleMerkezi(D.M && D.u >= D.M.sira.length ? D.M.kutle.merkez : null, ol);
}

function olcek(): number {
  let enBuyuk = 0;
  for (const ag of D.aglar.values()) {
    for (let i = 0; i < ag.V.length; i++) enBuyuk = Math.max(enBuyuk, Math.abs(ag.V[i]));
  }
  return Math.max(enBuyuk * 0.5, 10);
}

// --------------------------------------------------------------------- paneller

function panelleriCiz(): void {
  if (!K || !alan) return;
  if (!D.M) {
    alan.innerHTML = `<section class="bolum"><h2 class="ust-baslik">Montaj</h2>
      <div class="hata-kutu" role="alert"><b>Montaj yüklenemedi</b>${kacis(D.yukHata ?? "")}</div></section>`;
    const kap = (sagKap ??= document.createElement("div"));
    kap.innerHTML = `<section class="bolum"><div class="girisim-kart" data-testid="girisim-karti">Montaj yok</div></section>`;
    K.mufettis(kap);
    return;
  }
  agacCiz();
  sagCiz();
  hudCiz();
}

function hudCiz(): void {
  const M = D.M!;
  $("#hudBaslik").innerHTML = `<b>${kacis(M.ad)}</b><span>${M.bilesenler.length} bileşen · ${M.sira.length} adım · ${kacis(
    M.parcalar.map((p) => p.ad).join(", "),
  )}</span>`;
  $("#hudKatman").innerHTML = `<div class="lejant"><span class="kare-ornek girisim"></span> girişim · <span class="kare-ornek km"></span> kütle merkezi</div>`;
  $("#hudUyari").innerHTML = M.girisimler.length
    ? `<div class="uyari-kutu hata"><b>Girişim</b>${M.girisimler.length} çift, toplam ${sayi(
        M.girisimler.reduce((a, g) => a + g.hacim, 0),
        1,
      )} mm³</div>`
    : `<div class="uyari-kutu tamam"><b>Girişim yok</b>tam montaj temiz</div>`;
}

function agacCiz(): void {
  const M = D.M!;
  const kap = alan!;
  const yollar = new Set(M.bilesenler.map((b) => b.yol));
  const parcaAd = (k: string | null) => M.parcalar.find((p) => p.kimlik === k)?.ad ?? k ?? "";
  const dugum = (n: MontajDugum, yol: string): string => {
    if (n.part !== null && n.part !== undefined && yollar.has(yol)) {
      const s = serbestlik(yol);
      const sabit = M.bilesenler.find((b) => b.yol === yol)?.sabit;
      const kareler = s ? cip(s) : null;
      const cipHtml = sabit
        ? `<span class="cip-metin">sabit</span>`
        : kareler
          ? `<span class="cip" aria-hidden="true">${kareler.map((q) => `<i class="${q.kilitli ? "dolu" : ""}"></i>`).join("")}</span>
             <span class="cip-metin">${s!.sayi === 0 ? "kilitli" : `${s!.sayi} serbest: ${kacis(s!.etiketler.join(" "))}`}</span>`
          : `<span class="cip-metin">—</span>`;
      return `<li><button class="yaprak" data-yol="${kacis(yol)}" aria-pressed="${D.secili === yol}">
        <span class="ad">${kacis(n.name)} <small>${kacis(parcaAd(n.part))}</small></span>${cipHtml}</button></li>`;
    }
    const cocuk = n.children.map((c) => dugum(c, yol ? `${yol}/${c.name}` : c.name)).join("");
    if (!yol) return cocuk;
    return `<li><details open><summary>${kacis(n.name)} <small>alt montaj</small></summary><ul>${cocuk}</ul></details></li>`;
  };
  const kg = (t: number | null) => (t === null ? "—" : `${sayi(t * 1000, 3)} kg`);
  kap.innerHTML = `
    <section class="bolum">
      <h2 class="ust-baslik">Montaj ağacı <span>${kacis(M.agac.name)}</span></h2>
      <ul class="agac">${dugum(M.agac, "")}</ul>
      <p class="not-kucuk">Çip: 6 kare, dolu = kilitli serbestlik derecesi (SPEC 08).</p>
    </section>
    <section class="bolum">
      <h2 class="ust-baslik">BOM <span>${M.bom.length} satır</span></h2>
      <table class="bom"><thead><tr><th>Kalem</th><th>Adet</th><th>Birim</th><th>Toplam</th></tr></thead><tbody>
      ${M.bom
        .map(
          (b) =>
            `<tr><td>${kacis(parcaAd(b.item))}</td><td>${b.qty}</td><td>${kg(b.unit_mass)}</td><td>${kg(b.total_mass)}</td></tr>`,
        )
        .join("")}</tbody></table>
      <dl class="kv"><dt>Toplam kütle</dt><dd>${kg(M.kutle.toplam)}</dd>
        <dt>Kütle merkezi</dt><dd>${M.kutle.merkez.map((v) => sayi(v, 1)).join(", ")} mm</dd></dl>
    </section>`;
  kap.querySelectorAll<HTMLButtonElement>("button.yaprak").forEach((b) =>
    b.addEventListener("click", () => sec(D.secili === b.dataset.yol ? null : b.dataset.yol!)),
  );
}

/** Sağ panel: müfettişe girişim kartı ve seçili parça; alt bölmeye kanıtlar. */
function sagCiz(): void {
  const M = D.M!;
  const kap = (sagKap ??= document.createElement("div"));
  kap.innerHTML = `<section class="bolum"><h2 class="ust-baslik">Girişim <span>SPEC 09</span></h2><div class="m-kart"></div></section>
    ${D.secili ? `<section class="bolum m-secili"></section>` : ""}`;
  K!.mufettis(kap);
  kartCiz();
  if (D.secili) seciliCiz();
  $("#sekmeler").innerHTML = `<button role="tab" aria-selected="true">Kanıtlar <span class="sayi">${M.kontroller.length}</span></button>`;
  K!.kanitlar(M.kontroller);
}

function seciliCiz(): void {
  const M = D.M!;
  const yol = D.secili!;
  const b = M.bilesenler.find((x) => x.yol === yol);
  const p = M.parcalar.find((x) => x.kimlik === b?.parca);
  const s = serbestlik(yol);
  sagKap!.querySelector<HTMLElement>(".m-secili")!.innerHTML = `<h2 class="ust-baslik">Seçili <span>${kacis(yol)}</span></h2>
    <dl class="kv">
      <dt>Parça</dt><dd>${kacis(p?.ad ?? b?.parca ?? "")}</dd>
      <dt>Malzeme</dt><dd>${kacis(p?.malzeme ?? "—")}</dd>
      <dt>Hacim</dt><dd>${p ? `${sayi(p.hacim, 1)} mm³` : "—"}</dd>
      <dt>Kaynak</dt><dd>${p?.kaynak ? `${kacis(p.kaynak.tur)}: ${kacis(p.kaynak.is)}` : "CAD"}</dd>
      <dt>Serbestlik</dt><dd>${b?.sabit ? "sabit" : s ? `${s.sayi} · ${kacis(s.etiketler.join(" ") || "—")}` : "—"}</dd>
    </dl>
    ${s && s.sayi > 0 ? `<p class="not-kucuk">Sahnede: yeşil ok = öteleme yönü, pirinç halka + çizgi = dönme / vida ekseni.</p>` : ""}`;
}

/** Girişim çiftindeki parçalara bağlı parametreler. */
function baglar(a: string, b: string): Bag[] {
  const M = D.M!;
  const parca = (yol: string) => M.bilesenler.find((x) => x.yol === yol)?.parca ?? yol;
  const kume = new Set([a, b, parca(a), parca(b)]);
  return M.baglar.filter((g) => g.parcalar.some((k) => kume.has(k)));
}

/** "Tornada göster" adresi: değişen işlem ve süre farkı torna ekranının `secim`ine gider. */
function tornaAdresi(): string {
  const u = D.uygulama;
  const q = new URLSearchParams();
  if (u?.islem !== null && u?.islem !== undefined) q.set("islem", String(u.islem));
  if (u) q.set("fark", String(u.sure_farki));
  const s = q.toString();
  return `#/torna${s ? `?${s}` : ""}`;
}

function kartCiz(): void {
  if (!sagKap || !D.M) return;
  const M = D.M;
  const kap = sagKap.querySelector<HTMLElement>(".m-kart");
  if (!kap) return;
  const sonuc = D.uygulama
    ? `<div class="sonuc"><span class="rozet ${D.uygulama.sure_farki <= 0 ? "iyi" : "kotu"}" data-testid="sure-farki">torna süresi ${
        D.uygulama.sure_farki <= 0 ? "−" : "+"
      }${Math.abs(D.uygulama.sure_farki).toFixed(2)} s</span>
      <a href="${kacis(tornaAdresi())}" class="baglanti" data-testid="tornada-goster">Tornada göster →</a></div>`
    : "";
  if (!M.girisimler.length) {
    kap.innerHTML = `<div class="girisim-kart temiz" data-testid="girisim-karti" role="status">
      <b><span class="ik tamam" aria-hidden="true">✓</span> Girişim yok: temiz</b>
      <span>Tam montajda hacmi sıfırdan büyük kesişim yok.</span>${sonuc}</div>`;
  } else {
    const g = M.girisimler[0];
    const bag = baglar(g.a, g.b)[0] ?? null;
    const p = bag?.parametre;
    const o = D.oneri && D.oneriBag === bag ? D.oneri : null;
    kap.innerHTML = `<div class="girisim-kart" data-testid="girisim-karti" role="status">
      <b><span class="ik hata" aria-hidden="true">×</span> Girişim: ${kacis(g.a)} ↔ ${kacis(g.b)}</b>
      <span>hacim ${sayi(g.hacim, 2)} mm³${M.girisimler.length > 1 ? ` · ${M.girisimler.length - 1} çift daha` : ""}</span>
      ${
        p
          ? `<div class="bag">Bağlı parametre: <b>${kacis(p.is)} · ${kacis(p.anahtar)} = ${p.deger}</b> <small>(${p.min}–${p.max})</small></div>
        ${o ? `<div class="oneri">${o.deger === null ? `Öneri yok: ${kacis(o.neden)}` : `Öneri: ${kacis(p.anahtar)} = ${sayi(o.deger, 4)} (hacim ${sayi(o.hacim, 3)} mm³)`}</div>` : ""}
        <div class="dugmeler">
          <button data-testid="oner" ${D.mesgul ? "disabled" : ""}>Öner</button>
          <button data-testid="uygula" ${o && o.deger !== null && !D.mesgul ? "" : "disabled"}>Uygula</button>
        </div>`
          : `<div class="bag">Bu çifte bağlı parametre yok.</div>`
      }
      ${D.hata ? `<div class="hata-kutu" role="alert"><b>Sunucu</b>${kacis(D.hata)}</div>` : ""}
      ${sonuc}</div>`;
    kap.querySelector('[data-testid="oner"]')?.addEventListener("click", () => void oner(bag!, [g.a, g.b]));
    kap.querySelector('[data-testid="uygula"]')?.addEventListener("click", () => void uygula(bag!));
  }
  kap.querySelector('[data-testid="tornada-goster"]')?.addEventListener("click", (e) => {
    e.preventDefault();
    K?.git(tornaAdresi());
  });
}

async function oner(bag: Bag, cift: [string, string]): Promise<void> {
  if (!D.M || D.mesgul || !K) return;
  D.mesgul = true;
  D.hata = null;
  kartCiz();
  try {
    const q = new URLSearchParams({ is: bag.parametre.is, anahtar: bag.parametre.anahtar, cift: cift.join(",") });
    D.oneri = await K.api.getJson<Oneri>(`${encodeURIComponent(D.M.ad)}/oneri?${q}`);
    D.oneriBag = bag;
  } catch (e) {
    D.hata = e instanceof SunucuHatasi ? e.message : String(e);
  } finally {
    D.mesgul = false;
    kartCiz();
  }
}

async function uygula(bag: Bag, deger?: number): Promise<void> {
  const v = deger ?? (D.oneri && D.oneri.deger !== null ? D.oneri.deger : null);
  if (!D.M || D.mesgul || v === null || !K) return;
  D.mesgul = true;
  D.hata = null;
  kartCiz();
  try {
    const p = bag.parametre;
    // İlk uygulamada karşılaştırılacak eski torna işi: torna ekranının ucundan okunur (modülü import edilmez).
    if (!D.sonTorna) D.sonTorna = await tornaIsiOku(p.is);
    const y = await K.api.postJson<MontajParametreYaniti>(
      `${encodeURIComponent(D.M.ad)}/parametre`,
      { is: p.is, anahtar: p.anahtar, deger: v },
      `${D.M.ad}: ${p.is} ${p.anahtar} → ${v}`,
    );
    D.uygulama = { sure_farki: y.sure_farki, islem: degisenIslem(D.sonTorna, y.is) };
    D.sonTorna = y.is;
    D.oneri = null;
    D.oneriBag = null;
    D.mesgul = false;
    if (K) await yukle(y.montaj, bag.parcalar);
  } catch (e) {
    D.hata = e instanceof SunucuHatasi ? e.message : String(e);
    D.mesgul = false;
    kartCiz();
  }
}

// --------------------------------------------------------------------- klavye, komutlar

/** Ekranın kısayolları (yalnız ekran açıkken dinlenir; kabuğun Ctrl tuşlarına ve rakamlarına dokunmaz). */
function tus(e: KeyboardEvent): void {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const k = e.key;
  if (k === "Escape") {
    sec(null);
    return;
  }
  const hedef = e.target as HTMLElement;
  if (hedef.matches("input, textarea, select") || hedef.isContentEditable) return;
  const N = D.M?.sira.length ?? 0;
  if (k === "e" || k === "E") patlatTopla();
  else if (k === " ") {
    if (hedef.matches("button, a, summary")) return;
    e.preventDefault();
    oynat();
  } else if (k === "ArrowRight" || k === "ArrowLeft") {
    e.preventDefault();
    D.hedefU = null;
    oynatDugmesi();
    const u = k === "ArrowRight" ? Math.floor(D.u + 1e-9) + 1 : Math.ceil(D.u - 1e-9) - 1;
    uAyarla(Math.min(Math.max(u, 0), N));
  } else if (k === "Home") uAyarla(0);
  else if (k === "End") uAyarla(N);
}

function dinle(el: EventTarget, tur: string, f: (e: Event) => void): void {
  el.addEventListener(tur, f);
  temizlik.push(() => el.removeEventListener(tur, f));
}

function komutlar(): Komut[] {
  const M = D.M;
  const gecis: Komut[] = [
    { kimlik: "montaj.git.torna", baslik: "Torna ekranı", anahtar_kelimeler: ["torna", "2"], calistir: () => K?.git("#/torna") },
    { kimlik: "montaj.git.freze", baslik: "Freze ekranı", anahtar_kelimeler: ["freze", "1"], calistir: () => K?.git("#/freze") },
  ];
  if (!M) return gecis;
  // Bağlı parametreler (ör. "L 9.5"): torna işinin parametresi değişir, montaj ve torna yeniden hesaplanır.
  const bagli: Komut[] = M.baglar.map((b) => {
    const p = b.parametre;
    return {
      kimlik: `montaj.bag.${p.is}.${p.anahtar}`,
      baslik: `Bağlı parametre ${p.anahtar} (${p.is} · şu an ${p.deger}; ${p.min}–${p.max})`,
      anahtar_kelimeler: [p.anahtar.toLocaleLowerCase("tr")],
      desen: `${p.anahtar} <sayı>`,
      calistir: (sayi?: number) => (sayi === undefined ? undefined : uygula(b, sayi)),
      yama: (sayi: number) => [{ bolum: "torna_isleri", isaretci: `/parametreler/${p.is}/${p.anahtar}`, deger: sayi }],
    };
  });
  return [
    ...bagli,
    { kimlik: "montaj.patlat", baslik: "Patlat", anahtar_kelimeler: ["patlat", "patlatılmış görünüm"], calistir: () => hedefe(0) },
    { kimlik: "montaj.topla", baslik: "Topla", anahtar_kelimeler: ["topla", "tam montaj"], calistir: () => hedefe(M.sira.length) },
    { kimlik: "montaj.patlat_topla", baslik: "Patlat / topla", anahtar_kelimeler: ["patlat"], kisayol: "E", calistir: patlatTopla },
    { kimlik: "montaj.oynat", baslik: "Montaj sırasını oynat", anahtar_kelimeler: ["boşluk"], calistir: oynat },
    ...M.sira.map((a) => ({
      kimlik: `montaj.adim.${a.i}`,
      baslik: `Adım ${a.i + 1}: ${a.ad}`,
      anahtar_kelimeler: [a.yol],
      calistir: () => uAyarla(a.i + 1),
    })),
    ...gecis,
  ];
}

// --------------------------------------------------------------------- EkranModulu

const montaj: EkranModulu = {
  ad: AD,
  baslik: "Montaj",
  tus: "3",

  async ac(a: HTMLElement, k: Kabuk): Promise<void> {
    K = k;
    alan = a;
    D.yuklendi = false;
    D.hedefU = null;
    sahne ??= new MontajSahne(k.sahne, sec);
    sahne.bagla(k.sahne.katman(AD));
    serit ??= new MontajSeridi((u) => {
      D.hedefU = null;
      oynatDugmesi();
      uAyarla(u);
    });
    $("#seritKap").append(serit.tuval);
    $("#hiz").innerHTML = `<span class="serit-not"><kbd>E</kbd> patlat / topla</span>`;
    const kancaAlanlari = {
      get hazir() {
        return D.yuklendi && !D.mesgul;
      },
      montajU: () => D.u,
      montajPoz: (yol: string) => [...(D.poz.get(yol) ?? [])],
    };
    Object.defineProperties(k.kanca, Object.getOwnPropertyDescriptors(kancaAlanlari));
    oynatDugmesi();
    dinle($("#oynat"), "click", oynat);
    dinle(document, "keydown", (e) => tus(e as KeyboardEvent));
    if (D.M) {
      // önceki açılıştan kalan durum hemen çizilir; sunucudaki güncel montaj ardından gelir
      serit.kur(D.M.sira.map((x) => x.ad));
      uAyarla(D.u);
      panelleriCiz();
    }
    await yukle();
  },

  kapat(): void {
    D.hedefU = null;
    for (const f of temizlik.splice(0)) f();
    sahne?.birak();
    serit?.tuval.remove();
    if (K) K.sahne.katmanBirak(AD);
    $("#hiz").replaceChildren();
    yuklemeNo++;
    K = null;
    alan = null;
    D.yuklendi = false;
    D.mesgul = false;
    onceki = null;
  },

  /** Sunucu durumu dışarıdan değişti (geri al, proje aç, torna parametresi). */
  async tazele(): Promise<void> {
    if (K) await yukle(undefined, [...D.aglar.keys()]);
  },

  komutlar,

  sec(oge: string): void {
    if (D.M?.bilesenler.some((b) => b.yol === oge)) sec(oge);
  },

  kare(t: number): void {
    const dt = onceki === null ? 0 : Math.min(t - onceki, 0.1);
    onceki = t;
    if (D.hedefU === null || !D.M) return;
    const d = D.hedefU - D.u;
    const adim = D.hiz * dt;
    if (Math.abs(d) <= adim) {
      const h = D.hedefU;
      D.hedefU = null;
      oynatDugmesi();
      uAyarla(h);
    } else uAyarla(D.u + Math.sign(d) * adim);
  },
};

export default montaj;
