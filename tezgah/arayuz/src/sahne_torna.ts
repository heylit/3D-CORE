// SPEC 25 — torna sahnesi: yatay iş mili ekseni, dönel kesit (270° kesit / tam), ayna, yol, takım ve hayalet.
// Yalnızca gösterir: kesit, yol ve takım geometrisi sunucudan gelir.
// Sahne eşlemesi: three X = z (iş mili ekseni), three Y = r·cosθ, three Z = r·sinθ. Yol θ = 0 düzlemindedir
// (Y = x, Z = 0); kesit görünümünde θ ∈ [0°, 90°] çeyreği açıktır, kesit yüzü kameraya bakar.
// A3: kendi çizicisi yok; kabuğun sahnesinde "torna" katmanına çizer (kök grup Z yukarı sahneye döndürülür).

import * as THREE from "three";

import type { Sahne } from "./sahne";
import type { Nokta3 } from "./tipler";
import type { TornaIs, TornaNoktalar } from "./tipler_25";
import { type TornaSim, kesitAt, kesitIslem, tornaHareketKonum, tornaYayAci } from "./torna";

const RENK = {
  ham: new THREE.Color("#2f62ae"),
  celik: new THREE.Color("#b9c1c9"),
  hizli: new THREE.Color("#55606c"),
  ayna: new THREE.Color("#6d7884"),
  hedef: new THREE.Color("#ffd75e"),
};
const DILIM = 40; // çeyrek başına değil, toplam açısal parça sayısı (tam tur)
const ON = 0.06; // yolun kesit yüzünün önünde durması için Z kayması [mm]

/** Model (x, y, z) → sahne vektörü (θ = 0 düzlemi). */
const sahneNokta = (p: Nokta3, on = ON) => new THREE.Vector3(p[2], p[0], on);

function takimModeli(r: number, q: [number, number], saydam: boolean): THREE.Group {
  const g = new THREE.Group();
  const yogun = saydam ? 0.35 : 1;
  const plaka = new THREE.MeshBasicMaterial({
    color: saydam ? 0xffffff : 0xd8dee5,
    transparent: saydam,
    opacity: saydam ? 0.22 : 1,
    side: THREE.DoubleSide,
    depthWrite: !saydam,
  });
  // burun merkezi C = P − q (q = [q_z, q_x]); sahnede X = z, Y = x
  const cx = -q[0];
  const cy = -q[1];
  let dx = cx;
  let dy = cy;
  const L = Math.hypot(dx, dy);
  if (L < 1e-9) {
    dx = Math.SQRT1_2;
    dy = Math.SQRT1_2;
  } else {
    dx /= L;
    dy /= L;
  }
  // uç plakası: burun dairesinden plakanın ekseni (C − P yönü) boyunca uzanan eşkenar dörtgen
  const boy = Math.max(12, 10 * r);
  const en = boy * 0.42;
  const nx = -dy;
  const ny = dx;
  const s = new THREE.Shape();
  s.moveTo(cx - dx * r, cy - dy * r);
  s.lineTo(cx + dx * boy * 0.5 + nx * en, cy + dy * boy * 0.5 + ny * en);
  s.lineTo(cx + dx * boy, cy + dy * boy);
  s.lineTo(cx + dx * boy * 0.5 - nx * en, cy + dy * boy * 0.5 - ny * en);
  s.closePath();
  const m = new THREE.Mesh(new THREE.ShapeGeometry(s), plaka);
  m.position.z = 0.2;
  g.add(m);
  // burun dairesi
  const daire: THREE.Vector3[] = [];
  for (let i = 0; i <= 48; i++) {
    const a = (i / 48) * 2 * Math.PI;
    daire.push(new THREE.Vector3(cx + r * Math.cos(a), cy + r * Math.sin(a), 0.3));
  }
  g.add(
    new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(daire),
      new THREE.LineBasicMaterial({ color: 0xd6a54e, transparent: saydam, opacity: yogun }),
    ),
  );
  // hayali uç noktası: küçük artı
  const a = Math.max(0.8, r);
  g.add(
    new THREE.LineSegments(
      new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(-a, 0, 0.35),
        new THREE.Vector3(a, 0, 0.35),
        new THREE.Vector3(0, -a, 0.35),
        new THREE.Vector3(0, a, 0.35),
      ]),
      new THREE.LineBasicMaterial({ color: 0xe3604d, transparent: saydam, opacity: yogun }),
    ),
  );
  return g;
}

export class TornaSahne {
  /** Torna koordinatları (Y yukarı) → kabuk sahnesi (Z yukarı): X ekseni etrafında +90°. */
  private kok = new THREE.Group();
  private sabit = new THREE.Group(); // ayna, ham malzeme izi, hedef profil
  private yolG = new THREE.Group();
  private parcaAg?: THREE.Mesh;
  private yolTum?: THREE.LineSegments;
  private yolBiten?: THREE.LineSegments;
  private hareketSonu = new Int32Array(0); // hareket h bitince çizilen tepe sayısı
  private takim = new THREE.Group();
  private hayaletG = new THREE.Group();
  private takimAnahtar = "";
  private hayaletAnahtar = "";
  private hayaletP: Nokta3 | null = null;
  private is?: TornaIs;
  private nk: TornaNoktalar | null = null;
  private sim: TornaSim | null = null;
  private renkler: THREE.Color[] = [];
  private kSon = -2;
  private kesitDurum = true;
  private sonDis: Float32Array = new Float32Array(0);
  private sonIc: Float32Array = new Float32Array(0);

  /** `S`: kabuğun ortak sahnesi (kamera, kontrol, çizici); çizim yalnız `bagla` ile verilen katmana. */
  constructor(private S: Sahne) {
    this.kok.rotation.x = Math.PI / 2;
    this.kok.add(this.sabit, this.yolG, this.takim, this.hayaletG);
    this.hayaletG.visible = false;
  }

  /** Ekran açılınca: torna çizimi ekranın sahne katmanına bağlanır (kabuk kapanınca katmanı kaldırır). */
  bagla(katman: THREE.Group): void {
    katman.add(this.kok);
    this.kok.updateMatrixWorld(true);
    if (this.is) this.cercevele();
    this.ciz();
  }

  ciz(): void {
    this.S.ciz();
  }

  /** Yeni iş: yol, kesit, ayna yeniden kurulur. */
  isKur(is: TornaIs, nk: TornaNoktalar | null, sim: TornaSim | null, renkler: string[], kameraKoru: boolean): void {
    this.is = is;
    this.nk = nk;
    this.sim = sim;
    this.renkler = renkler.map((r) => new THREE.Color(r));
    this.sabitKur();
    this.yolKur();
    if (this.parcaAg) {
      this.kok.remove(this.parcaAg);
      this.parcaAg.geometry.dispose();
    }
    this.parcaAg = new THREE.Mesh(
      new THREE.BufferGeometry(),
      new THREE.MeshStandardMaterial({ vertexColors: true, metalness: 0.45, roughness: 0.42, side: THREE.DoubleSide }),
    );
    this.kok.add(this.parcaAg);
    this.sonDis = new Float32Array(0);
    this.kSon = -2;
    this.takimAnahtar = "";
    this.hayaletAnahtar = "";
    if (!kameraKoru) this.cercevele();
    this.ciz();
  }

  /** Kamera torna koordinatında kurulur, kökün dönüşümüyle kabuk sahnesine taşınır. */
  private cercevele(): void {
    const s = this.is!.kurulum.stok;
    const kamera = this.S.kamera;
    const boy = Math.max(s.zmax - s.zmin, s.D);
    const uzak = (boy * 2.6) / Math.min(Math.max(kamera.aspect, 0.6), 1.8);
    this.kok.updateMatrixWorld(true);
    const m = this.kok.localToWorld(new THREE.Vector3((s.zmin + s.zmax) / 2, s.D * 0.15, 0));
    const p = this.kok.localToWorld(new THREE.Vector3((s.zmin + s.zmax) / 2 + uzak * 0.13, s.D * 0.15 + uzak * 0.3, uzak));
    this.S.kontrol.target.copy(m);
    kamera.position.copy(p);
    this.S.kontrol.update();
  }

  private sabitKur(): void {
    const is = this.is!;
    this.sabit.clear();
    const s = is.kurulum.stok;
    // ham malzeme izi (θ = 0 düzleminde dikdörtgen)
    const R = s.D / 2;
    const r = s.d / 2;
    const iz = [
      [s.zmin, r],
      [s.zmax, r],
      [s.zmax, R],
      [s.zmin, R],
      [s.zmin, r],
    ].map(([z, x]) => new THREE.Vector3(z, x, ON / 2));
    this.sabit.add(
      new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(iz),
        new THREE.LineDashedMaterial({ color: 0x5d6875, dashSize: 2, gapSize: 1.5 }),
      ).computeLineDistances(),
    );
    // eksen çizgisi
    this.sabit.add(
      new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(s.zmin - 40, 0, 0),
          new THREE.Vector3(s.zmax + 20, 0, 0),
        ]),
        new THREE.LineDashedMaterial({ color: 0x8d99a6, dashSize: 6, gapSize: 2 }),
      ).computeLineDistances(),
    );
    // ayna / punta (sunucunun kurulumundan)
    for (const a of is.kurulum.aynalar ?? []) {
      const L = a.zmax - a.zmin;
      if (!(L > 0) || !(a.D > 0)) continue;
      const geo = new THREE.CylinderGeometry(a.D / 2, a.D / 2, L, 48, 1, false);
      geo.rotateZ(Math.PI / 2); // eksen Y → X
      const m = new THREE.Mesh(
        geo,
        new THREE.MeshStandardMaterial({ color: RENK.ayna, metalness: 0.6, roughness: 0.45, transparent: true, opacity: 0.55 }),
      );
      m.position.set((a.zmin + a.zmax) / 2, 0, 0);
      this.sabit.add(m);
    }
    // hedef profil (sunucunun hücre örneği)
    const sim = this.sim;
    if (sim) {
      const p: THREE.Vector3[] = [];
      for (let h = 0; h < sim.nz; h++) {
        const v = sim.hedef[h];
        if (Number.isFinite(v)) p.push(new THREE.Vector3(sim.z0 + (h + 0.5) * sim.dz, v, ON * 2));
      }
      if (p.length > 1) {
        this.sabit.add(
          new THREE.Line(
            new THREE.BufferGeometry().setFromPoints(p),
            new THREE.LineDashedMaterial({ color: RENK.hedef, dashSize: 1.2, gapSize: 1 }),
          ).computeLineDistances(),
        );
      }
    }
  }

  private yolKur(): void {
    const is = this.is!;
    this.yolG.clear();
    const kon: number[] = [];
    const ren: number[] = [];
    this.hareketSonu = new Int32Array(is.hareketler.length);
    const c = new THREE.Color();
    is.hareketler.forEach((h, i) => {
      if (h.F === null) c.copy(RENK.hizli);
      else c.copy(this.renkler[h.islem] ?? RENK.hizli);
      let n = 1;
      if ((h.g === 2 || h.g === 3) && h.c) {
        const { r, dth } = tornaYayAci(h);
        n = Math.max(2, Math.ceil(Math.max(Math.abs(dth) / (Math.PI / 60), (Math.abs(dth) * r) / 0.2)));
      }
      let p = sahneNokta(h.a);
      for (let j = 1; j <= n; j++) {
        const q = sahneNokta(n > 1 ? tornaHareketKonum(h, j / n) : h.b);
        kon.push(p.x, p.y, p.z, q.x, q.y, q.z);
        ren.push(c.r, c.g, c.b, c.r, c.g, c.b);
        p = q;
      }
      this.hareketSonu[i] = kon.length / 3;
    });
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(kon, 3));
    geo.setAttribute("color", new THREE.Float32BufferAttribute(ren, 3));
    this.yolTum = new THREE.LineSegments(
      geo,
      new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.45 }),
    );
    this.yolBiten = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ vertexColors: true }));
    this.yolG.add(this.yolTum, this.yolBiten);
  }

  /** Kesit görünümü (270°) açık mı. */
  kesit(acik?: boolean): boolean {
    if (acik !== undefined && acik !== this.kesitDurum) {
      this.kesitDurum = acik;
      this.sonDis = new Float32Array(0);
      this.kesitYaz(Math.max(this.kSon, 0));
      this.ciz();
    }
    return this.kesitDurum;
  }

  /** Nokta k'deki durum: biten yol ve dönel kesit. */
  ilerleme(k: number): void {
    if (k === this.kSon) return;
    this.kSon = k;
    const nk = this.nk;
    if (nk && this.yolBiten) {
      let hk = -1;
      for (let j = Math.min(k, nk.n - 1); j >= 0 && hk < 0; j--) hk = nk.hareket[j];
      this.yolBiten.geometry.setDrawRange(0, hk >= 0 ? this.hareketSonu[hk] : 0);
    }
    this.kesitYaz(k);
    this.ciz();
  }

  /** Dönel kesit ağı: her hücre için dış / iç yüzey şeridi, basamak yüzleri, kesit yüzleri. */
  private kesitYaz(k: number): void {
    const is = this.is;
    if (!is || !this.parcaAg) return;
    const sim = this.sim;
    const s = is.kurulum.stok;
    let dis: Float32Array;
    let ic: Float32Array;
    let op: Int16Array;
    let z0: number;
    let dz: number;
    if (sim) {
      ({ dis, ic } = kesitAt(sim, k));
      op = kesitIslem(sim, k);
      z0 = sim.z0;
      dz = sim.dz;
    } else {
      dis = new Float32Array([s.D / 2]);
      ic = new Float32Array([s.d / 2]);
      op = new Int16Array([-1]);
      z0 = s.zmin;
      dz = s.zmax - s.zmin;
    }
    if (this.esit(dis, ic)) return;
    this.sonDis = dis;
    this.sonIc = ic;
    const nz = dis.length;
    const kesit = this.kesitDurum;
    const a0 = kesit ? Math.PI / 2 : 0;
    const a1 = 2 * Math.PI;
    const na = kesit ? Math.round((DILIM * 3) / 4) : DILIM;
    const pos: number[] = [];
    const nor: number[] = [];
    const col: number[] = [];
    const c = new THREE.Color();
    const renk = (h: number, kesitYuzu: boolean) => {
      const o = op[h];
      if (o < 0) return c.copy(RENK.ham);
      const r = this.renkler[o] ?? RENK.celik;
      return kesitYuzu ? c.copy(r) : c.copy(RENK.celik).lerp(r, 0.25);
    };
    const ucgen = (P: number[][], N: number[][], C: THREE.Color) => {
      for (let i = 0; i < 3; i++) {
        pos.push(...P[i]);
        nor.push(...N[i]);
        col.push(C.r, C.g, C.b);
      }
    };
    const dortgen = (P: number[][], N: number[][], C: THREE.Color) => {
      ucgen([P[0], P[1], P[2]], [N[0], N[1], N[2]], C);
      ucgen([P[0], P[2], P[3]], [N[0], N[2], N[3]], C);
    };
    const halka = (z: number, ra: number, rb: number, nxs: number, C: THREE.Color) => {
      // z'de ra..rb yarıçaplı halka parçası, normal ±X
      for (let j = 0; j < na; j++) {
        const t0 = a0 + ((a1 - a0) * j) / na;
        const t1 = a0 + ((a1 - a0) * (j + 1)) / na;
        const n = [nxs, 0, 0];
        dortgen(
          [
            [z, ra * Math.cos(t0), ra * Math.sin(t0)],
            [z, rb * Math.cos(t0), rb * Math.sin(t0)],
            [z, rb * Math.cos(t1), rb * Math.sin(t1)],
            [z, ra * Math.cos(t1), ra * Math.sin(t1)],
          ],
          [n, n, n, n],
          C,
        );
      }
    };
    const silindir = (za: number, zb: number, r: number, disa: boolean, C: THREE.Color) => {
      if (!(r > 0)) return;
      const sg = disa ? 1 : -1;
      for (let j = 0; j < na; j++) {
        const t0 = a0 + ((a1 - a0) * j) / na;
        const t1 = a0 + ((a1 - a0) * (j + 1)) / na;
        const n0 = [0, sg * Math.cos(t0), sg * Math.sin(t0)];
        const n1 = [0, sg * Math.cos(t1), sg * Math.sin(t1)];
        dortgen(
          [
            [za, r * Math.cos(t0), r * Math.sin(t0)],
            [zb, r * Math.cos(t0), r * Math.sin(t0)],
            [zb, r * Math.cos(t1), r * Math.sin(t1)],
            [za, r * Math.cos(t1), r * Math.sin(t1)],
          ],
          [n0, n0, n1, n1],
          C,
        );
      }
    };
    const dolu = (h: number) => h >= 0 && h < nz && dis[h] > ic[h];
    for (let h = 0; h < nz; h++) {
      if (!dolu(h)) continue;
      const za = z0 + h * dz;
      const zb = za + dz;
      const R = dis[h];
      const r = ic[h];
      silindir(za, zb, R, true, renk(h, false));
      silindir(za, zb, r, false, renk(h, false));
      // basamak yüzleri: komşu hücreyle dış ve iç yarıçap farkı
      for (const [kom, z, yon] of [
        [h - 1, za, -1],
        [h + 1, zb, 1],
      ] as [number, number, number][]) {
        if (!dolu(kom)) halka(z, r, R, yon, renk(h, false));
        else {
          if (dis[kom] < R) halka(z, dis[kom], R, yon, renk(h, false));
          if (ic[kom] > r) halka(z, r, ic[kom], yon, renk(h, false));
        }
      }
      if (kesit) {
        const C = renk(h, true);
        // θ = 0 yüzü (Z = 0, Y > 0), dışa normal +Z; θ = 90° yüzü (Y = 0, Z > 0), dışa normal +Y
        dortgen(
          [
            [za, r, 0],
            [zb, r, 0],
            [zb, R, 0],
            [za, R, 0],
          ],
          [
            [0, 0, 1],
            [0, 0, 1],
            [0, 0, 1],
            [0, 0, 1],
          ],
          C,
        );
        dortgen(
          [
            [za, 0, r],
            [zb, 0, r],
            [zb, 0, R],
            [za, 0, R],
          ],
          [
            [0, 1, 0],
            [0, 1, 0],
            [0, 1, 0],
            [0, 1, 0],
          ],
          C,
        );
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    geo.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3));
    geo.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
    this.parcaAg.geometry.dispose();
    this.parcaAg.geometry = geo;
  }

  private esit(dis: Float32Array, ic: Float32Array): boolean {
    if (dis.length !== this.sonDis.length) return false;
    for (let i = 0; i < dis.length; i++) if (dis[i] !== this.sonDis[i] || ic[i] !== this.sonIc[i]) return false;
    return true;
  }

  private modelAyarla(g: THREE.Group, onceki: string, islem: number, saydam: boolean): string {
    const t = this.is?.islemler[islem]?.takim;
    if (!t) return onceki;
    const a = `${t.T}:${t.r}:${t.q?.join(",")}`;
    if (a !== onceki) {
      g.clear();
      g.add(takimModeli(t.r, t.q ?? [0, 0], saydam));
    }
    return a;
  }

  takimKonum(p: Nokta3, islem: number): void {
    this.takimAnahtar = this.modelAyarla(this.takim, this.takimAnahtar, islem, false);
    this.takim.position.copy(sahneNokta(p, ON * 3));
    this.ciz();
  }

  hayalet(p: Nokta3 | null, islem: number): void {
    this.hayaletP = p ? [p[0], p[1], p[2]] : null;
    this.hayaletG.visible = p !== null;
    if (p) {
      this.hayaletAnahtar = this.modelAyarla(this.hayaletG, this.hayaletAnahtar, islem, true);
      this.hayaletG.position.copy(sahneNokta(p, ON * 4));
    }
    this.ciz();
  }

  /** Hayalet takımın hayali uç noktası, model koordinatında (x, y, z); yoksa null. */
  hayaletKonum(): Nokta3 | null {
    return this.hayaletG.visible && this.hayaletP ? [...this.hayaletP] : null;
  }

  /** Ekran noktasının θ = 0 düzlemindeki (z, r) karşılığı (kesit büyüteci için); düzlemi kesmiyorsa null. */
  duzlemNokta(istemciX: number, istemciY: number): { z: number; r: number } | null {
    const kutu = this.S.renderer.domElement.getBoundingClientRect();
    if (!kutu.width || !kutu.height) return null;
    const ndc = new THREE.Vector2(
      ((istemciX - kutu.left) / kutu.width) * 2 - 1,
      -((istemciY - kutu.top) / kutu.height) * 2 + 1,
    );
    const ray = new THREE.Raycaster();
    ray.setFromCamera(ndc, this.S.kamera);
    this.kok.updateMatrixWorld(true);
    const duzlem = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0).applyMatrix4(this.kok.matrixWorld);
    const p = new THREE.Vector3();
    if (!ray.ray.intersectPlane(duzlem, p)) return null;
    this.kok.worldToLocal(p);
    return { z: p.x, r: Math.abs(p.y) };
  }
}
