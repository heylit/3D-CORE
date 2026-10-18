// SPEC 65b — "Görünüm" ekranı (A3): örnek montajı gerçekçi malzeme görünümüyle (PBR) gösterir.
// Sunucu: tezgah/ekranlar/gorunum.py. Sahneye yalnız "gorunum" katmanına çizer; ortam haritası ve ton eşleme
// ekran açıkken kurulur, kapanınca renderer önceki hâline döner.

import * as THREE from "three";

import {
  agBirak,
  agKaydet,
  aktifMod,
  gorunumModu,
  malzemeOlustur,
  ortamBirak,
  ortamKur,
  ortamVar,
  type Gorunum,
  type GorunumKanca,
  type GorunumModu,
  type MontajGorunumu,
} from "../gorunum";
import { isi } from "../sahne";
import type { EkranModulu, Kabuk, Komut } from "./tip";

const AD = "gorunum";
const MODLAR: [GorunumModu, string][] = [
  ["gercekci", "Gerçekçi"],
  ["teknik", "Teknik"],
  ["analiz", "Analiz"],
];

interface YuzGrubu {
  gorunum: Gorunum;
  indeksler: number[];
}
interface Bilesen {
  ad: string;
  T: number[][];
  gorunum: Gorunum;
  yuzler: Record<string, YuzGrubu>;
}

let K: Kabuk | null = null;
let grup: THREE.Group | null = null;
let hazir = false;
const aglar = new Map<string, THREE.Mesh>();
const temizlik: (() => void)[] = [];

/** model_kopru.ag_ikili: başlık (sema, n, m, boşluk) + float32 köşe + int32 üçgen + int32 yüz; bloklar 8'e hizalı. */
function agCoz(veri: ArrayBuffer): { V: Float32Array; T: Uint32Array; Y: Int32Array } {
  const [, n, m] = new Uint32Array(veri, 0, 3);
  const hizala = (b: number) => b + ((8 - (b % 8)) % 8);
  let ofs = 16;
  const V = new Float32Array(veri.slice(ofs, ofs + n * 12));
  ofs += hizala(n * 12);
  const T = new Uint32Array(new Int32Array(veri.slice(ofs, ofs + m * 12)));
  ofs += hizala(m * 12);
  const Y = new Int32Array(veri.slice(ofs, ofs + m * 4));
  return { V, T, Y };
}

/** Üçgenleri malzeme grubuna göre sıralı geometri: grup 0 bileşen görünümü, 1.. bitimli yüz grupları. */
function geometriKur(veri: ArrayBuffer, gruplar: number[][]): THREE.BufferGeometry {
  const { V, T, Y } = agCoz(veri);
  const yuzGrubu = new Map<number, number>();
  gruplar.forEach((idx, i) => idx.forEach((y) => yuzGrubu.set(y, i + 1)));
  const m = Y.length;
  const grupOf = (k: number) => yuzGrubu.get(Y[k]) ?? 0;
  const sira = Array.from({ length: m }, (_, k) => k).sort((a, b) => grupOf(a) - grupOf(b) || a - b);
  const index = new Uint32Array(m * 3);
  sira.forEach((k, j) => index.set(T.subarray(3 * k, 3 * k + 3), 3 * j));
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(V, 3));
  g.setIndex(new THREE.BufferAttribute(index, 1));
  let bas = 0;
  for (let i = 0; i <= gruplar.length; i++) {
    let say = 0;
    while (bas + say < m && grupOf(sira[bas + say]) === i) say++;
    g.addGroup(3 * bas, 3 * say, i);
    bas += say;
  }
  g.computeVertexNormals();
  return g;
}

/** Analiz modu için vertex rengi: yüksekliğe göre ısı haritası (örnek skaler alan). */
function analizRengi(g: THREE.BufferGeometry, zMin: number, zMax: number, T: THREE.Matrix4): void {
  const p = g.getAttribute("position") as THREE.BufferAttribute;
  const renk = new Float32Array(p.count * 3);
  const c = new THREE.Color();
  const v = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i).applyMatrix4(T);
    isi((v.z - zMin) / Math.max(zMax - zMin, 1e-9), c).toArray(renk, 3 * i);
  }
  g.setAttribute("color", new THREE.BufferAttribute(renk, 3));
}

async function gorunumAl(): Promise<MontajGorunumu> {
  const r = await fetch("/api/gorunum?montaj=ornek");
  if (!r.ok) throw new Error(`GET /api/gorunum: ${r.status}`);
  return (await r.json()) as MontajGorunumu;
}

function matris(T: number[][]): THREE.Matrix4 {
  const M = new THREE.Matrix4();
  M.set(...(T.flat() as [number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number]));
  return M;
}

function cercevele(s: Kabuk["sahne"], g: THREE.Object3D): void {
  const b = new THREE.Box3().setFromObject(g);
  if (b.isEmpty()) return;
  const m = b.getCenter(new THREE.Vector3());
  const r = b.getSize(new THREE.Vector3()).length() * 1.6;
  s.kontrol.target.copy(m);
  // önden, hafif soldan ve yukarıdan: yan yana parçalar ekranda üst üste binmez
  s.kamera.position.set(m.x - r * 0.15, m.y - r * 0.85, m.z + r * 0.5);
  s.kontrol.update();
}

function modSec(yeni: GorunumModu, dugmeler: Map<GorunumModu, HTMLButtonElement>): void {
  gorunumModu(yeni);
  for (const [m, d] of dugmeler) d.classList.toggle("secili", m === yeni);
  K?.sahne.ciz();
}

function panelKur(alan: HTMLElement): Map<GorunumModu, HTMLButtonElement> {
  const kap = document.createElement("div");
  kap.className = "gorunum-panel";
  const baslik = document.createElement("h3");
  baslik.textContent = "Görünüm modu";
  kap.append(baslik);
  const dugmeler = new Map<GorunumModu, HTMLButtonElement>();
  for (const [m, ad] of MODLAR) {
    const d = document.createElement("button");
    d.textContent = ad;
    d.dataset.testid = "gorunum-modu";
    d.dataset.mod = m;
    d.addEventListener("click", () => modSec(m, dugmeler));
    dugmeler.set(m, d);
    kap.append(d);
  }
  alan.append(kap);
  temizlik.push(() => kap.remove());
  return dugmeler;
}

function kancaKur(k: Kabuk): void {
  const kanca: GorunumKanca & { hazir: boolean; bilesenler(): string[] } = {
    get hazir() {
      return hazir;
    },
    bilesenler: () => [...aglar.keys()],
    mod: () => aktifMod(),
    malzemeler: (bilesen: string) => {
      const ag = aglar.get(bilesen);
      if (!ag) throw new Error(`Bilinmeyen bileşen: ${bilesen}`);
      const L = Array.isArray(ag.material) ? ag.material : [ag.material];
      return L.map((m) => {
        const p = m as THREE.MeshPhysicalMaterial;
        return {
          tip: m.type,
          metalness: p.metalness ?? 0,
          roughness: p.roughness ?? 1,
          clearcoat: p.clearcoat ?? 0,
          vertexColors: m.vertexColors,
        };
      });
    },
    ortamVar: () => ortamVar(),
    tonEsleme: () => k.sahne.renderer.toneMapping,
    programSayisi: () => k.sahne.renderer.info.programs?.length ?? 0,
    ekranKutusu: (bilesen: string) => ekranKutusu(k, bilesen),
  };
  Object.defineProperties(k.kanca, Object.getOwnPropertyDescriptors(kanca));
}

/** Bileşenin sınır kutusunun canvas üzerindeki izdüşümü [x0, y0, x1, y1] (CSS pikseli); görünmüyorsa null. */
function ekranKutusu(k: Kabuk, bilesen: string): [number, number, number, number] | null {
  const ag = aglar.get(bilesen);
  if (!ag) throw new Error(`Bilinmeyen bileşen: ${bilesen}`);
  ag.geometry.computeBoundingBox();
  const b = ag.geometry.boundingBox!.clone().applyMatrix4(ag.matrixWorld);
  const kamera = k.sahne.kamera;
  kamera.updateMatrixWorld();
  const tuval = k.sahne.renderer.domElement.getBoundingClientRect();
  let [x0, y0, x1, y1] = [Infinity, Infinity, -Infinity, -Infinity];
  const v = new THREE.Vector3();
  for (let i = 0; i < 8; i++) {
    v.set(i & 1 ? b.max.x : b.min.x, i & 2 ? b.max.y : b.min.y, i & 4 ? b.max.z : b.min.z).project(kamera);
    if (v.z < -1 || v.z > 1) return null; // kameranın arkasında / uzak düzlemin ötesinde
    const x = ((v.x + 1) / 2) * tuval.width;
    const y = ((1 - v.y) / 2) * tuval.height;
    [x0, y0, x1, y1] = [Math.min(x0, x), Math.min(y0, y), Math.max(x1, x), Math.max(y1, y)];
  }
  [x0, y0] = [Math.max(0, x0), Math.max(0, y0)];
  [x1, y1] = [Math.min(tuval.width, x1), Math.min(tuval.height, y1)];
  return x1 > x0 && y1 > y0 ? [x0, y0, x1, y1] : null;
}

function temizle(): void {
  for (const ag of aglar.values()) {
    agBirak(ag);
    ag.geometry.dispose();
    grup?.remove(ag);
  }
  aglar.clear();
}

function komutlar(): Komut[] {
  return MODLAR.map(([m, ad]) => ({
    kimlik: `gorunum-${m}`,
    baslik: `Görünüm: ${ad}`,
    anahtar_kelimeler: ["pbr", "malzeme", "görünüm"],
    calistir: () => {
      gorunumModu(m);
      K?.sahne.ciz();
    },
  }));
}

const ekran: EkranModulu = {
  ad: AD,
  baslik: "Görünüm",
  async ac(alan: HTMLElement, kabuk: Kabuk): Promise<void> {
    K = kabuk;
    hazir = false;
    grup = K.sahne.katman(AD);
    const sahne = grup.parent as THREE.Scene;
    ortamKur(K.sahne.renderer, sahne);
    kancaKur(K);
    const dugmeler = panelKur(alan);
    // geometri ve konumlar ekranın ucundan, görünümler SPEC 65b ucundan (GET /api/gorunum)
    const [veri, gorunumler] = await Promise.all([
      K.api.getJson<{ sema: number; bilesenler: Bilesen[] }>(""),
      gorunumAl(),
    ]);
    if (!K) return;
    for (const b of veri.bilesenler) {
      const g = gorunumler[b.ad];
      if (!g) continue;
      b.gorunum = g.gorunum;
      for (const [ref, y] of Object.entries(b.yuzler)) y.gorunum = g.yuzler[ref] ?? y.gorunum;
    }
    const ikililer = await Promise.all(veri.bilesenler.map((b) => K!.api.getIkili(`ag/${encodeURIComponent(b.ad)}`)));
    if (!K || !grup) return;
    temizle();
    const geometriler = veri.bilesenler.map((b, i) => {
      const yuzler = Object.values(b.yuzler);
      return { b, yuzler, g: geometriKur(ikililer[i], yuzler.map((y) => y.indeksler)), T: matris(b.T) };
    });
    const kutu = new THREE.Box3();
    for (const { g, T } of geometriler) {
      g.computeBoundingBox();
      kutu.union(g.boundingBox!.clone().applyMatrix4(T));
    }
    for (const { b, yuzler, g, T } of geometriler) {
      analizRengi(g, kutu.min.z, kutu.max.z, T);
      const ag = new THREE.Mesh(g);
      ag.name = b.ad;
      ag.matrixAutoUpdate = false;
      ag.matrix.copy(T);
      agKaydet(ag, [malzemeOlustur(b.gorunum), ...yuzler.map((y) => malzemeOlustur(y.gorunum))]);
      aglar.set(b.ad, ag);
      grup.add(ag);
    }
    modSec(aktifMod(), dugmeler);
    cercevele(K.sahne, grup);
    K.sahne.ciz();
    hazir = true;
  },

  kapat(): void {
    for (const f of temizlik.splice(0)) f();
    temizle();
    ortamBirak();
    if (K) {
      K.sahne.katmanBirak(AD);
      K.sahne.ciz();
    }
    grup = null;
    hazir = false;
    K = null;
  },

  komutlar,
};

export default ekran;
