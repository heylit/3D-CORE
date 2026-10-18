// SPEC 47c — Analiz ekranı (A3 EkranModulu). Ağ, seçim, koşul, çözüm, sonda ve yakınsama
// sunucudan (/api/ekran/analiz/...) gelir; bu modül çizer ve girdiyi iletir. Mühendislik sayısı hesaplamaz:
// renk ölçeği ve deforme konumu yalnız sunucu değerlerinin görsel dönüşümüdür (analiz_yardim.ts).

import * as THREE from "three";

import { SunucuHatasi } from "../api";
import { sayi } from "../paneller";
import type { Kontrol, Nokta3 } from "../tipler";
import { GERILME_RENKLERI, deformeKonum, renkOlcegi, sondaOlcegi } from "./analiz_yardim";
import type { EkranModulu, Kabuk, Komut } from "./tip";

const AD = "analiz";
const SONDA_N = 200;
const BILESEN_ADLARI: Record<string, string> = {
  vm: "von Mises",
  sxx: "σxx",
  syy: "σyy",
  szz: "σzz",
  sxy: "τxy",
  sxz: "τxz",
  syz: "τyz",
  s1: "σ1",
  s2: "σ2",
  s3: "σ3",
};

// --------------------------------------------------------------------- sunucu şeması

interface Secim {
  kimlik: string;
  tur: "duzlem" | "silindir";
  tanim: Record<string, unknown>;
  dugumler: number[];
  ucgenler: number[][];
  alan: number;
  kilitli: boolean;
}

interface Kosul {
  kimlik: string;
  secim: string;
  tur: "mesnet" | "cekme" | "basinc";
  deger: string[] | number[] | number;
  kilitli: boolean;
}

interface CozumOzeti {
  u_max: number;
  u_max_dugum: number;
  vm_max: number;
  vm_max_dugum: number;
  tepki: Nokta3;
  yuk: Nokta3;
  denge: Nokta3;
  guvenlik: number | null;
  olcek: number | null;
}

interface AnalitikSatir {
  ad: string;
  formul: string;
  deger: number;
  birim: string;
  fem: number | null;
  fark: number | null;
}

interface Egri {
  ad: string;
  p0: Nokta3;
  p1: Nokta3;
  s: number[];
  deger: number[];
}

interface YakinsamaSatir {
  h: number;
  dugum: number | null;
  u_max: number | null;
  vm_max: number | null;
  neden: string | null;
}

interface Analiz {
  sema: number;
  ad: string;
  parca: { ad: string; hacim: number };
  malzeme: { ad: string; E: number; nu: number; Re: number | null };
  ag: { h: number; dugum: number; eleman: number; hacim: number };
  secimler: Secim[];
  kosullar: Kosul[];
  cozum: CozumOzeti | null;
  analitik: AnalitikSatir[];
  egriler: Egri[];
  yakinsama: YakinsamaSatir[] | null;
  kontroller: Kontrol[];
}

interface AgVeri {
  dugum: Float32Array;
  ucgen: Uint32Array;
  kimlik: Int32Array;
}

interface AlanVeri {
  u: Float32Array;
  vm: Float32Array;
  asal: Float32Array;
  tensor: Float32Array;
}

interface SondaVeri {
  s: Float64Array;
  deger: Float64Array;
  iceride: Uint8Array;
  bilesen: string;
  egri: Egri | null;
}

// --------------------------------------------------------------------- ikili çözücüler (SPEC 47c biçimi)

const hiza = (n: number) => n + ((8 - (n % 8)) % 8);

function agCoz(b: ArrayBuffer): AgVeri {
  const v = new DataView(b);
  const nd = v.getUint32(4, true);
  const m = v.getUint32(8, true);
  let o = 16;
  const dugum = new Float32Array(b.slice(o, o + nd * 12));
  o += hiza(nd * 12);
  const ucgen = new Uint32Array(b.slice(o, o + m * 12));
  o += hiza(m * 12);
  const kimlik = new Int32Array(b.slice(o, o + nd * 4));
  return { dugum, ucgen, kimlik };
}

function alanCoz(b: ArrayBuffer): AlanVeri {
  const nd = new DataView(b).getUint32(4, true);
  let o = 8;
  const al = (k: number) => {
    const a = new Float32Array(b.slice(o, o + nd * k * 4));
    o += hiza(nd * k * 4);
    return a;
  };
  return { u: al(3), vm: al(1), asal: al(3), tensor: al(6) };
}

function sondaCoz(b: ArrayBuffer): Pick<SondaVeri, "s" | "deger" | "iceride"> {
  const n = new DataView(b).getUint32(4, true);
  let o = 8;
  const s = new Float64Array(b.slice(o, o + n * 8));
  o += hiza(n * 8);
  const deger = new Float64Array(b.slice(o, o + n * 8));
  o += hiza(n * 8);
  const iceride = new Uint8Array(b.slice(o, o + n));
  return { s, deger, iceride };
}

// --------------------------------------------------------------------- durum

interface Durum {
  ornekler: string[];
  ad: string;
  J: Analiz | null;
  ag: AgVeri | null;
  alan: AlanVeri | null;
  bilesen: string;
  kat: number;
  seciliSecim: string | null;
  seciliKosul: string | null;
  sondaModu: boolean;
  sondaBas: Nokta3 | null;
  sonda: SondaVeri | null;
  hata: string | null;
  mesgul: boolean;
  olcekUclari: [number, number] | null;
}

const D: Durum = {
  ornekler: [],
  ad: "",
  J: null,
  ag: null,
  alan: null,
  bilesen: "vm",
  kat: 1,
  seciliSecim: null,
  seciliKosul: null,
  sondaModu: false,
  sondaBas: null,
  sonda: null,
  hata: null,
  mesgul: false,
  olcekUclari: null,
};

let K: Kabuk | null = null;
let solAlan: HTMLElement | null = null;
let mufettisAlan: HTMLElement | null = null;
let govde: THREE.Mesh | null = null;
let sondaCizgi: THREE.Line | null = null;
const temizlik: (() => void)[] = [];

const kacis = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

function dinle(el: EventTarget, tur: string, f: (e: Event) => void): void {
  el.addEventListener(tur, f);
  temizlik.push(() => el.removeEventListener(tur, f));
}

function kabuk(): Kabuk {
  if (!K) throw new Error("analiz ekranı açık değil");
  return K;
}

async function is<T>(f: () => Promise<T>): Promise<T | null> {
  D.mesgul = true;
  D.hata = null;
  try {
    return await f();
  } catch (e) {
    D.hata = e instanceof SunucuHatasi ? e.message : String(e);
    return null;
  } finally {
    D.mesgul = false;
    ciz();
  }
}

// --------------------------------------------------------------------- sunucu çağrıları

const yol = (alt = "") => `${encodeURIComponent(D.ad)}${alt}`;

async function yukle(ad: string): Promise<void> {
  const k = kabuk();
  await is(async () => {
    const [J, ag] = await Promise.all([k.api.getJson<Analiz>(ad), k.api.getIkili(`${ad}/ag`)]);
    D.ad = ad;
    D.J = J;
    D.ag = agCoz(ag);
    D.alan = null;
    D.sonda = null;
    D.seciliSecim = null;
    D.seciliKosul = null;
    if (J.cozum) await alanAl();
    govdeKur(true);
  });
}

async function alanAl(): Promise<void> {
  D.alan = D.J?.cozum ? alanCoz(await kabuk().api.getIkili(yol("/alan"))) : null;
}

async function analizGonder(alt: string, gvd: unknown, etiket: string): Promise<void> {
  await is(async () => {
    D.J = await kabuk().api.postJson<Analiz>(yol(alt), gvd, etiket);
    await alanAl();
    if (!D.J.cozum) D.sonda = null;
    govdeKur(false);
  });
}

async function secimYap(govdeJson: unknown): Promise<void> {
  await analizGonder("/sec", govdeJson, "Yüz seç");
  if (D.J && !D.hata) D.seciliSecim = D.J.secimler.at(-1)?.kimlik ?? null;
  ciz();
}

async function kosulEkle(secim: string, tur: Kosul["tur"], deger: unknown): Promise<void> {
  await analizGonder("/kosul", { secim, tur, deger }, tur === "mesnet" ? "Mesnet" : "Yük");
}

/** api.ts'nin EkranApi'sinde olmayan yöntemler (DELETE, ikili yanıtlı POST) için; hata → SunucuHatasi. */
async function ham(yontem: string, alt: string, gvd?: unknown): Promise<Response> {
  const r = await fetch(`/api/ekran/${AD}/${yol(alt)}`, {
    method: yontem,
    headers: gvd === undefined ? {} : { "Content-Type": "application/json" },
    body: gvd === undefined ? undefined : JSON.stringify(gvd),
  });
  if (r.ok) return r;
  let mesaj = `${r.status} ${r.statusText}`;
  try {
    const j = await r.json();
    if (typeof j.detail === "string") mesaj = j.detail;
  } catch {
    /* gövde JSON değil */
  }
  throw new SunucuHatasi(r.status, mesaj);
}

async function kosulSil(kimlik: string): Promise<void> {
  await is(async () => {
    D.J = (await (await ham("DELETE", `/kosul/${encodeURIComponent(kimlik)}`)).json()) as Analiz;
    D.seciliKosul = null;
    D.alan = null;
    D.sonda = null;
    govdeKur(false);
  });
}

async function coz(): Promise<void> {
  await analizGonder("/coz", {}, "Çöz");
}

async function yakinsama(): Promise<void> {
  await analizGonder("/yakinsama", {}, "Yakınsama");
}

async function yenidenAg(h: number): Promise<void> {
  await is(async () => {
    D.J = await kabuk().api.postJson<Analiz>(yol("/ag"), { h }, "Ağ boyu");
    D.ag = agCoz(await kabuk().api.getIkili(yol("/ag")));
    D.alan = null;
    D.sonda = null;
    govdeKur(true);
  });
}

async function sondaCek(p0: Nokta3, p1: Nokta3, egri: Egri | null = null): Promise<void> {
  const bilesen = egri ? "sxx" : D.bilesen;
  await is(async () => {
    const r = await ham("POST", "/sonda", { p0, p1, n: SONDA_N, bilesen });
    D.sonda = { ...sondaCoz(await r.arrayBuffer()), bilesen, egri };
    sondaCizgisi(p0, p1);
  });
}

// --------------------------------------------------------------------- sahne

const GRI: [number, number, number] = [0.62, 0.66, 0.71];
const SECIM_RENGI: Record<string, [number, number, number]> = {
  mesnet: [0.2, 0.45, 0.95],
  cekme: [0.95, 0.55, 0.15],
  basinc: [0.85, 0.3, 0.6],
  secili: [0.98, 0.9, 0.2],
};

function katman(): THREE.Group {
  return kabuk().sahne.katman(AD);
}

/** Düğüm değerleri (renk) ve konumları sunucu verisinden; çerçeveleme ilk yüklemede. */
function govdeKur(cercevele: boolean): void {
  if (!K || !D.ag) return;
  const g = katman();
  if (govde) {
    g.remove(govde);
    govde.geometry.dispose();
    (govde.material as THREE.Material).dispose();
  }
  const { dugum, ucgen } = D.ag;
  const olcek = D.J?.cozum?.olcek ?? 0;
  const konum = D.alan && olcek ? deformeKonum(dugum, D.alan.u, olcek * D.kat) : dugum;
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(konum, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(renkler(), 3));
  // Her sınır üçgeni kendi yüzü: raycast faceIndex = sunucudaki sınır üçgeni indeksi j.
  geo.setIndex(new THREE.BufferAttribute(ucgen, 1));
  geo.computeVertexNormals();
  govde = new THREE.Mesh(
    geo,
    new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.6, metalness: 0.05, side: THREE.DoubleSide }),
  );
  govde.name = "analiz-govde";
  g.add(govde);
  if (cercevele) kameraCercevele(geo);
  kabuk().sahne.ciz();
}

function renkler(): Float32Array {
  const nd = D.ag!.kimlik.length;
  const c = new Float32Array(nd * 3);
  D.olcekUclari = null;
  const degerler = D.alan ? bilesenDizisi(D.alan, D.bilesen) : null;
  if (degerler) {
    // Ölçeğin uçları sunucu dizisinin min / max'ı (görsel; hesap değil). von Mises'te max = cozum.vm_max.
    let min = Number.POSITIVE_INFINITY;
    let max = Number.NEGATIVE_INFINITY;
    for (const v of degerler) {
      if (v < min) min = v;
      if (v > max) max = v;
    }
    D.olcekUclari = [min, max];
    for (let i = 0; i < nd; i++) c.set(renkOlcegi(degerler[i], min, max, GERILME_RENKLERI), i * 3);
    return c;
  }
  for (let i = 0; i < nd; i++) c.set(GRI, i * 3);
  const sira = new Map<number, number>();
  D.ag!.kimlik.forEach((k, i) => sira.set(k, i));
  const tur = new Map<string, string>();
  for (const k of D.J?.kosullar ?? []) tur.set(k.secim, k.tur);
  for (const s of D.J?.secimler ?? []) {
    const r = s.kimlik === D.seciliSecim ? SECIM_RENGI.secili : SECIM_RENGI[tur.get(s.kimlik) ?? ""];
    if (!r) continue;
    for (const k of s.dugumler) {
      const i = sira.get(k);
      if (i !== undefined) c.set(r, i * 3);
    }
  }
  return c;
}

function bilesenDizisi(a: AlanVeri, b: string): Float32Array {
  const nd = a.vm.length;
  if (b === "vm") return a.vm;
  const sutun = { sxx: 0, syy: 1, szz: 2, sxy: 3, sxz: 4, syz: 5 }[b as "sxx"];
  const [kaynak, adim, ofs] =
    sutun !== undefined ? [a.tensor, 6, sutun] : [a.asal, 3, Number(b.slice(1)) - 1];
  const out = new Float32Array(nd);
  for (let i = 0; i < nd; i++) out[i] = kaynak[i * adim + ofs];
  return out;
}

function kameraCercevele(geo: THREE.BufferGeometry): void {
  geo.computeBoundingSphere();
  const s = geo.boundingSphere!;
  const { kamera, kontrol } = kabuk().sahne;
  kontrol.target.copy(s.center);
  kamera.position.copy(s.center).add(new THREE.Vector3(-1.1, -1.6, 1.2).multiplyScalar(s.radius * 1.9));
  kamera.near = Math.max(s.radius / 500, 0.1);
  kamera.far = s.radius * 50;
  kamera.updateProjectionMatrix();
  kontrol.update();
}

function sondaCizgisi(p0: Nokta3 | null, p1: Nokta3 | null): void {
  if (!K) return;
  if (sondaCizgi) {
    katman().remove(sondaCizgi);
    sondaCizgi.geometry.dispose();
    sondaCizgi = null;
  }
  if (p0 && p1) {
    const geo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...p0), new THREE.Vector3(...p1)]);
    sondaCizgi = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0x111111, depthTest: false }));
    sondaCizgi.renderOrder = 10;
    katman().add(sondaCizgi);
  }
  kabuk().sahne.ciz();
}

/** Tıklanan sınır üçgeni ve dünya noktası (deforme görünümde de üçgen indeksi aynıdır). */
function vur(e: PointerEvent): { j: number; nokta: Nokta3 } | null {
  if (!govde) return null;
  const { renderer, kamera } = kabuk().sahne;
  const r = renderer.domElement.getBoundingClientRect();
  const ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  const ray = new THREE.Raycaster();
  ray.setFromCamera(ndc, kamera);
  const h = ray.intersectObject(govde, false)[0];
  if (!h || h.faceIndex == null) return null;
  return { j: h.faceIndex, nokta: [h.point.x, h.point.y, h.point.z] };
}

let basla: { x: number; y: number } | null = null;

async function tikla(e: PointerEvent): Promise<void> {
  if (!basla || Math.hypot(e.clientX - basla.x, e.clientY - basla.y) > 4 || D.mesgul) return; // sürükleme
  const v = vur(e);
  if (!v) return;
  if (D.sondaModu) {
    if (!D.alan) {
      D.hata = "Sonda için önce çözün";
      ciz();
    } else if (!D.sondaBas) {
      D.sondaBas = v.nokta;
      sondaCizgisi(null, null);
      ciz();
    } else {
      const p0 = D.sondaBas;
      D.sondaBas = null;
      await sondaCek(p0, v.nokta);
    }
    return;
  }
  await secimYap({ ucgen: v.j });
}

// --------------------------------------------------------------------- paneller

function ciz(): void {
  if (!K) return;
  solCiz();
  mufettisCiz();
  bolmeCiz();
  const uyari = D.J?.kontroller.filter((k) => k.durum !== "tamam").length ?? 0;
  K.rozet(AD, uyari ? `${uyari} uyarı` : null);
}

function solCiz(): void {
  if (!solAlan) return;
  const J = D.J;
  const secenek = D.ornekler.map((a) => `<option value="${kacis(a)}"${a === D.ad ? " selected" : ""}>${kacis(a)}</option>`);
  const kosulSatiri = (k: Kosul) => {
    const deger = Array.isArray(k.deger) ? k.deger.join(", ") : sayi(k.deger, 3);
    const ad = { mesnet: "Mesnet", cekme: "Çekme", basinc: "Basınç" }[k.tur];
    const birim = k.tur === "mesnet" ? "" : " MPa";
    return `<li><button class="kosul${k.kimlik === D.seciliKosul ? " secili" : ""}" data-kosul="${kacis(k.kimlik)}"
      aria-pressed="${k.kimlik === D.seciliKosul}">${ad} · ${kacis(k.secim)} · ${kacis(deger)}${birim}
      ${k.kilitli ? '<span class="kilit" title="Örnek koşulu (silinemez)">kilitli</span>' : ""}</button></li>`;
  };
  solAlan.innerHTML = `
    <h2 class="ust-baslik">Analiz <span>tet4</span></h2>
    <label>Örnek <select id="analizOrnek" aria-label="Analiz örneği">${secenek.join("")}</select></label>
    ${
      J
        ? `<dl class="bilgi">
        <dt>Parça</dt><dd>${kacis(J.parca.ad)} · ${sayi(J.parca.hacim, 1)} mm³</dd>
        <dt>Malzeme</dt><dd>${kacis(J.malzeme.ad)} · E ${sayi(J.malzeme.E, 0)} MPa · ν ${sayi(J.malzeme.nu, 2)}${
          J.malzeme.Re === null ? "" : ` · Re ${sayi(J.malzeme.Re, 0)} MPa`
        }</dd>
        <dt>Ağ</dt><dd>${J.ag.dugum} düğüm · ${J.ag.eleman} eleman</dd></dl>
      <label>Ağ boyu h [mm] <input id="analizH" type="number" step="0.5" min="0" value="${J.ag.h}" aria-label="Ağ boyu" /></label>
      <button id="analizAg">Yeniden ağ</button>
      <h3>Seçimler</h3><ul class="liste">${J.secimler
        .map(
          (s) => `<li><button class="secim${s.kimlik === D.seciliSecim ? " secili" : ""}" data-secim="${kacis(s.kimlik)}"
            aria-pressed="${s.kimlik === D.seciliSecim}">${kacis(s.kimlik)} · ${s.tur === "duzlem" ? "düzlem" : "silindir"} ·
            ${s.dugumler.length} düğüm · ${sayi(s.alan, 2)} mm²</button></li>`,
        )
        .join("")}</ul>
      <h3>Koşullar <small>(Del: seçili koşulu sil)</small></h3><ul class="liste">${J.kosullar.map(kosulSatiri).join("")}</ul>
      <div class="dugmeler">
        <button id="analizCoz" class="birincil">Çöz</button>
        <button id="analizYakinsama">Yakınsama</button>
        <button id="analizSonda" aria-pressed="${D.sondaModu}">Sonda (P)</button>
        <a id="analizInp" href="/api/ekran/${AD}/${yol("/inp")}" download="${kacis(D.ad)}.inp">.inp indir</a>
      </div>`
        : ""
    }
    ${D.hata ? `<p class="hata" role="alert">${kacis(D.hata)}</p>` : ""}
    ${D.mesgul ? '<p class="yukleniyor" role="status">Hesaplanıyor…</p>' : ""}`;
  solAlan.querySelector<HTMLSelectElement>("#analizOrnek")?.addEventListener("change", (e) => {
    void yukle((e.target as HTMLSelectElement).value);
  });
  solAlan.querySelector("#analizAg")?.addEventListener("click", () => {
    const h = Number(solAlan!.querySelector<HTMLInputElement>("#analizH")!.value);
    void yenidenAg(h);
  });
  solAlan.querySelector("#analizCoz")?.addEventListener("click", () => void coz());
  solAlan.querySelector("#analizYakinsama")?.addEventListener("click", () => void yakinsama());
  solAlan.querySelector("#analizSonda")?.addEventListener("click", () => sondaModu(!D.sondaModu));
  for (const b of solAlan.querySelectorAll<HTMLButtonElement>("[data-secim]"))
    b.addEventListener("click", () => {
      D.seciliSecim = b.dataset.secim!;
      govdeKur(false);
      ciz();
    });
  for (const b of solAlan.querySelectorAll<HTMLButtonElement>("[data-kosul]"))
    b.addEventListener("click", () => {
      D.seciliKosul = b.dataset.kosul!;
      ciz();
    });
}

function mufettisCiz(): void {
  if (!K || !mufettisAlan) return;
  const s = D.J?.secimler.find((x) => x.kimlik === D.seciliSecim);
  const yer = mufettisAlan;
  yer.innerHTML = `
    <h2 class="ust-baslik">Müfettiş</h2>
    ${
      s
        ? `<p>Seçim <b>${kacis(s.kimlik)}</b>: ${s.dugumler.length} düğüm, ${s.ucgenler.length} üçgen, alan ${sayi(s.alan, 3)} mm²</p>
      <form id="kosulFormu">
        <label>Tür <select name="tur" aria-label="Koşul türü">
          <option value="mesnet">Mesnet</option><option value="cekme">Yük: çekme t [MPa]</option>
          <option value="basinc">Yük: basınç p [MPa]</option></select></label>
        <fieldset class="dof"><legend>Mesnet</legend>
          ${["ux", "uy", "uz"].map((d) => `<label><input type="checkbox" name="${d}" checked /> ${d}</label>`).join("")}</fieldset>
        <label>t / p <input name="deger" value="0, 0, 0" aria-label="Çekme vektörü ya da basınç" /></label>
        <button type="submit">Ekle (Enter)</button>
      </form>`
        : "<p>Sahnede bir yüze tıklayın: aynı düzlemdeki sınır yüzü seçilir.</p>"
    }
    <form id="silindirFormu"><h3>Silindir seçimi</h3>
      <label>Eksen noktası <input name="nokta" value="100, 50, 0" /></label>
      <label>Eksen yönü <input name="eksen" value="0, 0, 1" /></label>
      <label>Yarıçap r <input name="r" type="number" step="0.1" value="5" /></label>
      <button type="submit">Seç</button></form>
    ${D.J?.cozum ? gorunumFormu() : ""}`;
  const sayilar = (m: string) => m.split(/[,\s]+/).filter(Boolean).map(Number);
  yer.querySelector<HTMLFormElement>("#kosulFormu")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const f = e.target as HTMLFormElement;
    const tur = (f.elements.namedItem("tur") as HTMLSelectElement).value as Kosul["tur"];
    const ham = (f.elements.namedItem("deger") as HTMLInputElement).value;
    const deger =
      tur === "mesnet"
        ? ["ux", "uy", "uz"].filter((d) => (f.elements.namedItem(d) as HTMLInputElement).checked)
        : tur === "cekme"
          ? sayilar(ham)
          : sayilar(ham)[0];
    void kosulEkle(s!.kimlik, tur, deger);
  });
  yer.querySelector<HTMLFormElement>("#silindirFormu")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const f = e.target as HTMLFormElement;
    const al = (ad: string) => (f.elements.namedItem(ad) as HTMLInputElement).value;
    void secimYap({ silindir: { nokta: sayilar(al("nokta")), eksen: sayilar(al("eksen")), r: Number(al("r")) } });
  });
  yer.querySelector<HTMLSelectElement>("#analizBilesen")?.addEventListener("change", (e) => {
    D.bilesen = (e.target as HTMLSelectElement).value;
    govdeKur(false);
    ciz();
  });
  yer.querySelector<HTMLInputElement>("#analizKat")?.addEventListener("input", (e) => {
    D.kat = Number((e.target as HTMLInputElement).value);
    govdeKur(false);
  });
  kabuk().mufettis(yer);
}

function gorunumFormu(): string {
  const c = D.J!.cozum!;
  const u = D.olcekUclari;
  return `<h3>Görünüm</h3>
    <label>Renk <select id="analizBilesen" aria-label="Renk bileşeni">${Object.entries(BILESEN_ADLARI)
      .map(([k, a]) => `<option value="${k}"${k === D.bilesen ? " selected" : ""}>${a}</option>`)
      .join("")}</select></label>
    <div class="olcek" data-testid="renk-olcegi" aria-label="Renk ölçeği">
      <span>${u ? sayi(u[0], 2) : "—"}</span>
      <i style="display:inline-block;width:96px;height:10px;vertical-align:middle;background:linear-gradient(90deg,${GERILME_RENKLERI.map((r) => `rgb(${r.map((x) => Math.round(x * 255)).join(",")})`).join(",")})"></i>
      <span>${u ? sayi(u[1], 2) : "—"}</span> MPa</div>
    <label>Deforme ölçeği ×${c.olcek === null ? "—" : sayi(c.olcek, 1)}
      <input id="analizKat" type="range" min="0" max="2" step="0.05" value="${D.kat}" aria-label="Deforme ölçeği çarpanı" /></label>
    <dl class="bilgi"><dt>u_max</dt><dd>${sayi(c.u_max, 4)} mm (düğüm ${c.u_max_dugum})</dd>
      <dt>σvM max</dt><dd>${sayi(c.vm_max, 2)} MPa (düğüm ${c.vm_max_dugum})</dd>
      <dt>Güvenlik</dt><dd>${c.guvenlik === null ? "Re yok" : sayi(c.guvenlik, 3)}</dd>
      <dt>Yük</dt><dd>${c.yuk.map((v) => sayi(v, 1)).join(", ")} N</dd>
      <dt>Tepki</dt><dd>${c.tepki.map((v) => sayi(v, 1)).join(", ")} N</dd></dl>`;
}

function bolmeCiz(): void {
  if (!K || !D.J) return;
  K.kanitlar(D.J.kontroller);
  const bolme = document.querySelector<HTMLElement>("#bolme");
  if (!bolme) return;
  const ek = document.createElement("div");
  ek.className = "analiz-ek";
  ek.innerHTML = `${analitikTablosu()}${sondaGrafigi()}${yakinsamaGrafigi()}`;
  bolme.append(ek);
  ek.querySelector("#kirschSonda")?.addEventListener("click", () => {
    const e = D.J!.egriler[0];
    void sondaCek(e.p0, e.p1, e);
  });
}

function analitikTablosu(): string {
  const A = D.J!.analitik;
  const egri = D.J!.egriler[0];
  if (!A.length && !egri) return "";
  return `<h3>Analitik karşılaştırma <small>(bilgi; FEM kanıtı SPEC 11–13 testleridir)</small></h3>
    <table class="analitik"><thead><tr><th>Ad</th><th>Formül</th><th>Analitik</th><th>FEM</th><th>Fark</th></tr></thead>
    <tbody>${A.map(
      (r) => `<tr><td>${kacis(r.ad)}</td><td>${kacis(r.formul)}</td><td>${sayi(r.deger, 4)} ${kacis(r.birim)}</td>
        <td>${r.fem === null ? "—" : sayi(r.fem, 4)}</td><td>${r.fark === null ? "—" : `${sayi(100 * r.fark, 1)} %`}</td></tr>`,
    ).join("")}</tbody></table>
    ${egri && D.J!.cozum ? `<button id="kirschSonda">${kacis(egri.ad)} boyunca sonda</button>` : ""}`;
}

/** Basit SVG çizgi grafiği: seriler [x[], y[], bayrak?], eksen uçları verilir (hesap yok, ölçekleme). */
function grafik(seriler: { x: ArrayLike<number>; y: ArrayLike<number>; ic?: Uint8Array; sinif: string }[], yUc: [number, number], baslik: string, xAd: string, yAd: string): string {
  const W = 320;
  const H = 160;
  const P = 34;
  let xMin = Number.POSITIVE_INFINITY;
  let xMax = Number.NEGATIVE_INFINITY;
  for (const s of seriler)
    for (let i = 0; i < s.x.length; i++) {
      xMin = Math.min(xMin, s.x[i]);
      xMax = Math.max(xMax, s.x[i]);
    }
  if (!(xMax > xMin)) xMax = xMin + 1;
  const [y0, y1r] = yUc;
  const y1 = y1r > y0 ? y1r : y0 + 1;
  const X = (x: number) => P + ((x - xMin) / (xMax - xMin)) * (W - P - 8);
  const Y = (y: number) => H - P + 4 - ((y - y0) / (y1 - y0)) * (H - P - 8);
  const yollar = seriler.map((s) => {
    let d = "";
    let kalem = false;
    for (let i = 0; i < s.x.length; i++) {
      if (s.ic && !s.ic[i]) {
        kalem = false; // parça dışı: boşluk, değer çizilmez
        continue;
      }
      d += `${kalem ? "L" : "M"}${X(s.x[i]).toFixed(1)},${Y(s.y[i]).toFixed(1)}`;
      kalem = true;
    }
    const cizgi = s.sinif === "analitik" ? 'stroke="#c05621" stroke-dasharray="4 3"' : 'stroke="#2b6cb0"';
    return `<path class="${s.sinif}" d="${d}" fill="none" stroke-width="1.5" ${cizgi} />`;
  });
  return `<figure class="grafik"><figcaption>${kacis(baslik)}</figcaption>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${kacis(baslik)}">
      <line x1="${P}" y1="${H - P + 4}" x2="${W - 8}" y2="${H - P + 4}" class="eksen" stroke="#8a8f98" />
      <line x1="${P}" y1="4" x2="${P}" y2="${H - P + 4}" class="eksen" stroke="#8a8f98" />
      <text x="${P}" y="${H - 6}" class="etiket" font-size="9" fill="currentColor">${sayi(xMin, 1)}</text>
      <text x="${W - 8}" y="${H - 6}" text-anchor="end" class="etiket" font-size="9" fill="currentColor">${sayi(xMax, 1)} ${kacis(xAd)}</text>
      <text x="2" y="12" class="etiket" font-size="9" fill="currentColor">${sayi(y1, 1)}</text>
      <text x="2" y="${H - P + 4}" class="etiket" font-size="9" fill="currentColor">${sayi(y0, 1)}</text>
      <text x="${P + 4}" y="12" class="etiket" font-size="9" fill="currentColor">${kacis(yAd)}</text>
      ${yollar.join("")}
    </svg></figure>`;
}

function sondaGrafigi(): string {
  const S = D.sonda;
  if (!S) return D.sondaModu ? `<p class="ipucu-metin">Sonda: parçada ${D.sondaBas ? "ikinci" : "ilk"} noktaya tıklayın.</p>` : "";
  const uc = sondaOlcegi(S.deger, S.iceride);
  if (!uc) return "<p>Sonda çizgisi parçanın dışında kalıyor.</p>";
  const seriler: Parameters<typeof grafik>[0] = [{ x: S.s, y: S.deger, ic: S.iceride, sinif: "fem" }];
  let [y0, y1] = uc;
  if (S.egri) {
    seriler.push({ x: S.egri.s, y: S.egri.deger, sinif: "analitik" });
    for (const v of S.egri.deger) {
      y0 = Math.min(y0, v);
      y1 = Math.max(y1, v);
    }
  }
  const ad = BILESEN_ADLARI[S.bilesen] ?? S.bilesen;
  return grafik(seriler, [y0, y1], `Sonda: ${ad}${S.egri ? ` ve ${S.egri.ad}` : ""}`, "mm", "MPa");
}

function yakinsamaGrafigi(): string {
  const Y = D.J!.yakinsama;
  if (!Y) return "";
  const satirlar = Y.map(
    (r) =>
      `<tr><td>${sayi(r.h, 3)}</td><td>${r.dugum ?? "—"}</td><td>${r.u_max === null ? "—" : sayi(r.u_max, 5)}</td>
      <td>${r.vm_max === null ? "—" : sayi(r.vm_max, 2)}</td><td>${r.neden ? kacis(r.neden) : ""}</td></tr>`,
  ).join("");
  const tam = Y.filter((r) => r.vm_max !== null);
  let g = "";
  if (tam.length >= 2) {
    const vm = tam.map((r) => r.vm_max!);
    g = grafik([{ x: tam.map((r) => r.h), y: vm, sinif: "fem" }], [Math.min(...vm), Math.max(...vm)], "Güven halkası: σvM max – h", "mm", "MPa");
  }
  return `<h3>Yakınsama</h3><table class="analitik"><thead><tr><th>h</th><th>Düğüm</th><th>u_max</th><th>σvM max</th><th></th></tr></thead>
    <tbody>${satirlar}</tbody></table>${g}`;
}

function sondaModu(acik: boolean): void {
  D.sondaModu = acik;
  D.sondaBas = null;
  ciz();
}

// --------------------------------------------------------------------- klavye ve komutlar

function tus(e: KeyboardEvent): void {
  const hedef = e.target as HTMLElement | null;
  if (hedef && /^(INPUT|SELECT|TEXTAREA)$/.test(hedef.tagName)) return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.key === "p" || e.key === "P") {
    e.preventDefault();
    sondaModu(!D.sondaModu);
  } else if (e.key === "Delete" && D.seciliKosul) {
    e.preventDefault();
    void kosulSil(D.seciliKosul);
  } else if (e.key === "Enter" && D.seciliSecim) {
    const f = mufettisAlan?.querySelector<HTMLFormElement>("#kosulFormu");
    if (f) {
      e.preventDefault();
      f.requestSubmit();
    }
  } else if (e.key === "Escape") {
    D.seciliSecim = null;
    D.sondaBas = null;
    govdeKur(false);
    ciz();
  }
}

function komutlar(): Komut[] {
  return [
    { kimlik: "analiz.coz", baslik: "Analiz: çöz", anahtar_kelimeler: ["fem", "solve"], calistir: () => coz() },
    { kimlik: "analiz.yakinsama", baslik: "Analiz: yakınsama (3 ağ)", calistir: () => yakinsama() },
    { kimlik: "analiz.sonda", baslik: "Analiz: sonda modu", kisayol: "P", calistir: () => sondaModu(!D.sondaModu) },
    {
      kimlik: "analiz.ag",
      baslik: "Analiz: ağ boyu",
      desen: "h <sayı>",
      calistir: (h?: number) => (h === undefined ? undefined : yenidenAg(h)),
    },
  ];
}

// --------------------------------------------------------------------- modül

const analiz: EkranModulu = {
  ad: AD,
  baslik: "Analiz",
  tus: "6",

  async ac(alan: HTMLElement, k: Kabuk, secim?: string): Promise<void> {
    K = k;
    solAlan = alan;
    mufettisAlan = document.createElement("div");
    mufettisAlan.className = "analiz-mufettis";
    k.serit.bosalt();
    katman();
    const kancaAlanlari = {
      get hazir() {
        return D.J !== null && !D.mesgul;
      },
      analiz: () => D.J,
      olcekUclari: () => D.olcekUclari,
      sonda: () =>
        D.sonda ? { s: Array.from(D.sonda.s), deger: Array.from(D.sonda.deger), iceride: Array.from(D.sonda.iceride) } : null,
      hata: () => D.hata,
    };
    Object.defineProperties(k.kanca, Object.getOwnPropertyDescriptors(kancaAlanlari));
    const tuval = k.sahne.renderer.domElement;
    dinle(tuval, "pointerdown", (e) => {
      const p = e as PointerEvent;
      basla = { x: p.clientX, y: p.clientY };
    });
    dinle(tuval, "pointerup", (e) => void tikla(e as PointerEvent));
    dinle(document, "keydown", (e) => tus(e as KeyboardEvent));
    const L = await k.api.getJson<{ sema: number; ornekler: (string | { ad: string })[] }>("ornekler");
    D.ornekler = L.ornekler.map((o) => (typeof o === "string" ? o : o.ad));
    if (!D.ornekler.length) throw new Error("Sunucuda analiz örneği yok");
    const istenen = secim ? new URLSearchParams(secim).get("ornek") : null;
    await yukle(istenen && D.ornekler.includes(istenen) ? istenen : D.ad && D.ornekler.includes(D.ad) ? D.ad : D.ornekler[0]);
  },

  kapat(): void {
    for (const f of temizlik.splice(0)) f();
    if (K) {
      if (govde) {
        govde.geometry.dispose();
        (govde.material as THREE.Material).dispose();
      }
      sondaCizgi?.geometry.dispose();
      K.sahne.katmanBirak(AD);
      K.rozet(AD, null);
    }
    govde = null;
    sondaCizgi = null;
    K = null;
    solAlan = null;
    mufettisAlan = null;
    D.sondaModu = false;
    D.sondaBas = null;
  },

  async tazele(): Promise<void> {
    if (K && D.ad) await yukle(D.ad);
  },

  komutlar,

  sec(oge: string): void {
    if (D.J?.secimler.some((s) => s.kimlik === oge)) {
      D.seciliSecim = oge;
      govdeKur(false);
      ciz();
    }
  },
};

export default analiz;
