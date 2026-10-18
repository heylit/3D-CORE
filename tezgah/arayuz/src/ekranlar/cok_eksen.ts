// SPEC 47b — Çok eksen ekranı (A3 EkranModulu). Sunucu: /api/ekran/cok_eksen (tezgah/ekranlar/cok_eksen.py).
// Davranış: eklem şeridi + olay işaretleri, V ile göreli görünüm (parça sabit ↔ tezgâh sabit), sapma şeridi,
// TCP kapalı uç yolu, tri-dexel ışın görünümü, eklem tablosu ("postprosesör yok"). Kanca: window.__tezgah.cok_eksen.
// Ön yüz mühendislik sayısı hesaplamaz: eklem değerleri, pozlar, olaylar, sapma ve dexel sunucudan gelir;
// burada yalnız iki sunucu noktası arasında görsel ara değer (cok_eksen_yardim.ts) yapılır.

import * as THREE from "three";
import type { Kontrol } from "../tipler";
import {
  type Olay,
  type Poz,
  type PozDizisi,
  eklemSeridi,
  olayZamani,
  pozAraDeger,
  pozlarCoz,
  zamandanIndeks,
} from "./cok_eksen_yardim";
import type { EkranModulu, Kabuk, Komut } from "./tip";

const AD = "cok_eksen";
const SEMA = 1;
const HIZLAR = [1, 5, 20];
const PARAMETRELER: [string, string, string][] = [
  ["lead", "Lead", "°"],
  ["tilt", "Tilt", "°"],
  ["tol_p", "Konum toleransı", "mm"],
  ["tol_a", "Açı toleransı", "°"],
  ["L", "Takım boyu L", "mm"],
  ["clearance", "Güvenlik payı", "mm"],
];

// --------------------------------------------------------------------- sunucu biçimleri

interface Eksen {
  ad: string;
  tur: "dogrusal" | "doner";
  min: number | null;
  max: number | null;
}
interface Govde {
  ad: string;
  halka: string;
  sekil: "kutu" | "kapsul";
}
interface IslemJ {
  i: number;
  ad: string;
  takim: string;
  t0: number;
  t1: number;
  k0: number;
  k1: number;
}
interface CokEksen {
  sema: number;
  ad: string;
  tur: "3arti2" | "5eksen";
  profil: string;
  tezgah: { ad: string; eksenler: Eksen[]; govdeler: Govde[] };
  wcs: { code: string; origin: [number, number, number] };
  L: number;
  parametreler: Record<string, number>;
  islemler: IslemJ[];
  olaylar: Olay[];
  sim: { removed_volume: number; total_time: number; collisions: unknown[] } | null;
  sapma: { tol_p: number; tol_a: number; e_p_max: number; e_a_max: number };
  kontroller: Kontrol[];
}
interface Noktalar {
  n: number;
  k: number;
  konum: Float32Array;
  zaman: Float64Array;
  islem: Int16Array;
  hizli: Uint8Array;
  a: Float32Array;
  q: Float64Array;
  g93: Float32Array;
}
interface Sapma {
  s: number;
  ara: number;
  e: Float32Array;
  tcp: Float32Array;
}

/** Little-endian blok okuyucu: her blok (başlık dahil) 8 baytın katına tamamlanmıştır (sunucu `_blok`). */
class Okuyucu {
  private ofs = 0;
  constructor(private buf: ArrayBuffer) {}
  private blok<T>(Tip: { new (b: ArrayBuffer, o: number, n: number): T; BYTES_PER_ELEMENT: number }, n: number): T {
    const boy = Tip.BYTES_PER_ELEMENT * n;
    if (this.ofs + boy > this.buf.byteLength) throw new Error("ikili dizi beklenenden kısa");
    const kopya = this.buf.slice(this.ofs, this.ofs + boy);
    this.ofs += boy + ((8 - (boy % 8)) % 8);
    return new Tip(kopya, 0, n);
  }
  u4 = (n: number) => this.blok(Uint32Array, n);
  u2 = (n: number) => this.blok(Uint16Array, n);
  u1 = (n: number) => this.blok(Uint8Array, n);
  i2 = (n: number) => this.blok(Int16Array, n);
  f4 = (n: number) => this.blok(Float32Array, n);
  f8 = (n: number) => this.blok(Float64Array, n);
  baslik(m: number): number[] {
    const b = [...this.u4(1 + m)];
    if (b[0] !== SEMA) throw new Error(`ikili sürüm ${b[0]}, beklenen ${SEMA}`);
    return b.slice(1);
  }
  bitti(): void {
    if (this.ofs !== this.buf.byteLength) throw new Error("ikili dizinin boyu tutmuyor");
  }
}

function noktalarCoz(buf: ArrayBuffer): Noktalar {
  const o = new Okuyucu(buf);
  const [n, k] = o.baslik(2);
  const d = { n, k, konum: o.f4(3 * n), zaman: o.f8(n), islem: o.i2(n), hizli: o.u1(n), a: o.f4(3 * n), q: o.f8(n * (3 + k)), g93: o.f4(n) };
  o.bitti();
  return d;
}

function sapmaCoz(buf: ArrayBuffer): Sapma {
  const o = new Okuyucu(buf);
  const [s, ara] = o.baslik(2);
  const d = { s, ara, e: o.f4(2 * s), tcp: o.f4(3 * s * ara) };
  o.bitti();
  return d;
}

function govdeCoz(buf: ArrayBuffer): THREE.BufferGeometry {
  const o = new Okuyucu(buf);
  const [nv, nt] = o.baslik(2);
  const V = o.f4(3 * nv);
  const T = o.u4(3 * nt);
  o.bitti();
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(V, 3));
  g.setIndex(new THREE.BufferAttribute(T, 1));
  g.computeVertexNormals();
  return g;
}

/** Dexel ikilisinin son görüntüsü → ışın aralıkları kısa çizgi parçaları (WCS). Yüzey ağı kurulmaz. */
function dexelCizgileri(buf: ArrayBuffer): Float32Array {
  const o = new Okuyucu(buf);
  const [g] = o.baslik(1);
  let son: number[] = [];
  for (let s = 0; s < g; s++) {
    const [x0, y0, z0, dx, dy, dz] = o.f8(6);
    const [nx, ny, nz] = o.u4(3);
    const c: number[] = [];
    for (const [eksen, ni, nj] of [["z", nx, ny], ["x", ny, nz], ["y", nx, nz]] as [string, number, number][]) {
      const [r] = o.u4(1);
      const say = o.u2(r);
      const uc = o.f4(2 * say.reduce((a, b) => a + b, 0));
      let p = 0;
      for (let ray = 0; ray < r; ray++) {
        const i = Math.floor(ray / nj);
        const j = ray % nj;
        for (let m = 0; m < say[ray]; m++, p += 2) {
          for (const w of [uc[p], uc[p + 1]]) {
            if (eksen === "z") c.push(x0 + (i + 0.5) * dx, y0 + (j + 0.5) * dy, w);
            else if (eksen === "x") c.push(w, y0 + (i + 0.5) * dy, z0 + (j + 0.5) * dz);
            else c.push(x0 + (i + 0.5) * dx, w, z0 + (j + 0.5) * dz);
          }
        }
      }
      void ni;
    }
    son = c;
  }
  o.bitti();
  return new Float32Array(son);
}

// --------------------------------------------------------------------- durum

type Gorunum = "parca" | "tezgah";

interface Durum {
  ad: string;
  ornekler: { ad: string; tur: string; profil: string }[];
  J: CokEksen | null;
  nk: Noktalar | null;
  pz: PozDizisi | null;
  sp: Sapma | null;
  t: number;
  oynuyor: boolean;
  hiz: number;
  gorunum: Gorunum;
  tcpKapali: boolean;
  secili: Olay | null;
  hata: string | null;
  hazir: boolean;
  mesgul: boolean;
}

const D: Durum = {
  ad: "",
  ornekler: [],
  J: null,
  nk: null,
  pz: null,
  sp: null,
  t: 0,
  oynuyor: false,
  hiz: 5,
  gorunum: "parca",
  tcpKapali: false,
  secili: null,
  hata: null,
  hazir: false,
  mesgul: false,
};

let K: Kabuk | null = null;
let alan: HTMLElement | null = null;
let kok: THREE.Group | null = null;
let onceki: number | null = null;
const temizlik: (() => void)[] = [];
const govdeler: THREE.Mesh[] = [];
const parcaGrubu = new THREE.Group(); // yol, TCP kapalı yol, dexel: WCS'de çizilir, is_parcasi pozuyla taşınır
/** Ekranın biçimi (ekran açıkken belgeye eklenir, kapanınca kalkar). */
const BICIM = `
.ce-sol { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px 18px; min-width: 0; }
.ce-sol h3 { margin: 6px 0 0; font: 600 11px var(--govde); letter-spacing: .14em; text-transform: uppercase; color: var(--soluk); }
.ce-baslik { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.ce-baslik b { font: 800 20px/1.1 var(--baslik); overflow-wrap: anywhere; }
.ce-baslik span { color: var(--soluk); font-size: 12px; white-space: nowrap; }
.ce-sol select, .ce-param input { width: 100%; min-width: 0; background: var(--zemin); border: 1px solid var(--cizgi); border-radius: 6px; padding: 5px 8px; font: 13px var(--mono); }
.ce-eylem { display: flex; flex-wrap: wrap; gap: 4px; }
.ce-eylem button { border: 1px solid var(--cizgi); background: var(--panel-2); border-radius: 6px; padding: 5px 9px; cursor: pointer; font-weight: 600; }
.ce-eylem button[aria-pressed="true"] { border-color: var(--pirinc); }
.ce-serit, .ce-sapma-serit { width: 100%; display: block; background: var(--zemin); border: 1px solid var(--cizgi); border-radius: 6px; cursor: pointer; }
.ce-olaylar { display: flex; flex-direction: column; gap: 3px; max-height: 150px; overflow: auto; font-size: 12px; color: var(--soluk); }
.ce-olaylar button { text-align: left; border: 1px solid var(--cizgi); background: transparent; border-radius: 5px; padding: 3px 7px; cursor: pointer; font: 12px var(--mono); }
.ce-olaylar button.tezgah_carpma { box-shadow: inset 3px 0 0 var(--hata); }
.ce-olaylar button.eksen_siniri { box-shadow: inset 3px 0 0 var(--pirinc); }
.ce-param { display: flex; flex-direction: column; gap: 4px; }
.ce-param label { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); align-items: center; gap: 8px; font-size: 12.5px; color: var(--soluk); }
.ce-sapma { font: 12px var(--mono); color: var(--soluk); }
.ce-etiket { margin-left: 6px; padding: 1px 6px; border: 1px solid var(--cizgi); border-radius: 4px; letter-spacing: 0; text-transform: none; }
.ce-eklem { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px 10px; font: 13px var(--mono); padding: 8px 10px; border: 1px solid var(--cizgi); border-radius: 8px; }
.ce-eklem div { display: flex; gap: 6px; min-width: 0; }
.ce-eklem i { color: var(--pirinc); font-style: normal; }
.ce-eklem .alt { grid-column: 1 / -1; color: var(--soluk); font-size: 12px; }
`;

const RENK: Record<string, number> = { is_mili: 0xc9a227, is_parcasi: 0x6fa8dc, taban: 0x5b6470 };

function kabuk(): Kabuk {
  if (!K) throw new Error("çok eksen ekranı açık değil");
  return K;
}

// --------------------------------------------------------------------- yükleme

async function yukle(ad: string, J?: CokEksen): Promise<void> {
  const k = kabuk();
  D.mesgul = true;
  const [j, nb, pb, sb] = await Promise.all([
    J ?? k.api.getJson<CokEksen>(ad),
    k.api.getIkili(`${ad}/noktalar`),
    k.api.getIkili(`${ad}/pozlar`),
    k.api.getIkili(`${ad}/sapma`),
  ]);
  if (!K) return;
  const geo = await Promise.all(j.tezgah.govdeler.map((g) => k.api.getIkili(`${ad}/govde/${g.ad}`)));
  const dexel = j.sim ? await k.api.getIkili(`${ad}/dexel`).catch(() => null) : null;
  if (!K) return;
  D.ad = ad;
  D.J = j;
  D.nk = noktalarCoz(nb);
  D.pz = pozlarCoz(pb);
  D.sp = sapmaCoz(sb);
  D.t = Math.min(D.t, D.nk.zaman[D.nk.n - 1]);
  D.secili = null;
  sahneKur(geo, dexel);
  panelCiz();
  k.kanitlar(j.kontroller);
  const hata = j.kontroller.filter((c) => c.durum === "hata").length;
  k.rozet(AD, hata ? `${hata} hata` : null);
  guncelle();
  D.mesgul = false;
  D.hazir = true;
}

function temizleGrup(g: THREE.Object3D): void {
  for (const c of [...g.children]) {
    g.remove(c);
    const m = c as THREE.Mesh;
    m.geometry?.dispose();
    const mat = m.material as THREE.Material | THREE.Material[] | undefined;
    if (Array.isArray(mat)) mat.forEach((x) => x.dispose());
    else mat?.dispose();
  }
}

function cizgi(P: ArrayLike<number>, renk: number, kesik = false): THREE.Line {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(P), 3));
  const m = kesik
    ? new THREE.LineDashedMaterial({ color: renk, dashSize: 1.5, gapSize: 1 })
    : new THREE.LineBasicMaterial({ color: renk });
  const l = new THREE.Line(g, m);
  if (kesik) l.computeLineDistances();
  return l;
}

function sahneKur(geo: ArrayBuffer[], dexel: ArrayBuffer | null): void {
  const J = D.J!;
  temizleGrup(parcaGrubu);
  for (const m of govdeler.splice(0)) {
    kok!.remove(m);
    m.geometry.dispose();
    (m.material as THREE.Material).dispose();
  }
  J.tezgah.govdeler.forEach((g, b) => {
    const renk = RENK[g.halka] ?? 0x8a9199;
    const mat = new THREE.MeshStandardMaterial({ color: renk, transparent: true, opacity: g.halka === "is_mili" ? 0.85 : 0.35 });
    const m = new THREE.Mesh(govdeCoz(geo[b]), mat);
    m.matrixAutoUpdate = false;
    m.name = g.ad;
    govdeler.push(m);
    kok!.add(m);
  });
  const nk = D.nk!;
  parcaGrubu.add(cizgi(nk.konum, 0x4caf50));
  const tcp = cizgi(D.sp!.tcp, 0xe06666, true);
  tcp.name = "tcp_kapali";
  tcp.visible = D.tcpKapali;
  parcaGrubu.add(tcp);
  if (dexel) {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(dexelCizgileri(dexel), 3));
    parcaGrubu.add(new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0xb0b8c0, transparent: true, opacity: 0.5 })));
  }
  parcaGrubu.matrixAutoUpdate = false;
  kok!.add(parcaGrubu);
  kameraKur();
}

function kameraKur(): void {
  const s = kabuk().sahne;
  const [x, y, z] = D.gorunum === "parca" ? [0, 0, 0] : D.J!.wcs.origin;
  s.kontrol.target.set(x, y, z);
  const r = D.gorunum === "parca" ? 220 : 1400;
  s.kamera.position.set(x - r * 0.45, y - r * 0.75, z + r * 0.55);
  s.kamera.lookAt(x, y, z);
  s.kontrol.update();
}

// --------------------------------------------------------------------- görünüm

function matris(p: Poz): THREE.Matrix4 {
  const R = p.R;
  return new THREE.Matrix4().set(R[0], R[1], R[2], p.t[0], R[3], R[4], R[5], p.t[1], R[6], R[7], R[8], p.t[2], 0, 0, 0, 1);
}

/** "Parça sabit": makine → WCS dönüşümü T(−o)·P_parça⁻¹; "tezgâh sabit": birim. */
function gorunumMatrisi(kf: number): { M: THREE.Matrix4; parca: THREE.Matrix4 } {
  const J = D.J!;
  const o = J.wcs.origin;
  const b = J.tezgah.govdeler.findIndex((g) => g.halka === "is_parcasi");
  const P = b >= 0 ? matris(pozAraDeger(D.pz!, kf, b)) : new THREE.Matrix4();
  const wcs = new THREE.Matrix4().makeTranslation(o[0], o[1], o[2]);
  if (D.gorunum === "tezgah") return { M: new THREE.Matrix4(), parca: P.clone().multiply(wcs) };
  const M = new THREE.Matrix4().makeTranslation(-o[0], -o[1], -o[2]).multiply(P.clone().invert());
  return { M, parca: new THREE.Matrix4() };
}

function guncelle(): void {
  const nk = D.nk;
  if (!nk || !K || !D.pz) return;
  const kf = zamandanIndeks(Math.min(Math.max(D.t, 0), nk.zaman[nk.n - 1]), nk.zaman);
  const { M, parca } = gorunumMatrisi(kf);
  govdeler.forEach((m, b) => {
    m.matrix.copy(M).multiply(matris(pozAraDeger(D.pz!, kf, b)));
    m.matrixWorldNeedsUpdate = true;
    const vurgu = D.secili?.kind === "tezgah_carpma" && (D.secili.a === m.name || D.secili.b === m.name);
    (m.material as THREE.MeshStandardMaterial).emissive.setHex(vurgu ? 0xaa2222 : 0x000000);
  });
  parcaGrubu.matrix.copy(parca);
  parcaGrubu.matrixWorldNeedsUpdate = true;
  K.sahne.ciz();
  seritCiz();
  droCiz(Math.round(kf));
}

// --------------------------------------------------------------------- panel

const $a = <T extends HTMLElement = HTMLElement>(s: string) => alan!.querySelector<T>(s)!;

function sayi(v: number | null | undefined, b = 3): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "—" : v.toFixed(b);
}

function panelCiz(): void {
  const J = D.J!;
  alan!.innerHTML = `<div class="ce-sol" data-testid="cok-eksen">
    <div class="ce-baslik"><b>${J.ad}</b><span>${J.tur === "3arti2" ? "3+2" : "5 eksen"} · ${J.tezgah.ad}</span></div>
    <select data-ce="ornek" aria-label="Örnek">${D.ornekler.map((o) => `<option value="${o.ad}"${o.ad === J.ad ? " selected" : ""}>${o.ad}</option>`).join("")}</select>
    <div class="ce-eylem">
      <button data-ce="oynat">${D.oynuyor ? "Duraklat" : "Oynat"}</button>
      <button data-ce="hiz">×${D.hiz}</button>
      <button data-ce="gorunum" title="V">${D.gorunum === "parca" ? "Parça sabit" : "Tezgâh sabit"}</button>
      <button data-ce="tcp" aria-pressed="${D.tcpKapali}">TCP kapalı</button>
      <button data-ce="simule">${J.sim ? "Simülasyon ✓" : "Simüle et"}</button>
    </div>
    <canvas class="ce-serit" data-ce="serit" height="${28 * (J.tezgah.eksenler.filter((e) => e.tur === "doner").length + 1)}"></canvas>
    <div class="ce-olaylar">${J.olaylar.length ? J.olaylar.slice(0, 40).map((e, i) => `<button data-olay="${i}" class="${e.kind}">${e.kind === "eksen_siniri" ? "Sınır" : "Çarpma"} · ${e.a}${e.b ? " × " + e.b : ""} · ${sayi(e.distance, 2)} mm</button>`).join("") : "<span>Olay yok</span>"}</div>
    <h3>Parametreler</h3>
    <div class="ce-param">${PARAMETRELER.map(([a, ad, b]) => `<label><span>${ad} [${b}]</span><input data-param="${a}" value="${J.parametreler[a]}" inputmode="decimal"></label>`).join("")}</div>
    ${D.hata ? `<div class="uyari-kutu hata">${D.hata}</div>` : ""}
    <h3>Sapma (SPEC 42)</h3>
    <div class="ce-sapma">e_p ${sayi(J.sapma.e_p_max, 4)} / ${J.sapma.tol_p} mm · e_a ${sayi(J.sapma.e_a_max, 3)} / ${J.sapma.tol_a}°</div>
    <canvas class="ce-sapma-serit" data-ce="sapma" height="40"></canvas>
    <h3>Eklem tablosu <span class="ce-etiket">postprosesör yok</span></h3>
    <div class="ce-dro" data-ce="dro"></div>
  </div>`;
  const dugme = (ad: string, f: () => void) => $a(`[data-ce="${ad}"]`).addEventListener("click", f);
  dugme("oynat", () => oynat(!D.oynuyor));
  dugme("hiz", () => {
    D.hiz = HIZLAR[(HIZLAR.indexOf(D.hiz) + 1) % HIZLAR.length];
    panelCiz();
    guncelle();
  });
  dugme("gorunum", () => gorunumDegistir());
  dugme("tcp", () => tcpDegistir());
  dugme("simule", () => void simule());
  $a<HTMLSelectElement>('[data-ce="ornek"]').addEventListener("change", (e) => void yukle((e.target as HTMLSelectElement).value));
  alan!.querySelectorAll<HTMLButtonElement>("[data-olay]").forEach((b) =>
    b.addEventListener("click", () => olaySec(Number(b.dataset.olay))),
  );
  alan!.querySelectorAll<HTMLInputElement>("[data-param]").forEach((g) =>
    g.addEventListener("change", () => void parametre(g.dataset.param!, Number(g.value))),
  );
  const serit = $a<HTMLCanvasElement>('[data-ce="serit"]');
  serit.addEventListener("click", (e) => {
    const r = serit.getBoundingClientRect();
    const nk = D.nk!;
    zamanAyarla(((e.clientX - r.left) / r.width) * nk.zaman[nk.n - 1], true);
  });
  sapmaCiz();
}

/** Eklem şeridi: her döner eksen bir bant, sınır bantları kırmızı, olaylar işaretli, imleç t'de. */
function seritCiz(): void {
  if (!alan || !D.J || !D.nk) return;
  const c = alan.querySelector<HTMLCanvasElement>('[data-ce="serit"]');
  if (!c) return;
  const w = Math.max(1, Math.round(c.clientWidth || 300));
  c.width = w;
  const g = c.getContext("2d");
  if (!g) return;
  const nk = D.nk;
  const T = nk.zaman[nk.n - 1] || 1;
  const doner = D.J.tezgah.eksenler.map((e, j) => ({ e, j })).filter((x) => x.e.tur === "doner");
  g.clearRect(0, 0, w, c.height);
  doner.forEach(({ e, j }, s) => {
    const y0 = s * 28 + 2;
    const h = 24;
    const S = eklemSeridi(nk.zaman, nk.q, 3 + nk.k, j, w);
    let lo = Math.min(...S.min);
    let hi = Math.max(...S.max);
    if (e.min !== null && e.max !== null) {
      lo = Math.min(lo, e.min - 5);
      hi = Math.max(hi, e.max + 5);
    }
    const Y = (v: number) => y0 + h - ((v - lo) / (hi - lo || 1)) * h;
    if (e.min !== null && e.max !== null) {
      g.fillStyle = "rgba(220,60,60,.18)";
      g.fillRect(0, y0, w, Y(e.max) - y0);
      g.fillRect(0, Y(e.min), w, y0 + h - Y(e.min));
    }
    g.fillStyle = "#c9a227";
    for (let p = 0; p < w; p++) g.fillRect(p, Y(S.max[p]), 1, Math.max(1, Y(S.min[p]) - Y(S.max[p])));
    g.fillStyle = "#9aa3ad";
    g.font = "10px monospace";
    g.fillText(e.ad, 2, y0 + 10);
  });
  const yOlay = doner.length * 28 + 2;
  for (const o of D.J.olaylar) {
    g.fillStyle = o.kind === "eksen_siniri" ? "#e69138" : "#e06666";
    g.fillRect((olayZamani(o, nk.zaman) / T) * w - 1, yOlay, 3, 22);
  }
  g.fillStyle = "#ffffff";
  g.fillRect((D.t / T) * w, 0, 1, c.height);
}

function sapmaCiz(): void {
  const c = alan?.querySelector<HTMLCanvasElement>('[data-ce="sapma"]');
  if (!c || !D.sp || !D.J) return;
  const w = Math.max(1, Math.round(c.clientWidth || 300));
  c.width = w;
  const g = c.getContext("2d");
  if (!g) return;
  const { s, e } = D.sp;
  const tol = D.J.sapma.tol_p;
  let en = tol;
  for (let i = 0; i < s; i++) en = Math.max(en, e[2 * i]);
  const Y = (v: number) => 38 - (v / en) * 34;
  g.fillStyle = "#6fa8dc";
  for (let i = 0; i < s; i++) g.fillRect((i / Math.max(1, s)) * w, Y(e[2 * i]), Math.max(1, w / s), 38 - Y(e[2 * i]));
  g.fillStyle = "#e06666";
  g.fillRect(0, Y(tol), w, 1);
}

function droCiz(k: number): void {
  const d = alan?.querySelector<HTMLElement>('[data-ce="dro"]');
  if (!d || !D.nk || !D.J) return;
  const nk = D.nk;
  const sut = 3 + nk.k;
  const adlar = D.J.tezgah.eksenler.map((e) => e.ad);
  const isl = D.J.islemler[nk.islem[k]];
  d.innerHTML = `<div class="ce-eklem" data-test="eklem">${adlar
    .map((a, j) => `<div><i>${a}</i><span>${sayi(nk.q[k * sut + j])}</span></div>`)
    .join("")}<div class="alt">G93 ${nk.hizli[k] ? "G0" : sayi(nk.g93[k], 1)} · ${isl ? isl.ad : "—"} · nokta ${k}</div></div>`;
}

// --------------------------------------------------------------------- etkileşim

function zamanAyarla(t: number, durdur: boolean): void {
  if (!D.nk) return;
  if (durdur) oynat(false);
  D.t = Math.min(Math.max(t, 0), D.nk.zaman[D.nk.n - 1]);
  guncelle();
}

function oynat(acik: boolean): void {
  D.oynuyor = acik;
  const b = alan?.querySelector<HTMLButtonElement>('[data-ce="oynat"]');
  if (b) b.textContent = acik ? "Duraklat" : "Oynat";
}

function olaySec(i: number): void {
  const o = D.J?.olaylar[i];
  if (!o || !D.nk) return;
  D.secili = o;
  zamanAyarla(olayZamani(o, D.nk.zaman), true);
}

function gorunumDegistir(): void {
  D.gorunum = D.gorunum === "parca" ? "tezgah" : "parca";
  if (D.J) {
    panelCiz();
    kameraKur();
    guncelle();
  }
}

function tcpDegistir(): void {
  D.tcpKapali = !D.tcpKapali;
  const l = parcaGrubu.getObjectByName("tcp_kapali");
  if (l) l.visible = D.tcpKapali;
  if (D.J) {
    panelCiz();
    guncelle();
  }
}

async function parametre(anahtar: string, deger: number): Promise<void> {
  if (!D.J) return;
  try {
    const r = await kabuk().api.postJson<{ sema: number; is: CokEksen; sure_farki: number }>(
      `${D.ad}/parametre`,
      { anahtar, deger },
      `${anahtar} ${deger}`,
    );
    D.hata = null;
    await yukle(D.ad, r.is);
  } catch (e) {
    D.hata = e instanceof Error ? e.message : String(e);
    panelCiz();
  }
}

async function simule(): Promise<void> {
  if (!D.J || D.J.sim) return;
  D.mesgul = true;
  try {
    const J = await kabuk().api.postJson<CokEksen>(`${D.ad}/simule`, {});
    await yukle(D.ad, J);
  } catch (e) {
    D.hata = e instanceof Error ? e.message : String(e);
    D.mesgul = false;
    panelCiz();
  }
}

function tus(e: KeyboardEvent): void {
  if ((e.target as HTMLElement)?.tagName === "INPUT" || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.key === "v" || e.key === "V") gorunumDegistir();
  else if (e.key === " ") {
    e.preventDefault();
    oynat(!D.oynuyor);
  } else if (e.key === "Home") zamanAyarla(0, true);
  else if (e.key === "End" && D.nk) zamanAyarla(D.nk.zaman[D.nk.n - 1], true);
}

function dinle(el: EventTarget, tur: string, f: (e: Event) => void): void {
  el.addEventListener(tur, f);
  temizlik.push(() => el.removeEventListener(tur, f));
}

function komutlar(): Komut[] {
  return [
    { kimlik: "cok_eksen.gorunum", baslik: "Göreli görünüm (parça / tezgâh sabit)", kisayol: "V", calistir: gorunumDegistir },
    { kimlik: "cok_eksen.tcp", baslik: "TCP kapalı uç yolu", anahtar_kelimeler: ["sapma"], calistir: tcpDegistir },
    { kimlik: "cok_eksen.simule", baslik: "Tri-dexel simülasyonu", anahtar_kelimeler: ["dexel", "talaş"], calistir: () => simule() },
    { kimlik: "cok_eksen.oynat", baslik: D.oynuyor ? "Duraklat" : "Oynat", calistir: () => oynat(!D.oynuyor) },
    ...(D.J?.olaylar ?? []).slice(0, 20).map((o, i) => ({
      kimlik: `cok_eksen.olay.${i}`,
      baslik: `Olay: ${o.kind} ${o.a}${o.b ? " × " + o.b : ""}`,
      calistir: () => olaySec(i),
    })),
  ];
}

// --------------------------------------------------------------------- EkranModulu

const modul: EkranModulu = {
  ad: AD,
  baslik: "Çok eksen",
  tus: "5",

  async ac(a: HTMLElement, k: Kabuk, secim?: string): Promise<void> {
    K = k;
    alan = a;
    D.hazir = false;
    kok = k.sahne.katman(AD);
    const bicim = document.createElement("style");
    bicim.textContent = BICIM;
    document.head.append(bicim);
    temizlik.push(() => bicim.remove());
    const kancaAlanlari = {
      get hazir() {
        return D.hazir && !D.mesgul;
      },
      zaman: () => D.t,
      gorunum: () => D.gorunum,
      olaylar: () => D.J?.olaylar.length ?? 0,
      olaySec: (i: number) => olaySec(i),
      noktaSayisi: () => D.nk?.n ?? 0,
    };
    Object.defineProperties(k.kanca, Object.getOwnPropertyDescriptors(kancaAlanlari));
    dinle(document, "keydown", (e) => tus(e as KeyboardEvent));
    const r = await k.api.getJson<{ sema: number; ornekler: { ad: string; tur: string; profil: string }[] }>("ornekler");
    D.ornekler = r.ornekler;
    if (!D.ornekler.length) throw new Error("Sunucuda çok eksen örneği yok");
    const istenen = secim ? new URLSearchParams(secim).get("is") : null;
    const adlar = D.ornekler.map((o) => o.ad);
    await yukle(istenen && adlar.includes(istenen) ? istenen : adlar.includes(D.ad) ? D.ad : adlar[0]);
  },

  kapat(): void {
    oynat(false);
    for (const f of temizlik.splice(0)) f();
    if (K) {
      temizleGrup(parcaGrubu);
      for (const m of govdeler.splice(0)) {
        m.geometry.dispose();
        (m.material as THREE.Material).dispose();
      }
      K.sahne.katmanBirak(AD);
    }
    if (alan) alan.innerHTML = "";
    K = null;
    alan = null;
    kok = null;
    D.hazir = false;
    onceki = null;
  },

  async tazele(): Promise<void> {
    if (K && D.ad) await yukle(D.ad);
  },

  komutlar,

  sec(oge: string): void {
    const i = Number(oge);
    if (Number.isInteger(i)) olaySec(i);
  },

  kare(t: number): void {
    const dt = onceki === null ? 0 : Math.min(t - onceki, 0.1);
    onceki = t;
    if (D.oynuyor && D.nk) {
      const T = D.nk.zaman[D.nk.n - 1];
      D.t += dt * D.hiz;
      if (D.t >= T) {
        D.t = T;
        oynat(false);
      }
      guncelle();
    }
  },
};

export default modul;
