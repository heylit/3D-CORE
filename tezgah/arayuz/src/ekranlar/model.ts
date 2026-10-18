// SPEC 26 — "Model" ekranı (A3 kaydı): eskiz katmanı, serbestlik haritası, çelişki kartı, ekstrüzyon,
// parametre tablosu ve geçmiş şeridi. Uçlar /api/ekran/model/ altındadır (SPEC 26 Ek A). Saf hesaplar ../eskiz.ts'te.
// Arayüz mühendislik sayısı hesaplamaz: çözüm, hacim ve ağ sunucudan gelir; burada yalnız imleç düzleme oturtulur.

import * as THREE from "three";
import { type Duzlem, isinDuzlemUv, type Nokta2, yakalamaOnerileri } from "../eskiz";
import type { Kontrol, Nokta3 } from "../tipler";
import "./model.css";
import type { EkranModulu, Kabuk, Komut } from "./tip";

const AD = "model";
const ON = `/api/ekran/${AD}/`;
const $ = <T extends HTMLElement = HTMLElement>(s: string) => document.querySelector<T>(s)!;
const SECIM_PX = 10; // ölçü aracında kenara tıklama eşiği
const NOKTA_PX = 9; // sürükleme için noktaya tıklama eşiği

// --------------------------------------------------------------------- sunucu biçimleri

type Arac = "cizgi" | "daire" | "yay" | "olcu" | "ekstruzyon" | "delik" | null;

interface NoktaJ {
  x: number;
  y: number;
  fixed: boolean;
}
type OgeJ =
  | { tur: "line"; p0: string; p1: string; construction: boolean }
  | { tur: "circle"; center: string; r: number; construction: boolean }
  | { tur: "arc"; center: string; start: string; end: string; construction: boolean };
interface KisitJ {
  type: string;
  refs: string[];
  value: number | null;
  side: number;
  internal: boolean;
}
interface EskizJ {
  sema: number;
  plane: Duzlem;
  points: Record<string, NoktaJ>;
  entities: Record<string, OgeJ>;
  constraints: KisitJ[];
}
interface Cozum {
  points: Record<string, Nokta2>;
  radii: Record<string, number>;
  sides: Record<string, number>;
  dof: number;
  freedom: Record<string, number>;
  redundant: number[];
}
interface Adim {
  kimlik: string;
  tur: string;
  [k: string]: unknown;
}
interface ModelJ {
  sema: number;
  ad: string;
  parametreler: Record<string, string | number>;
  adimlar: Adim[];
}
interface AdimRaporu {
  kimlik: string;
  tur: string;
  hata: string | null;
  dof: number | null;
}
interface Rapor {
  adimlar: AdimRaporu[];
  kontroller: Kontrol[];
  hata: { kimlik: string; hata: string; celiski: number[] } | null;
}

class Hata extends Error {
  constructor(
    readonly durum: number,
    readonly detay: unknown,
  ) {
    super(typeof detay === "string" ? detay : ((detay as { hata?: string })?.hata ?? `HTTP ${durum}`));
  }
}

async function istek<T>(yontem: string, yol: string, govde?: unknown, iptal?: AbortSignal): Promise<T> {
  const r = await fetch(ON + yol, {
    method: yontem,
    headers: govde === undefined ? undefined : { "Content-Type": "application/json" },
    body: govde === undefined ? undefined : JSON.stringify(govde),
    signal: iptal,
  });
  if (!r.ok) {
    let detay: unknown = `${r.status} ${r.statusText}`;
    try {
      detay = (await r.json()).detail;
    } catch {
      /* gövde JSON değil */
    }
    throw new Hata(r.status, detay);
  }
  return (await r.json()) as T;
}

// --------------------------------------------------------------------- durum

interface Celiski {
  aday: EskizJ;
  olculer: Record<string, string>;
  kisitlar: number[];
  hata: string;
}

interface Surukle {
  nokta: string;
  taban: EskizJ;
  hedef: Nokta2 | null;
  ucta: AbortController | null;
}

const S = {
  hazir: false,
  model: null as ModelJ | null,
  rapor: null as Rapor | null,
  hacim: null as number | null,
  k: 0,
  agBayt: 0,
  arac: null as Arac,
  // etkin eskiz
  eskiz: null as EskizJ | null,
  olculer: {} as Record<string, string>,
  duzlem: { tur: "XY", ofset: 0 } as Record<string, unknown>,
  cozum: null as Cozum | null,
  dof: 0,
  celiski: null as Celiski | null,
  cizgiBas: null as string | null,
  yayNoktalar: [] as string[],
  olcuOge: null as string | null,
  surukle: null as Surukle | null,
  mesaj: null as string | null,
  sira: Promise.resolve() as Promise<unknown>,
};

let K: Kabuk | null = null;
let alanSol: HTMLElement | null = null;
const temizlik: (() => void)[] = [];
let grup: THREE.Group | null = null;
const parcaG = new THREE.Group();
const eskizG = new THREE.Group();
let girdi: HTMLInputElement | null = null;

function kabuk(): Kabuk {
  if (!K) throw new Error("model ekranı açık değil");
  return K;
}

function dinle<K2 extends keyof HTMLElementEventMap>(
  h: EventTarget,
  olay: K2 | string,
  f: (e: HTMLElementEventMap[K2]) => void,
  secenek?: AddEventListenerOptions,
): void {
  const g = f as EventListener;
  h.addEventListener(olay, g, secenek);
  temizlik.push(() => h.removeEventListener(olay, g, secenek));
}

/** İstekleri sıraya koyar: eskiz işlemleri birbirini ezmesin. */
function sirala<T>(f: () => Promise<T>): Promise<T> {
  const p = S.sira.then(f, f);
  S.sira = p.catch(() => undefined);
  return p;
}

function kopya<T>(x: T): T {
  return JSON.parse(JSON.stringify(x)) as T;
}

function hataYaz(e: unknown): void {
  if (e instanceof DOMException && e.name === "AbortError") return;
  S.mesaj = e instanceof Error ? e.message : String(e);
  console.warn("Model:", S.mesaj);
  panelleriCiz();
}

// --------------------------------------------------------------------- düzlem ve ekran

function duzlem(): Duzlem {
  return S.eskiz?.plane ?? { origin: [0, 0, 0], normal: [0, 0, 1], xdir: [1, 0, 0] };
}

function ydir(d: Duzlem): Nokta3 {
  const [n, x] = [d.normal, d.xdir];
  return [n[1] * x[2] - n[2] * x[1], n[2] * x[0] - n[0] * x[2], n[0] * x[1] - n[1] * x[0]];
}

function dunya(uv: Nokta2, d: Duzlem = duzlem()): THREE.Vector3 {
  const y = ydir(d);
  return new THREE.Vector3(
    d.origin[0] + uv[0] * d.xdir[0] + uv[1] * y[0],
    d.origin[1] + uv[0] * d.xdir[1] + uv[1] * y[1],
    d.origin[2] + uv[0] * d.xdir[2] + uv[1] * y[2],
  );
}

function tuval(): HTMLCanvasElement {
  return kabuk().sahne.renderer.domElement;
}

/** uv → sayfa (client) pikseli. */
function ekranPx(uv: Nokta2): Nokta2 {
  const kamera = kabuk().sahne.kamera;
  kamera.updateMatrixWorld();
  const p = dunya(uv).project(kamera);
  const r = tuval().getBoundingClientRect();
  return [r.left + ((p.x + 1) / 2) * r.width, r.top + ((1 - p.y) / 2) * r.height];
}

/** Sayfa pikseli → düzlem uv (imleç ışını, eskiz.ts). */
function pxUv(x: number, y: number): Nokta2 | null {
  const r = tuval().getBoundingClientRect();
  const ndc = new THREE.Vector2(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1);
  const ray = new THREE.Raycaster();
  const kamera = kabuk().sahne.kamera;
  kamera.updateMatrixWorld();
  ray.setFromCamera(ndc, kamera);
  const o = ray.ray.origin;
  const d = ray.ray.direction;
  return isinDuzlemUv([o.x, o.y, o.z], [d.x, d.y, d.z], duzlem());
}

function noktaUv(id: string): Nokta2 {
  const p = S.eskiz!.points[id];
  return [p.x, p.y];
}

/** Eskiz düzlemine dik, üstten bakış (kontrol kapalıyken çizim kayması yok). */
function eskizKamerasi(): void {
  const s = kabuk().sahne;
  const d = duzlem();
  const n = new THREE.Vector3(...d.normal);
  const y = new THREE.Vector3(...ydir(d));
  const hedef = dunya([0, 0]);
  const boy = Math.max(110, parcaBoyu() * 1.3);
  const uzak = boy / (2 * Math.tan(THREE.MathUtils.degToRad(s.kamera.fov / 2)));
  s.kontrol.target.copy(hedef);
  s.kamera.position.copy(hedef).addScaledVector(n, uzak).addScaledVector(y, -uzak * 0.002);
  s.kontrol.update();
  s.ciz();
}

function parcaBoyu(): number {
  const b = new THREE.Box3().setFromObject(parcaG);
  return b.isEmpty() ? 0 : b.getSize(new THREE.Vector3()).length();
}

function parcayiCercevele(): void {
  const b = new THREE.Box3().setFromObject(parcaG);
  if (b.isEmpty()) return;
  const s = kabuk().sahne;
  const m = b.getCenter(new THREE.Vector3());
  const r = b.getSize(new THREE.Vector3()).length() * 2.1;
  s.kontrol.target.copy(m);
  s.kamera.position.set(m.x - r * 0.42, m.y - r * 0.72, m.z + r * 0.55);
  s.kontrol.update();
  s.ciz();
}

function kontrolAyarla(): void {
  if (!K) return;
  K.sahne.kontrol.enabled = S.eskiz === null && S.arac === null;
}

// --------------------------------------------------------------------- 3B çizim

function agKur(veri: ArrayBuffer): void {
  const u32 = new Uint32Array(veri, 0, 3);
  const [n, m] = [u32[1], u32[2]];
  const yuvarla = (b: number) => b + ((8 - (b % 8)) % 8);
  let ofs = 16;
  const V = new Float32Array(veri.slice(ofs, ofs + n * 12));
  ofs += yuvarla(n * 12);
  const T = new Uint32Array(new Int32Array(veri.slice(ofs, ofs + m * 12)));
  parcaTemizle();
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(V, 3));
  g.setIndex(new THREE.BufferAttribute(T, 1));
  g.computeVertexNormals();
  const mat = new THREE.MeshStandardMaterial({
    color: 0x8fa3b8,
    metalness: 0.55,
    roughness: 0.38,
    polygonOffset: true,
    polygonOffsetFactor: 1,
    polygonOffsetUnits: 1,
  });
  const ag = new THREE.Mesh(g, mat);
  const kenar = new THREE.LineSegments(
    new THREE.EdgesGeometry(g, 25),
    new THREE.LineBasicMaterial({ color: 0x1b222b, transparent: true, opacity: 0.85 }),
  );
  parcaG.add(ag, kenar);
  S.agBayt = veri.byteLength;
}

function parcaTemizle(): void {
  for (const o of parcaG.children) {
    const m = o as THREE.Mesh;
    m.geometry?.dispose();
    (m.material as THREE.Material)?.dispose();
  }
  parcaG.clear();
  S.agBayt = 0;
}

const RENK = { tam: 0xe4e8ec, eksik: 0x5cb8dc, fazla: 0xe3604d, nokta: 0xd6a54e };

function eskizCiz(): void {
  for (const o of eskizG.children) {
    const m = o as THREE.Line;
    m.geometry?.dispose();
    (m.material as THREE.Material)?.dispose();
  }
  eskizG.clear();
  const sk = S.eskiz;
  if (!sk) {
    K?.sahne.ciz();
    return;
  }
  for (const [id, o] of Object.entries(sk.entities)) {
    const P = ogeNoktalari(o).map((uv) => dunya(uv));
    const renk = RENK[durum(id)];
    const cizgi = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(P),
      new THREE.LineBasicMaterial({ color: renk, depthTest: false }),
    );
    cizgi.renderOrder = 10;
    eskizG.add(cizgi);
  }
  const Pn = Object.values(sk.points).map((p) => dunya([p.x, p.y]));
  const nok = new THREE.Points(
    new THREE.BufferGeometry().setFromPoints(Pn),
    new THREE.PointsMaterial({ color: RENK.nokta, size: 7, sizeAttenuation: false, depthTest: false }),
  );
  nok.renderOrder = 11;
  eskizG.add(nok);
  K?.sahne.ciz();
}

function ogeNoktalari(o: OgeJ): Nokta2[] {
  if (o.tur === "line") return [noktaUv(o.p0), noktaUv(o.p1)];
  const c = noktaUv(o.center);
  let r: number;
  let a0 = 0;
  let a1 = 2 * Math.PI;
  if (o.tur === "circle") r = o.r;
  else {
    const s = noktaUv(o.start);
    const e = noktaUv(o.end);
    r = Math.hypot(s[0] - c[0], s[1] - c[1]);
    a0 = Math.atan2(s[1] - c[1], s[0] - c[0]);
    a1 = Math.atan2(e[1] - c[1], e[0] - c[0]);
    while (a1 <= a0) a1 += 2 * Math.PI;
  }
  const n = 64;
  return Array.from({ length: n + 1 }, (_, i) => {
    const a = a0 + ((a1 - a0) * i) / n;
    return [c[0] + r * Math.cos(a), c[1] + r * Math.sin(a)] as Nokta2;
  });
}

// --------------------------------------------------------------------- serbestlik

function durum(id: string): "tam" | "eksik" | "fazla" {
  const c = S.cozum;
  if (!c || !S.eskiz) return "eksik";
  for (const i of c.redundant) if (S.eskiz.constraints[i]?.refs.includes(id)) return "fazla";
  return (c.freedom[id] ?? 0) > 0 ? "eksik" : "tam";
}

/** Sunucu yanıtını eskize yazar (konum, yarıçap, dal). */
function uygula(sk: EskizJ, c: Cozum): void {
  for (const [k, p] of Object.entries(c.points)) {
    if (sk.points[k]) {
      sk.points[k].x = p[0];
      sk.points[k].y = p[1];
    }
  }
  for (const [k, r] of Object.entries(c.radii)) {
    const o = sk.entities[k];
    if (o && o.tur === "circle") o.r = r;
  }
  for (const [k, s] of Object.entries(c.sides)) {
    const ks = sk.constraints[Number(k)];
    if (ks) ks.side = s;
  }
}

function parametreler(): Record<string, string | number> {
  return S.model?.parametreler ?? {};
}

/** Aday eskizi çözer: 200 → eskiz olur; 422 çelişki → kart (eskiz değişmez). */
async function coz(aday: EskizJ, olculer: Record<string, string>): Promise<boolean> {
  try {
    const c = await istek<Cozum>("POST", "eskiz/coz", { eskiz: aday, olculer, parametreler: parametreler() });
    uygula(aday, c);
    S.eskiz = aday;
    S.olculer = olculer;
    S.cozum = c;
    S.dof = c.dof;
    S.celiski = null;
    S.mesaj = null;
    eskizCiz();
    panelleriCiz();
    return true;
  } catch (e) {
    if (e instanceof Hata && e.durum === 422 && typeof e.detay === "object" && e.detay !== null) {
      const d = e.detay as { hata: string; kisitlar: number[] };
      S.celiski = { aday, olculer, kisitlar: d.kisitlar ?? [], hata: d.hata };
      panelleriCiz();
      return false;
    }
    hataYaz(e);
    return false;
  }
}

// --------------------------------------------------------------------- eskiz düzenleme

function yeniKimlik(on: string, var_: Record<string, unknown>): string {
  let i = 1;
  while (`${on}${i}` in var_) i++;
  return `${on}${i}`;
}

function eskizBaslat(d: Duzlem, duzlemAdim: Record<string, unknown>): void {
  S.eskiz = {
    sema: 1,
    plane: d,
    points: { o: { x: 0, y: 0, fixed: true } }, // uv orijininde sabit referans noktası
    entities: {},
    constraints: [],
  };
  S.olculer = {};
  S.duzlem = duzlemAdim;
  S.cozum = null;
  S.dof = 0;
  S.celiski = null;
  S.cizgiBas = null;
  aracSec("cizgi");
  eskizKamerasi();
  eskizCiz();
  panelleriCiz();
}

function eskizBitir(): void {
  S.eskiz = null;
  S.cozum = null;
  S.celiski = null;
  S.cizgiBas = null;
  aracSec(null);
  eskizCiz();
  parcayiCercevele();
  panelleriCiz();
}

function uclar(haric?: string): { kimlik: string; px: Nokta2 }[] {
  return Object.keys(S.eskiz!.points)
    .filter((k) => k !== haric)
    .map((k) => ({ kimlik: k, px: ekranPx(noktaUv(k)) }));
}

/** Tıklanan yer: yakalanan nokta ya da yeni nokta (aday eskize eklenir). */
function noktaAl(aday: EskizJ, px: Nokta2, bas?: string): { id: string; oneriler: ReturnType<typeof yakalamaOnerileri> } | null {
  const basPx = bas ? ekranPx(noktaUv(bas)) : px;
  const oneriler = yakalamaOnerileri(basPx, px, uclar(bas));
  const cak = oneriler.find((o) => o.tur === "cakisik");
  if (cak?.kimlik) return { id: cak.kimlik, oneriler };
  const uv = pxUv(px[0], px[1]);
  if (!uv) return null;
  const id = yeniKimlik("p", aday.points);
  aday.points[id] = { x: uv[0], y: uv[1], fixed: false };
  return { id, oneriler };
}

function kisit(type: string, refs: string[], value: number | null = null): KisitJ {
  return { type, refs, value, side: 0, internal: false };
}

async function cizgiTik(px: Nokta2): Promise<void> {
  const aday = kopya(S.eskiz!);
  const bas = S.cizgiBas;
  const n = noktaAl(aday, px, bas ?? undefined);
  if (!n) return;
  if (bas === null) {
    S.eskiz = aday;
    S.cizgiBas = n.id;
    eskizCiz();
    return;
  }
  if (n.id === bas) return;
  const id = yeniKimlik("c", aday.entities);
  aday.entities[id] = { tur: "line", p0: bas, p1: n.id, construction: false };
  for (const o of n.oneriler) {
    if (o.tur === "yatay") aday.constraints.push(kisit("horizontal", [id]));
    if (o.tur === "dikey") aday.constraints.push(kisit("vertical", [id]));
  }
  const kapandi = n.oneriler.some((o) => o.tur === "cakisik");
  if (await coz(aday, { ...S.olculer })) S.cizgiBas = kapandi ? null : n.id;
}

async function daireTik(px: Nokta2): Promise<void> {
  const aday = kopya(S.eskiz!);
  if (S.cizgiBas === null) {
    const n = noktaAl(aday, px);
    if (!n) return;
    S.eskiz = aday;
    S.cizgiBas = n.id;
    eskizCiz();
    return;
  }
  const uv = pxUv(px[0], px[1]);
  if (!uv) return;
  const c = noktaUv(S.cizgiBas);
  const r = Math.hypot(uv[0] - c[0], uv[1] - c[1]); // başlangıç tahmini; çözücü ölçüyle düzeltir
  if (r <= 0) return;
  aday.entities[yeniKimlik("o", aday.entities)] = { tur: "circle", center: S.cizgiBas, r, construction: false };
  if (await coz(aday, { ...S.olculer })) S.cizgiBas = null;
}

async function yayTik(px: Nokta2): Promise<void> {
  const aday = kopya(S.eskiz!);
  const n = noktaAl(aday, px);
  if (!n) return;
  S.yayNoktalar.push(n.id);
  if (S.yayNoktalar.length < 3) {
    S.eskiz = aday;
    eskizCiz();
    return;
  }
  const [c, s, e] = S.yayNoktalar;
  S.yayNoktalar = [];
  const id = yeniKimlik("y", aday.entities);
  aday.entities[id] = { tur: "arc", center: c, start: s, end: e, construction: false };
  await coz(aday, { ...S.olculer });
}

function kenaraUzaklik(p: Nokta2, a: Nokta2, b: Nokta2): number {
  const [dx, dy] = [b[0] - a[0], b[1] - a[1]];
  const L = dx * dx + dy * dy;
  const t = L > 0 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L)) : 0;
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
}

function ogeBul(px: Nokta2): string | null {
  let en: { id: string; d: number } | null = null;
  for (const [id, o] of Object.entries(S.eskiz!.entities)) {
    const P = ogeNoktalari(o).map(ekranPx);
    for (let i = 0; i + 1 < P.length; i++) {
      const d = kenaraUzaklik(px, P[i], P[i + 1]);
      if (d <= SECIM_PX && (!en || d < en.d)) en = { id, d };
    }
  }
  return en?.id ?? null;
}

function girdiGoster(px: Nokta2 | null, ipucu: string, deger = ""): void {
  const g = girdi!;
  const r = $("#sahneKap").getBoundingClientRect();
  const [x, y] = px ?? [r.left + r.width / 2, r.top + r.height / 2];
  g.style.left = `${Math.min(Math.max(x - r.left + 14, 8), Math.max(r.width - 150, 8))}px`;
  g.style.top = `${Math.min(Math.max(y - r.top - 14, 8), Math.max(r.height - 40, 8))}px`;
  g.placeholder = ipucu;
  g.setAttribute("aria-label", ipucu);
  g.value = deger;
  g.hidden = false;
  g.focus();
}

function girdiGizle(): void {
  if (!girdi || girdi.hidden) return;
  girdi.hidden = true;
  girdi.blur();
}

function olcuTik(px: Nokta2): void {
  const id = ogeBul(px);
  if (!id) return;
  S.olcuOge = id;
  const o = S.eskiz!.entities[id];
  girdiGoster(px, o.tur === "line" ? "Boy (sayı ya da =ifade)" : "Yarıçap (sayı ya da =ifade)");
}

async function olcuUygula(id: string, metin: string): Promise<void> {
  if (!S.eskiz?.entities[id]) return;
  const aday = kopya(S.eskiz);
  const o = aday.entities[id];
  aday.constraints.push(kisit(o.tur === "line" ? "length" : "radius", [id], 1)); // değer olculer'den
  const olculer = { ...S.olculer, [String(aday.constraints.length - 1)]: metin };
  await coz(aday, olculer);
}

/** Çelişki kartında bir kısıt kaldırılır; ölçü sıraları kayar. */
async function kisitKaldir(i: number): Promise<void> {
  const c = S.celiski;
  if (!c) return;
  const aday = kopya(c.aday);
  aday.constraints.splice(i, 1);
  const olculer: Record<string, string> = {};
  for (const [k, v] of Object.entries(c.olculer)) {
    const j = Number(k);
    if (j < i) olculer[k] = v;
    else if (j > i) olculer[String(j - 1)] = v;
  }
  await coz(aday, olculer);
}

// --------------------------------------------------------------------- sürükleme

function noktaBul(px: Nokta2): string | null {
  let en: { id: string; d: number } | null = null;
  for (const [id, p] of Object.entries(S.eskiz!.points)) {
    if (p.fixed) continue;
    const q = ekranPx([p.x, p.y]);
    const d = Math.hypot(q[0] - px[0], q[1] - px[1]);
    if (d <= NOKTA_PX && (!en || d < en.d)) en = { id, d };
  }
  return en?.id ?? null;
}

async function surukleGonder(s: Surukle, son: boolean): Promise<void> {
  if (!s.hedef) return;
  const hedef = s.hedef;
  s.hedef = null;
  const iptal = new AbortController();
  s.ucta = iptal;
  try {
    const c = await istek<Cozum>(
      "POST",
      "eskiz/surukle",
      { eskiz: s.taban, nokta: s.nokta, hedef, olculer: S.olculer, parametreler: parametreler() },
      iptal.signal,
    );
    if (S.surukle !== s && !son) return;
    const sk = kopya(s.taban);
    uygula(sk, c);
    S.eskiz = sk;
    S.cozum = c;
    S.dof = c.dof;
    eskizCiz();
    if (son) panelleriCiz();
  } catch (e) {
    hataYaz(e);
  } finally {
    if (s.ucta === iptal) s.ucta = null;
  }
  if (!son && S.surukle === s && s.hedef) void surukleGonder(s, false);
}

// --------------------------------------------------------------------- model, geçmiş, ekstrüzyon

async function modelYaz(m: ModelJ, k?: number): Promise<void> {
  const J = await istek<{ rapor: Rapor; hacim: number | null }>("PUT", "", m);
  S.model = m;
  S.rapor = J.rapor;
  S.hacim = J.hacim;
  S.k = k ?? m.adimlar.length;
  await agYukle();
  panelleriCiz();
}

/** İlk k adımda katı var mı (yalnız eskizse ağ istenmez). */
function katiVar(k: number): boolean {
  const m = S.model!;
  const r = S.rapor;
  return m.adimlar.slice(0, k).some((a, i) => a.tur === "ekstruzyon" && !(r && r.adimlar[i]?.hata));
}

async function agYukle(): Promise<void> {
  if (!S.model) return;
  if (!katiVar(S.k)) {
    parcaTemizle();
    K?.sahne.ciz();
    return;
  }
  const veri = await (await fetch(`${ON}ag?k=${S.k}`)).arrayBuffer();
  if (!K) return;
  agKur(veri);
  K.sahne.ciz();
}

async function gecmiseGit(k: number): Promise<void> {
  if (!S.model) return;
  S.k = Math.max(0, Math.min(S.model.adimlar.length, k));
  panelleriCiz();
  await agYukle();
}

async function ekstruzyonUygula(metin: string): Promise<void> {
  const m = S.model;
  const sk = S.eskiz;
  if (!m || !sk) {
    S.mesaj = "Ekstrüzyon için önce bir eskiz çiz (XY'de yeni eskiz)";
    panelleriCiz();
    return;
  }
  const adimlar = m.adimlar.slice(0, S.k);
  const eskizId = yeniKimlik("eskiz", Object.fromEntries(adimlar.map((a) => [a.kimlik, 1])));
  const kesme = metin.trim().startsWith("-");
  const katili = katiVar(S.k);
  const yeni: ModelJ = {
    ...m,
    adimlar: [
      ...adimlar,
      { kimlik: eskizId, tur: "eskiz", duzlem: S.duzlem, eskiz: sk, olculer: S.olculer },
      {
        kimlik: yeniKimlik("govde", Object.fromEntries(adimlar.map((a) => [a.kimlik, 1]))),
        tur: "ekstruzyon",
        eskiz: eskizId,
        bolgeler: "hepsi",
        mesafe: kesme ? metin.trim().slice(1) : metin.trim(),
        yon: "ileri",
        islem: !katili ? "yeni" : kesme ? "kes" : "ekle",
        bitis: "mesafe",
      },
    ],
  };
  await modelYaz(yeni);
  eskizBitir();
}

async function parametreDegistir(ad: string, deger: string): Promise<void> {
  const m = S.model;
  if (!m) return;
  await modelYaz({ ...m, parametreler: { ...m.parametreler, [ad]: deger } }, undefined);
}

async function tezgahaGonder(): Promise<void> {
  const J = await kabuk().api.postJson<{ ad: string }>("tezgaha-gonder", {}, "Model: Tezgah'a gönder");
  kabuk().git(`#/freze?is=${encodeURIComponent(J.ad)}`);
}

// --------------------------------------------------------------------- araçlar ve olaylar

const ARAC_TUSLARI: Record<string, Exclude<Arac, null>> = {
  l: "cizgi",
  c: "daire",
  a: "yay",
  d: "olcu",
  e: "ekstruzyon",
  h: "delik",
};
const ARAC_ADI: Record<Exclude<Arac, null>, string> = {
  cizgi: "Çizgi (L)",
  daire: "Daire (C)",
  yay: "Yay (A)",
  olcu: "Ölçü (D)",
  ekstruzyon: "Ekstrüzyon (E)",
  delik: "Delik (H)",
};

function aracSec(a: Arac): void {
  S.arac = a;
  S.cizgiBas = null;
  S.yayNoktalar = [];
  S.olcuOge = null;
  girdiGizle();
  if (a === "ekstruzyon") girdiGoster(null, "Mesafe (sayı ya da =ifade; − kesim)");
  kontrolAyarla();
  if (K) {
    tuval().style.cursor = a === null ? "" : "crosshair";
    eskizCiz();
    araclariCiz();
  }
}

function tus(e: KeyboardEvent): void {
  const hedef = e.target as HTMLElement;
  const yaziyor = hedef.matches?.("input, textarea, select") || hedef.isContentEditable;
  if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "z") {
    if (yaziyor || S.eskiz) return;
    e.preventDefault();
    void gecmiseGit(S.k + (e.shiftKey ? 1 : -1));
    return;
  }
  if (e.ctrlKey || e.metaKey || e.altKey || yaziyor) return;
  if (e.key === "Escape") {
    if (S.arac !== null) aracSec(null);
    else if (S.celiski) {
      S.celiski = null;
      panelleriCiz();
    }
    return;
  }
  const a = ARAC_TUSLARI[e.key.toLowerCase()];
  if (a) {
    e.preventDefault();
    aracSec(a);
  }
}

function tik(e: MouseEvent): void {
  if (!S.eskiz || S.arac === null || e.button !== 0) return;
  const px: Nokta2 = [e.clientX, e.clientY];
  if (S.arac === "cizgi") void sirala(() => cizgiTik(px));
  else if (S.arac === "daire") void sirala(() => daireTik(px));
  else if (S.arac === "yay") void sirala(() => yayTik(px));
  else if (S.arac === "olcu") olcuTik(px);
}

function basili(e: PointerEvent): void {
  if (!S.eskiz || S.arac !== null || e.button !== 0) return;
  const id = noktaBul([e.clientX, e.clientY]);
  if (!id) return;
  e.preventDefault();
  S.surukle = { nokta: id, taban: kopya(S.eskiz), hedef: null, ucta: null };
}

function hareket(e: PointerEvent): void {
  const s = S.surukle;
  if (!s) return;
  const uv = pxUv(e.clientX, e.clientY);
  if (!uv) return;
  s.hedef = uv;
  if (!s.ucta) void surukleGonder(s, false);
}

function birakildi(e: PointerEvent): void {
  const s = S.surukle;
  if (!s) return;
  S.surukle = null; // ara yanıtlar artık uygulanmaz
  s.ucta?.abort();
  const uv = pxUv(e.clientX, e.clientY);
  if (!uv) return;
  s.hedef = uv;
  void sirala(() => surukleGonder(s, true));
}

function girdiTus(e: KeyboardEvent): void {
  if (e.key === "Escape") {
    e.stopPropagation();
    aracSec(null);
    return;
  }
  if (e.key !== "Enter") return;
  e.preventDefault();
  const metin = girdi!.value.trim();
  if (!metin) return;
  const a = S.arac;
  const oge = S.olcuOge;
  girdiGizle();
  aracSec(null);
  if (a === "olcu" && oge) {
    void sirala(() => olcuUygula(oge, metin)).catch(hataYaz);
  } else if (a === "ekstruzyon") void sirala(() => ekstruzyonUygula(metin)).catch(hataYaz);
}

// --------------------------------------------------------------------- paneller

function el<T extends keyof HTMLElementTagNameMap>(etiket: T, sinif?: string, metin?: string): HTMLElementTagNameMap[T] {
  const e = document.createElement(etiket);
  if (sinif) e.className = sinif;
  if (metin !== undefined) e.textContent = metin;
  return e;
}

function sayiYaz(x: number): string {
  return x.toLocaleString("tr-TR", { maximumFractionDigits: 1 });
}

function araclariCiz(): void {
  const kap = alanSol?.querySelector<HTMLElement>(".m-araclar");
  if (!kap) return;
  kap.replaceChildren(
    ...Object.entries(ARAC_ADI).map(([a, ad]) => {
      const b = el("button", "m-arac", ad);
      b.type = "button";
      b.setAttribute("aria-pressed", String(S.arac === a));
      b.addEventListener("click", () => aracSec(S.arac === a ? null : (a as Arac)));
      return b;
    }),
  );
}

function solCiz(): void {
  const sol = alanSol;
  const m = S.model;
  if (!sol || !m) return;
  const kap = el("div", "m-sol");

  const bas = el("div", "m-baslik");
  bas.append(el("b", undefined, m.ad), el("span", undefined, `${m.adimlar.length} adım`));
  kap.append(bas);

  const eylem = el("div", "m-eylem");
  const xy = el("button", "m-dugme", "XY'de yeni eskiz");
  xy.type = "button";
  xy.dataset.testid = "duzlem-xy";
  xy.addEventListener("click", () => eskizBaslat({ origin: [0, 0, 0], normal: [0, 0, 1], xdir: [1, 0, 0] }, { tur: "XY", ofset: 0 }));
  const gonder = el("button", "m-dugme birincil", "Tezgah'a gönder");
  gonder.type = "button";
  gonder.dataset.testid = "tezgaha-gonder";
  gonder.disabled = !katiVar(m.adimlar.length);
  gonder.addEventListener("click", () => void tezgahaGonder().catch(hataYaz));
  eylem.append(xy, gonder);
  kap.append(eylem);

  if (S.eskiz) {
    const bitir = el("button", "m-dugme", "Eskizi bırak");
    bitir.type = "button";
    bitir.addEventListener("click", eskizBitir);
    eylem.append(bitir);
  }

  kap.append(el("h3", undefined, "Araçlar"), el("div", "m-araclar"));

  kap.append(el("h3", undefined, "Parametreler"));
  const tablo = el("div", "m-parametreler");
  tablo.dataset.testid = "parametre-tablosu";
  const adlar = Object.keys(m.parametreler);
  if (!adlar.length) tablo.append(el("p", "m-soluk", "Parametre yok"));
  for (const ad of adlar) {
    const satir = el("label", "m-parametre");
    const g = el("input");
    g.dataset.testid = "model-parametre";
    g.dataset.ad = ad;
    g.value = String(m.parametreler[ad]);
    g.spellcheck = false;
    g.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      void sirala(() => parametreDegistir(ad, g.value.trim())).catch(hataYaz);
    });
    satir.append(el("span", undefined, ad), g);
    tablo.append(satir);
  }
  kap.append(tablo);

  kap.append(el("h3", undefined, "Geçmiş"));
  const serit = el("ol", "m-gecmis");
  serit.dataset.testid = "gecmis-seridi";
  serit.setAttribute("aria-label", "Model geçmişi (Ctrl Z / Ctrl Shift Z)");
  m.adimlar.forEach((a, i) => {
    const li = el("li");
    const b = el("button", "m-dilim");
    b.type = "button";
    b.dataset.testid = "gecmis-dilim";
    b.dataset.k = String(i + 1);
    b.setAttribute("aria-current", String(i + 1 === S.k));
    if (i + 1 > S.k) b.classList.add("sonra");
    const hata = S.rapor?.adimlar[i]?.hata;
    if (hata) {
      b.classList.add("hatali");
      b.title = hata;
    }
    b.append(el("span", "tur", a.tur === "eskiz" ? "Eskiz" : a.tur === "ekstruzyon" ? "Ekstrüzyon" : "Delik"), el("b", undefined, a.kimlik));
    b.addEventListener("click", () => void gecmiseGit(i + 1).catch(hataYaz));
    li.append(b);
    serit.append(li);
  });
  kap.append(serit);

  sol.replaceChildren(kap);
  araclariCiz();
}

function mufettisCiz(): void {
  if (!K) return;
  const kap = el("div", "m-mufettis");
  const hacim = el("div", "m-kanit");
  hacim.append(el("span", undefined, "Hacim"));
  if (S.hacim !== null) {
    const d = el("b", undefined, `${sayiYaz(S.hacim)} mm³`);
    d.dataset.testid = "kanit-hacim";
    hacim.append(d);
  } else hacim.append(el("b", "m-soluk", "katı yok"));
  kap.append(hacim);

  if (S.eskiz) {
    const s = el("div", "m-kanit");
    s.append(el("span", undefined, "Eskiz"), el("b", undefined, S.dof === 0 && S.cozum ? "Tam tanımlı" : `${S.dof} serbestlik`));
    kap.append(s);
  }

  if (S.celiski) {
    const kart = el("div", "m-celiski");
    kart.dataset.testid = "celiski-karti";
    kart.setAttribute("role", "alert");
    kart.append(el("b", undefined, "Çelişen kısıtlar"), el("p", undefined, "Birini kaldırmak için tıkla."));
    for (const i of S.celiski.kisitlar) {
      const k = S.celiski.aday.constraints[i];
      const b = el("button", "m-kisit");
      b.type = "button";
      b.dataset.testid = "celiski-kisit";
      b.dataset.kisit = String(i);
      const deger = S.celiski.olculer[String(i)] ?? (k?.value ?? "");
      b.textContent = `#${i} ${k?.type ?? "?"}(${k?.refs.join(", ") ?? ""})${deger !== "" && deger !== null ? ` = ${deger}` : ""}`;
      b.addEventListener("click", () => void sirala(() => kisitKaldir(i)).catch(hataYaz));
      kart.append(b);
    }
    kap.append(kart);
  }
  if (S.mesaj) {
    const h = el("p", "m-mesaj", S.mesaj);
    h.setAttribute("role", "status");
    kap.append(h);
  }
  K.mufettis(kap);
  K.kanitlar(S.rapor?.kontroller ?? []);
}

function hudCiz(): void {
  const b = $("#hudBaslik");
  b.replaceChildren(
    el("b", undefined, S.eskiz ? "Eskiz" : "Model"),
    el("span", undefined, S.eskiz ? "L çizgi · D ölçü · E ekstrüzyon · Esc araç bırak" : `Geçmiş ${S.k}/${S.model?.adimlar.length ?? 0}`),
  );
  const d = $("#hudDro");
  const sayac = el("div", "m-dof");
  sayac.dataset.testid = "dof-sayaci";
  sayac.setAttribute("aria-live", "polite");
  sayac.append(el("span", undefined, "DOF"), el("b", undefined, String(S.dof)));
  sayac.classList.toggle("tam", S.dof === 0);
  d.replaceChildren(sayac);
}

function panelleriCiz(): void {
  solCiz();
  mufettisCiz();
  hudCiz();
}

function komutlar(): Komut[] {
  return [
    { kimlik: "model-xy", baslik: "XY'de yeni eskiz", anahtar_kelimeler: ["eskiz"], calistir: () => eskizBaslat({ origin: [0, 0, 0], normal: [0, 0, 1], xdir: [1, 0, 0] }, { tur: "XY", ofset: 0 }) },
    { kimlik: "model-gonder", baslik: "Tezgah'a gönder", anahtar_kelimeler: ["freze", "cam"], calistir: () => tezgahaGonder() },
  ];
}

// --------------------------------------------------------------------- EkranModulu

const ekran: EkranModulu = {
  ad: AD,
  baslik: "Model",
  tus: "7",
  async ac(alan: HTMLElement, kabuk_: Kabuk, _secim?: string): Promise<void> {
    K = kabuk_;
    alanSol = alan;
    S.hazir = false;
    grup = K.sahne.katman(AD);
    grup.add(parcaG, eskizG);
    const kancaAlanlari = {
      get hazir() {
        return S.hazir;
      },
      arac: () => S.arac,
      dof: () => S.dof,
      durum: (id: string) => durum(id),
      ogeler: () => (S.eskiz ? Object.entries(S.eskiz.entities).filter(([, o]) => !o.construction).map(([k]) => k) : []),
      noktalar: () => (S.eskiz ? Object.keys(S.eskiz.points) : []),
      nokta: (id: string) => (S.eskiz?.points[id] ? noktaUv(id) : null),
      ekranPx: (uv: Nokta2) => ekranPx(uv),
      kenarOrtasi: (id: string) => {
        const o = S.eskiz?.entities[id];
        if (!o || o.tur !== "line") throw new Error(`Çizgi yok: ${id}`);
        const [a, b] = [noktaUv(o.p0), noktaUv(o.p1)];
        return ekranPx([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]);
      },
      hacim: () => S.hacim,
      gecmisK: () => S.k,
      adimSayisi: () => S.model?.adimlar.length ?? 0,
      agBayt: () => S.agBayt,
    };
    Object.defineProperties(K.kanca, Object.getOwnPropertyDescriptors(kancaAlanlari));

    const t = tuval();
    t.dataset.testid = "eskiz-alani";
    temizlik.push(() => {
      delete t.dataset.testid;
      t.style.cursor = "";
    });
    girdi = el("input", "m-girdi");
    girdi.dataset.testid = "olcu-girdi";
    girdi.hidden = true;
    girdi.spellcheck = false;
    girdi.autocomplete = "off";
    girdi.addEventListener("keydown", girdiTus);
    $("#sahneKap").append(girdi);
    const g = girdi;
    temizlik.push(() => g.remove());
    dinle(t, "click", (e) => tik(e as MouseEvent));
    dinle(t, "pointerdown", (e) => basili(e as PointerEvent));
    dinle(window, "pointermove", (e) => hareket(e as PointerEvent));
    dinle(window, "pointerup", (e) => birakildi(e as PointerEvent));
    dinle(document, "keydown", (e) => tus(e as KeyboardEvent));

    S.eskiz = null;
    S.celiski = null;
    S.mesaj = null;
    S.arac = null;
    const m = await istek<ModelJ>("GET", "");
    if (!K) return;
    await modelYaz(m);
    if (!K) return;
    kontrolAyarla();
    parcayiCercevele();
    if (!katiVar(m.adimlar.length)) eskizKamerasiBos();
    S.hazir = true;
  },

  kapat(): void {
    for (const f of temizlik.splice(0)) f();
    if (K) {
      K.sahne.kontrol.enabled = true;
      grup?.remove(parcaG, eskizG);
      K.sahne.katmanBirak(AD);
    }
    parcaTemizle();
    S.eskiz = null;
    eskizCiz();
    S.hazir = false;
    S.surukle = null;
    K = null;
    alanSol = null;
    girdi = null;
  },

  async tazele(): Promise<void> {
    if (!K) return;
    const m = await istek<ModelJ>("GET", "");
    await modelYaz(m);
  },

  komutlar,
};

/** Boş modelde XY'ye üstten bakış (ilk eskiz için hazır). */
function eskizKamerasiBos(): void {
  eskizKamerasi();
}


export default ekran;
