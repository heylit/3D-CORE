// SPEC 24 — three.js sahnesi: yörünge kamera, stok / z-haritası yüzeyi, takım yolu, takım ve hayalet.
// Yalnızca gösterir: konumlar, yüzey ve yük sunucudan gelir.

import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import { yuzeyAt } from "./ikili";
import type { Is, Noktalar, Nokta3, SimVeri } from "./tipler";
import { hareketKonum, parcaSayisi } from "./yol";

export type Katman = "islem" | "yuk";

const ISI: [number, THREE.Color][] = [
  [0, new THREE.Color("#1f2a6b")],
  [0.35, new THREE.Color("#7b2f8f")],
  [0.65, new THREE.Color("#e2573b")],
  [1, new THREE.Color("#ffd75e")],
];
const RENK = {
  dykem: new THREE.Color("#2f62ae"),
  alu: new THREE.Color("#c3cad1"),
  hizli: new THREE.Color("#55606c"),
};

export function isi(v: number, out: THREE.Color): THREE.Color {
  for (let i = 1; i < ISI.length; i++) {
    if (v <= ISI[i][0]) {
      const [a, ca] = ISI[i - 1];
      const [b, cb] = ISI[i];
      return out.copy(ca).lerp(cb, (v - a) / (b - a));
    }
  }
  return out.copy(ISI[ISI.length - 1][1]);
}

function takimModeli(R: number, tur: string, saydam: boolean): THREE.Group {
  const g = new THREE.Group();
  const kesici = new THREE.MeshStandardMaterial({
    color: saydam ? 0xffffff : 0xd8dee5,
    metalness: 0.8,
    roughness: 0.28,
    transparent: saydam,
    opacity: saydam ? 0.28 : 1,
    depthWrite: !saydam,
  });
  const govde = new THREE.MeshStandardMaterial({
    color: saydam ? 0xffffff : 0x8b95a1,
    metalness: 0.6,
    roughness: 0.4,
    transparent: saydam,
    opacity: saydam ? 0.16 : 1,
    depthWrite: !saydam,
  });
  const Lf = Math.max(4 * R, 14);
  const ekle = (geo: THREE.BufferGeometry, mat: THREE.Material, z: number) => {
    const m = new THREE.Mesh(geo, mat);
    m.rotation.x = Math.PI / 2; // silindir ekseni Y → Z
    m.position.z = z;
    g.add(m);
  };
  if (tur === "matkap") {
    const uc = R / Math.tan((59 * Math.PI) / 180); // 118° uç
    const koni = new THREE.ConeGeometry(R, uc, 32);
    koni.rotateX(Math.PI); // tepe aşağı
    ekle(koni, kesici, uc / 2);
    ekle(new THREE.CylinderGeometry(R, R, Lf, 32), kesici, uc + Lf / 2);
  } else if (tur === "kuresel") {
    const s = new THREE.Mesh(new THREE.SphereGeometry(R, 32, 16), kesici);
    s.position.z = R;
    g.add(s);
    ekle(new THREE.CylinderGeometry(R, R, Lf - R, 32), kesici, R + (Lf - R) / 2);
  } else {
    ekle(new THREE.CylinderGeometry(R, R, Lf, 32), kesici, Lf / 2);
  }
  const Rs = Math.max(R, 3);
  ekle(new THREE.CylinderGeometry(Rs, Rs, 30, 32), govde, Lf + 15);
  ekle(new THREE.CylinderGeometry(Rs + 10, Rs + 2, 22, 40), govde, Lf + 30 + 11);
  return g;
}

export class Sahne {
  readonly renderer: THREE.WebGLRenderer;
  readonly kamera: THREE.PerspectiveCamera;
  readonly kontrol: OrbitControls;
  private sahne = new THREE.Scene();
  private grup = new THREE.Group();
  private yolTum?: THREE.LineSegments;
  private yolBiten?: THREE.LineSegments;
  private iz?: THREE.LineSegments; // parametre değişikliğinden önceki yol, sönerek kaybolur
  private izBas = 0;
  private parcaSonu = new Int32Array(0); // nokta k'ye kadar çizilen tepe sayısı
  private yuzeyAg?: THREE.Mesh;
  private stokKutu?: THREE.Mesh;
  private takim = new THREE.Group();
  private hayaletG = new THREE.Group();
  private takimAnahtar = "";
  private hayaletAnahtar = "";
  private is?: Is;
  private nk?: Noktalar;
  private sim: SimVeri | null = null;
  private renkler: THREE.Color[] = [];
  private kSon = -2;
  private katmanAd: Katman = "islem";
  private zH = new Float32Array(0);
  private zI = new Int16Array(0);
  private zK = new Int32Array(0);
  private cizimIstegi = true;

  constructor(private kap: HTMLElement) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    kap.appendChild(this.renderer.domElement);
    this.kamera = new THREE.PerspectiveCamera(32, 1, 1, 5000);
    this.kamera.up.set(0, 0, 1);
    this.kontrol = new OrbitControls(this.kamera, this.renderer.domElement);
    this.kontrol.enableDamping = true;
    this.kontrol.addEventListener("change", () => this.ciz());
    this.sahne.add(new THREE.HemisphereLight(0xe2ebf3, 0x2a2f36, 1.4));
    const gunes = new THREE.DirectionalLight(0xffffff, 1.6);
    gunes.position.set(-120, -160, 260);
    const kenar = new THREE.DirectionalLight(0x9fc4ff, 0.6);
    kenar.position.set(200, 180, 80);
    this.sahne.add(gunes, kenar, this.grup, this.takim, this.hayaletG);
    this.hayaletG.visible = false;
    new ResizeObserver(() => this.boyutla()).observe(kap);
    this.boyutla();
    const dongu = () => {
      this.kontrol.update();
      this.izSondur();
      if (this.cizimIstegi) {
        this.cizimIstegi = false;
        this.renderer.render(this.sahne, this.kamera);
      }
      requestAnimationFrame(dongu);
    };
    requestAnimationFrame(dongu);
  }

  ciz(): void {
    this.cizimIstegi = true;
  }

  private boyutla(): void {
    const w = this.kap.clientWidth;
    const h = this.kap.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h);
    this.kamera.aspect = w / h;
    this.kamera.updateProjectionMatrix();
    this.ciz();
  }

  /** Yeni iş: yol, yüzey ve takım yeniden kurulur. `kameraKoru` parametre değişikliğinde görünümü korur. */
  isKur(is: Is, nk: Noktalar, sim: SimVeri | null, renkler: string[], kameraKoru: boolean): void {
    const eskiYol = this.yolTum;
    this.is = is;
    this.nk = nk;
    this.sim = sim;
    this.renkler = renkler.map((r) => new THREE.Color(r));
    this.grup.clear();
    if (this.iz) this.iz.geometry.dispose();
    this.iz = undefined;
    if (kameraKoru && eskiYol) {
      // eski yol: değişikliği göstermek için kısa süre görünür kalır
      eskiYol.material = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.5 });
      this.iz = eskiYol;
      this.izBas = performance.now();
      this.grup.add(eskiYol);
    }
    this.yolKur();
    this.yuzeyKur();
    if (!kameraKoru) this.cercevele();
    this.kSon = -2;
    this.ciz();
  }

  private izSondur(): void {
    if (!this.iz) return;
    const u = (performance.now() - this.izBas) / 2500;
    const m = this.iz.material as THREE.LineBasicMaterial;
    if (u >= 1) {
      this.grup.remove(this.iz);
      this.iz.geometry.dispose();
      this.iz = undefined;
    } else m.opacity = 0.5 * (1 - u);
    this.ciz();
  }

  private cercevele(): void {
    const s = this.is!.kurulum.stok;
    const m = new THREE.Vector3((s.x0 + s.x1) / 2, (s.y0 + s.y1) / 2, (s.z0 + s.z1) / 2);
    const boy = Math.hypot(s.x1 - s.x0, s.y1 - s.y0, s.z1 - s.z0);
    this.kontrol.target.copy(m);
    const r = boy * 2.3;
    this.kamera.position.set(m.x - r * 0.42, m.y - r * 0.72, m.z + r * 0.55);
    this.kontrol.update();
  }

  private yolKur(): void {
    const is = this.is!;
    const nk = this.nk!;
    const P = nk.konum;
    const kon: number[] = [];
    const ren: number[] = [];
    this.parcaSonu = new Int32Array(nk.n);
    const c = new THREE.Color();
    const nokta = (k: number): Nokta3 => [P[3 * k], P[3 * k + 1], P[3 * k + 2]];
    for (let k = 1; k < nk.n; k++) {
      const hk = nk.hareket[k];
      const h = hk >= 0 ? is.hareketler[hk] : null;
      if (nk.hizli[k]) c.copy(RENK.hizli);
      else if (this.katmanAd === "yuk") isi(nk.yuk[k], c);
      else c.copy(this.renkler[nk.islem[k]] ?? RENK.hizli);
      const n = h ? parcaSayisi(h) : 1;
      let p = nokta(k - 1);
      for (let i = 1; i <= n; i++) {
        const q = h && n > 1 ? hareketKonum(h, i / n) : nokta(k);
        kon.push(...p, ...q);
        ren.push(c.r, c.g, c.b, c.r, c.g, c.b);
        p = q;
      }
      this.parcaSonu[k] = kon.length / 3;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(kon, 3));
    geo.setAttribute("color", new THREE.Float32BufferAttribute(ren, 3));
    this.yolTum = new THREE.LineSegments(
      geo,
      new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.22 }),
    );
    this.yolBiten = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ vertexColors: true }));
    this.grup.add(this.yolTum, this.yolBiten);
  }

  private yuzeyKur(): void {
    const s = this.is!.kurulum.stok;
    const sim = this.sim;
    if (!sim) {
      const kutu = new THREE.BoxGeometry(s.x1 - s.x0, s.y1 - s.y0, s.z1 - s.z0);
      this.stokKutu = new THREE.Mesh(
        kutu,
        new THREE.MeshStandardMaterial({ color: RENK.dykem, metalness: 0.3, roughness: 0.55, transparent: true, opacity: 0.6 }),
      );
      this.stokKutu.position.set((s.x0 + s.x1) / 2, (s.y0 + s.y1) / 2, (s.z0 + s.z1) / 2);
      this.grup.add(this.stokKutu);
      this.yuzeyAg = undefined;
      return;
    }
    // hücre merkezlerinde tepeler + kenarda stok tabanına inen etek (VX = nx + 2)
    const VX = sim.nx + 2;
    const VY = sim.ny + 2;
    const pos = new Float32Array(VX * VY * 3);
    for (let j = 0; j < VY; j++) {
      for (let i = 0; i < VX; i++) {
        const v = j * VX + i;
        const ci = Math.min(Math.max(i - 1, 0), sim.nx - 1);
        const cj = Math.min(Math.max(j - 1, 0), sim.ny - 1);
        // etek tepeleri stok kenarına
        pos[3 * v] = i === 0 ? s.x0 : i === VX - 1 ? s.x1 : sim.x0 + (ci + 0.5) * sim.dx;
        pos[3 * v + 1] = j === 0 ? s.y0 : j === VY - 1 ? s.y1 : sim.y0 + (cj + 0.5) * sim.dy;
        pos[3 * v + 2] = sim.zAlt;
      }
    }
    const idx = new Uint32Array((VX - 1) * (VY - 1) * 6);
    let q = 0;
    for (let j = 0; j < VY - 1; j++) {
      for (let i = 0; i < VX - 1; i++) {
        const a = j * VX + i;
        idx.set([a, a + 1, a + VX + 1, a, a + VX + 1, a + VX], q);
        q += 6;
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setIndex(new THREE.BufferAttribute(idx, 1));
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("normal", new THREE.BufferAttribute(new Float32Array(VX * VY * 3), 3));
    geo.setAttribute("color", new THREE.BufferAttribute(new Float32Array(VX * VY * 3), 3));
    this.yuzeyAg = new THREE.Mesh(
      geo,
      new THREE.MeshStandardMaterial({ vertexColors: true, metalness: 0.35, roughness: 0.5, side: THREE.DoubleSide }),
    );
    this.grup.add(this.yuzeyAg);
    const N = sim.nx * sim.ny;
    this.zH = new Float32Array(N);
    this.zI = new Int16Array(N);
    this.zK = new Int32Array(N);
  }

  katman(ad: Katman): void {
    this.katmanAd = ad;
    if (!this.is) return;
    this.grup.remove(this.yolTum!, this.yolBiten!);
    this.yolTum!.geometry.dispose();
    this.yolKur();
    this.kSon = -2;
  }

  /** Nokta k'deki durum: biten yol, simülasyon yüzeyi. */
  ilerleme(k: number): void {
    if (!this.nk || k === this.kSon) return;
    this.kSon = k;
    this.yolBiten?.geometry.setDrawRange(0, k > 0 ? this.parcaSonu[k] : 0);
    if (this.sim && this.yuzeyAg) this.yuzeyYaz(k);
    this.ciz();
  }

  /** Sim yüzeyindeki k anı yüzeyi (test kancası için kopya). */
  yuzey(): Float32Array | null {
    return this.sim ? this.zH.slice() : null;
  }

  private yuzeyYaz(k: number): void {
    const sim = this.sim!;
    const nk = this.nk!;
    yuzeyAt(sim, k, this.zH, this.zI, this.zK);
    const geo = this.yuzeyAg!.geometry;
    const pos = geo.attributes.position.array as Float32Array;
    const nor = geo.attributes.normal.array as Float32Array;
    const col = geo.attributes.color.array as Float32Array;
    const { nx, ny } = sim;
    const VX = nx + 2;
    const H = this.zH;
    const c = new THREE.Color();
    for (let j = 0; j < ny + 2; j++) {
      for (let i = 0; i < VX; i++) {
        const v = j * VX + i;
        const ic = i > 0 && j > 0 && i < VX - 1 && j < ny + 1;
        const ci = Math.min(Math.max(i - 1, 0), nx - 1);
        const cj = Math.min(Math.max(j - 1, 0), ny - 1);
        const h = cj * nx + ci;
        const op = this.zI[h];
        if (op < 0) c.copy(RENK.dykem);
        else if (this.katmanAd === "yuk") isi(nk.yuk[this.zK[h]] ?? 0, c);
        else c.copy(RENK.alu).lerp(this.renkler[op] ?? RENK.alu, 0.28);
        if (ic) {
          pos[3 * v + 2] = H[h];
          const hl = H[cj * nx + Math.max(ci - 1, 0)];
          const hr = H[cj * nx + Math.min(ci + 1, nx - 1)];
          const hd = H[Math.max(cj - 1, 0) * nx + ci];
          const hu = H[Math.min(cj + 1, ny - 1) * nx + ci];
          const gx = -(hr - hl) / (2 * sim.dx);
          const gy = -(hu - hd) / (2 * sim.dy);
          const L = Math.hypot(gx, gy, 1);
          nor[3 * v] = gx / L;
          nor[3 * v + 1] = gy / L;
          nor[3 * v + 2] = 1 / L;
          col[3 * v] = c.r;
          col[3 * v + 1] = c.g;
          col[3 * v + 2] = c.b;
        } else {
          pos[3 * v + 2] = sim.zAlt;
          nor[3 * v] = i === 0 ? -1 : i === VX - 1 ? 1 : 0;
          nor[3 * v + 1] = j === 0 ? -1 : j === ny + 1 ? 1 : 0;
          nor[3 * v + 2] = 0;
          col[3 * v] = c.r * 0.62;
          col[3 * v + 1] = c.g * 0.62;
          col[3 * v + 2] = c.b * 0.66;
        }
      }
    }
    geo.attributes.position.needsUpdate = true;
    geo.attributes.normal.needsUpdate = true;
    geo.attributes.color.needsUpdate = true;
    geo.computeBoundingSphere();
  }

  private modelAyarla(g: THREE.Group, anahtar: string, onceki: string, islem: number, saydam: boolean): string {
    const t = this.is?.islemler[islem]?.takim;
    if (!t) return onceki;
    const a = `${t.T}:${t.R}:${t.tur}`;
    if (a !== onceki) {
      g.clear();
      g.add(takimModeli(t.R, t.tur, saydam));
    }
    void anahtar;
    return a;
  }

  takimKonum(p: Nokta3, islem: number): void {
    this.takimAnahtar = this.modelAyarla(this.takim, "takim", this.takimAnahtar, islem, false);
    this.takim.position.set(p[0], p[1], p[2]);
    this.ciz();
  }

  hayalet(p: Nokta3 | null, islem: number): void {
    this.hayaletG.visible = p !== null;
    if (p) {
      this.hayaletAnahtar = this.modelAyarla(this.hayaletG, "hayalet", this.hayaletAnahtar, islem, true);
      this.hayaletG.position.set(p[0], p[1], p[2]);
    }
    this.ciz();
  }

  /** Hayalet takımın konumu (test kancası). */
  hayaletKonum(): Nokta3 | null {
    if (!this.hayaletG.visible) return null;
    const p = this.hayaletG.position;
    return [p.x, p.y, p.z];
  }
}
