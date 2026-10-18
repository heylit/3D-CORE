// SPEC 25 — montaj sahnesi: parça ağları (kendi koordinatında, T ile yerleştirilir), girişim hacimleri (kırmızı),
// seçili parçada serbestlik glifleri, kütle merkezi. Yalnızca gösterir: dönüşümler ve ağlar sunucudan.

import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import type { Mat4, Serbestlik } from "./sira";
import type { Ag, Nokta3 } from "./tipler";

const PARCA_RENKLERI = ["#93a6ba", "#d6a54e", "#5cb8dc", "#b98ae0", "#55c08f", "#e3795d"];

function agGeometri(ag: Ag): THREE.BufferGeometry {
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(ag.V, 3));
  geo.setIndex(new THREE.BufferAttribute(ag.F, 1));
  geo.computeVertexNormals();
  return geo;
}

export const matris = (T: Mat4) =>
  new THREE.Matrix4().set(...(T as [number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number]));

export class MontajSahne {
  readonly renderer: THREE.WebGLRenderer;
  readonly kamera: THREE.PerspectiveCamera;
  readonly kontrol: OrbitControls;
  private sahne = new THREE.Scene();
  private parcalar = new Map<string, THREE.Mesh>(); // yol → ağ
  private girisimG = new THREE.Group();
  private glifG = new THREE.Group();
  private kmG = new THREE.Group();
  private cizimIstegi = true;
  private cerceveli = false;

  constructor(
    private kap: HTMLElement,
    secildi: (yol: string | null) => void,
  ) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    kap.appendChild(this.renderer.domElement);
    this.kamera = new THREE.PerspectiveCamera(32, 1, 1, 10000);
    this.kamera.up.set(0, 0, 1);
    this.kontrol = new OrbitControls(this.kamera, this.renderer.domElement);
    this.kontrol.enableDamping = true;
    this.kontrol.addEventListener("change", () => this.ciz());
    this.sahne.add(new THREE.HemisphereLight(0xe2ebf3, 0x2a2f36, 1.4));
    const gunes = new THREE.DirectionalLight(0xffffff, 1.5);
    gunes.position.set(-120, -160, 260);
    const kenar = new THREE.DirectionalLight(0x9fc4ff, 0.6);
    kenar.position.set(200, 180, -80);
    this.sahne.add(gunes, kenar, this.girisimG, this.glifG, this.kmG);
    new ResizeObserver(() => this.boyutla()).observe(kap);
    this.boyutla();
    // tıklama ile parça seçimi (sürüklemeden ayırmak için küçük hareket eşiği)
    let bas: [number, number] | null = null;
    const tv = this.renderer.domElement;
    tv.addEventListener("pointerdown", (e) => (bas = [e.clientX, e.clientY]));
    tv.addEventListener("pointerup", (e) => {
      if (!bas || Math.hypot(e.clientX - bas[0], e.clientY - bas[1]) > 4) return;
      secildi(this.isinla(e.clientX, e.clientY));
    });
    const dongu = () => {
      this.kontrol.update();
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

  private isinla(x: number, y: number): string | null {
    const r = this.renderer.domElement.getBoundingClientRect();
    const ray = new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1), this.kamera);
    const vur = ray.intersectObjects([...this.parcalar.values()], false)[0];
    if (!vur) return null;
    for (const [yol, m] of this.parcalar) if (m === vur.object) return yol;
    return null;
  }

  /** Bileşenler: yol → (parça kimliği, ağ). Ağı gelmeyen bileşen çizilmez. */
  kur(bilesenler: { yol: string; parca: string }[], aglar: Map<string, Ag>, kameraKoru: boolean): void {
    for (const m of this.parcalar.values()) {
      this.sahne.remove(m);
      m.geometry.dispose();
    }
    this.parcalar.clear();
    const geolar = new Map<string, THREE.BufferGeometry>();
    const kimlikler = [...new Set(bilesenler.map((b) => b.parca))];
    bilesenler.forEach((b) => {
      const ag = aglar.get(b.parca);
      if (!ag) return;
      let geo = geolar.get(b.parca);
      if (!geo) {
        geo = agGeometri(ag);
        geolar.set(b.parca, geo);
      }
      const renk = PARCA_RENKLERI[kimlikler.indexOf(b.parca) % PARCA_RENKLERI.length];
      const m = new THREE.Mesh(
        geo.clone(),
        new THREE.MeshStandardMaterial({ color: renk, metalness: 0.45, roughness: 0.45, side: THREE.DoubleSide }),
      );
      m.matrixAutoUpdate = false;
      this.parcalar.set(b.yol, m);
      this.sahne.add(m);
    });
    if (!kameraKoru || !this.cerceveli) this.cerceveleGerekli = true;
    this.ciz();
  }

  private cerceveleGerekli = false;

  /** Bileşen pozları (satır öncelikli 4x4). İlk çağrıda kamera bu pozlara çerçevelenir. */
  pozlar(T: Map<string, Mat4>): void {
    for (const [yol, M] of T) {
      const m = this.parcalar.get(yol);
      if (!m) continue;
      m.matrix.copy(matris(M));
      m.matrixWorldNeedsUpdate = true;
    }
    if (this.cerceveleGerekli) {
      this.cerceveleGerekli = false;
      this.cerceveli = true;
      this.cercevele();
    }
    this.ciz();
  }

  private cercevele(): void {
    const kutu = new THREE.Box3();
    for (const m of this.parcalar.values()) {
      m.updateMatrixWorld(true);
      m.geometry.computeBoundingBox();
      kutu.union(m.geometry.boundingBox!.clone().applyMatrix4(m.matrixWorld));
    }
    if (kutu.isEmpty()) return;
    const mrk = kutu.getCenter(new THREE.Vector3());
    const boy = kutu.getSize(new THREE.Vector3()).length();
    this.kontrol.target.copy(mrk);
    const r = boy * 1.9;
    this.kamera.position.set(mrk.x - r * 0.45, mrk.y - r * 0.75, mrk.z + r * 0.5);
    this.kontrol.update();
  }

  /** Girişim ağları (dünya koordinatı), kırmızı yarı saydam. */
  girisimler(aglar: Ag[]): void {
    for (const c of this.girisimG.children) (c as THREE.Mesh).geometry.dispose();
    this.girisimG.clear();
    for (const ag of aglar) {
      this.girisimG.add(
        new THREE.Mesh(
          agGeometri(ag),
          new THREE.MeshBasicMaterial({ color: 0xe3604d, transparent: true, opacity: 0.55, depthTest: false }),
        ),
      );
    }
    this.ciz();
  }

  girisimGorunur(acik: boolean): void {
    if (this.girisimG.visible !== acik) {
      this.girisimG.visible = acik;
      this.ciz();
    }
  }

  /** Seçili parçanın vurgusu ve serbestlik glifleri (oklar: öteleme, halka + eksen: vida). */
  secili(yol: string | null, s: Serbestlik | null, merkez: Nokta3 | null, olcek: number): void {
    for (const [y, m] of this.parcalar) {
      const mat = m.material as THREE.MeshStandardMaterial;
      mat.emissive.set(y === yol ? 0x3a2a08 : 0x000000);
      mat.transparent = yol !== null && y !== yol;
      mat.opacity = yol !== null && y !== yol ? 0.35 : 1;
    }
    this.glifG.clear();
    if (yol && s && merkez) {
      const p = new THREE.Vector3(...merkez);
      for (const u of s.oteleme) {
        const d = new THREE.Vector3(...u).normalize();
        this.glifG.add(new THREE.ArrowHelper(d, p, olcek, 0x55c08f, olcek * 0.25, olcek * 0.12));
        this.glifG.add(new THREE.ArrowHelper(d.clone().negate(), p, olcek, 0x55c08f, olcek * 0.25, olcek * 0.12));
      }
      for (const v of s.vida) {
        const d = new THREE.Vector3(...v.yon).normalize();
        const n = new THREE.Vector3(...v.nokta);
        // eksen üstünde parçanın merkezine en yakın nokta
        const o = n.clone().add(d.clone().multiplyScalar(p.clone().sub(n).dot(d)));
        this.glifG.add(
          new THREE.Line(
            new THREE.BufferGeometry().setFromPoints([
              o.clone().addScaledVector(d, -olcek * 1.6),
              o.clone().addScaledVector(d, olcek * 1.6),
            ]),
            new THREE.LineBasicMaterial({ color: 0xd6a54e }),
          ),
        );
        const halka = new THREE.Mesh(
          new THREE.TorusGeometry(olcek * 0.55, olcek * 0.03, 8, 48),
          new THREE.MeshBasicMaterial({ color: 0xd6a54e }),
        );
        halka.position.copy(o);
        halka.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), d);
        this.glifG.add(halka);
      }
    }
    this.ciz();
  }

  /** Kütle merkezi işareti. */
  kutleMerkezi(p: Nokta3 | null, olcek: number): void {
    this.kmG.clear();
    if (p) {
      const k = new THREE.Mesh(
        new THREE.SphereGeometry(olcek * 0.08, 16, 8),
        new THREE.MeshBasicMaterial({ color: 0xffd75e, depthTest: false }),
      );
      k.position.set(...p);
      this.kmG.add(k);
    }
    this.ciz();
  }
}
