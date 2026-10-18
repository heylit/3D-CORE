// SPEC 65b — gerçekçi malzeme görünümü (PBR): Gorunum → MeshPhysicalMaterial, çevrimdışı ortam haritası, ton eşleme,
// görünüm modu. Ön ayarlar ve çözümleme sunucudadır (tezgah/gorunum.py, GET /api/gorunum); burada yalnız çizim.

import * as THREE from "three";

/** tezgah/gorunum.py Gorunum.to_dict() ile aynı alanlar. */
export interface Gorunum {
  renk: string; // "#rrggbb"
  metalness: number; // [0, 1]
  roughness: number; // [0, 1]
  clearcoat: number; // [0, 1]
  anisotropy: number; // [0, 1]
}

/** GET /api/gorunum?montaj=… gövdesi: bileşen adı → bileşen görünümü ve yüz başına (FaceRef) görünüm. */
export interface MontajGorunumu {
  [bilesen: string]: { gorunum: Gorunum; yuzler: Record<string, Gorunum> };
}

/** gercekci: PBR; teknik: bugünkü düz görünüm; analiz: vertex renk haritası, PBR kapalı. */
export type GorunumModu = "gercekci" | "teknik" | "analiz";

/** Test kancası: window.__tezgah.gorunum (kanca.ts deseni, yalnız okuma). */
export interface GorunumKanca {
  mod(): GorunumModu;
  /** Bileşenin ağındaki malzemeler, malzeme grubu sırasıyla. */
  malzemeler(bilesen: string): {
    tip: string; // material.type, ör. "MeshPhysicalMaterial"
    metalness: number;
    roughness: number;
    clearcoat: number;
    vertexColors: boolean;
  }[];
  ortamVar(): boolean; // scene.environment !== null
  tonEsleme(): number; // renderer.toneMapping
  programSayisi(): number; // renderer.info.programs.length
  /** Bileşenin canvas üzerindeki kutusu [x0, y0, x1, y1] (CSS pikseli, sol üst köşeye göre); görünmüyorsa null. */
  ekranKutusu(bilesen: string): [number, number, number, number] | null;
}

// ------------------------------------------------------------------ malzeme önbelleği

const onbellek = new Map<string, THREE.MeshPhysicalMaterial>();

function anahtar(g: Gorunum): string {
  return [g.renk.toLowerCase(), g.metalness, g.roughness, g.clearcoat, g.anisotropy].join("|");
}

/** Önbellekli: aynı Gorunum (değerce) → aynı nesne. */
export function malzemeOlustur(g: Gorunum): THREE.MeshPhysicalMaterial {
  const k = anahtar(g);
  let m = onbellek.get(k);
  if (!m) {
    m = new THREE.MeshPhysicalMaterial({
      color: new THREE.Color(g.renk),
      metalness: g.metalness,
      roughness: g.roughness,
      clearcoat: g.clearcoat,
      clearcoatRoughness: 0.15,
      anisotropy: g.anisotropy,
      polygonOffset: true,
      polygonOffsetFactor: 1,
      polygonOffsetUnits: 1,
    });
    onbellek.set(k, m);
  }
  return m;
}

// ------------------------------------------------------------------ ortam ve mod

interface Ortam {
  renderer: THREE.WebGLRenderer;
  sahne: THREE.Scene;
  harita: THREE.Texture;
  onceki: {
    toneMapping: THREE.ToneMapping;
    renkUzayi: THREE.ColorSpace;
    environment: THREE.Texture | null;
    background: THREE.Scene["background"];
  };
}

let ortam: Ortam | null = null;
let mod: GorunumModu = "gercekci";

/** Mod geçişinde malzemesi değişen ağlar: gerçekçi malzemeleri ve analiz renkleri hazır. */
interface Kayit {
  ag: THREE.Mesh;
  gercekci: THREE.Material[];
}
const kayitlar: Kayit[] = [];

/** Görünüm ekranı açıkken sahnenin düz zemin rengi (stil.css --zemin tonunda). */
const ZEMIN = 0x161b22;

// teknik ve analiz modlarının paylaşılan malzemeleri (her kayıtta yeniden kurulmaz: program sızıntısı yok)
const TEKNIK = new THREE.MeshStandardMaterial({ color: 0x8fa3b8, metalness: 0.55, roughness: 0.38 });
const ANALIZ = new THREE.MeshBasicMaterial({ vertexColors: true });

/**
 * Kodla kurulan stüdyo ortamı (Z-yukarı, dosya indirmez): koyu zemin, ufuktan tepeye açılan gök, üstte ve iki
 * yanda yumuşak ışık kutuları. Düz metal yüzler bu karşıtlığı yansıtır; RoomEnvironment'ın tekdüze duvarları
 * metali boz plastik gibi gösteriyordu.
 */
function studyoKur(): THREE.Scene {
  const s = new THREE.Scene();
  const R = 50;
  const kure = new THREE.SphereGeometry(R, 64, 32).rotateX(Math.PI / 2); // kutuplar ±Z
  const p = kure.getAttribute("position");
  const renk = new Float32Array(p.count * 3);
  for (let i = 0; i < p.count; i++) {
    const z = p.getZ(i) / R; // -1 zemin … +1 tepe
    // zemin: ufukta açık, aşağı doğru hızla kararır (yan yüzlerde yansıma geçişi); gök ufuktan tepeye açılır
    const v = z < 0 ? 0.06 + 0.6 * Math.max(0, 1 + 1.6 * z) : 0.66 + 0.34 * z;
    renk.set([v, v, v * 1.04], 3 * i);
  }
  kure.setAttribute("color", new THREE.BufferAttribute(renk, 3));
  s.add(new THREE.Mesh(kure, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.BackSide })));
  const kutu = (w: number, h: number, siddet: number, konum: [number, number, number]) => {
    const m = new THREE.Mesh(
      new THREE.PlaneGeometry(w, h),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(siddet, siddet, siddet), side: THREE.DoubleSide }),
    );
    m.position.set(...konum);
    m.lookAt(0, 0, 0);
    s.add(m);
  };
  kutu(30, 30, 4, [0, 0, 40]);
  kutu(10, 40, 3, [-35, -25, 10]);
  kutu(10, 40, 2, [35, 25, 15]);
  kutu(60, 6, 1.5, [15, -35, -14]); // ön alt yansıtma kartı: varsayılan bakışta yan yüzlerde parlak şerit
  return s;
}

/** Stüdyo ortamı + PMREMGenerator ile scene.environment; ACESFilmic ton eşleme, SRGB çıkış. Dosya indirmez. */
export function ortamKur(renderer: THREE.WebGLRenderer, sahne: THREE.Scene): void {
  if (ortam && ortam.renderer === renderer && ortam.sahne === sahne) {
    modUygula();
    return;
  }
  if (ortam) ortamBirak();
  const pmrem = new THREE.PMREMGenerator(renderer);
  const studyo = studyoKur();
  const harita = pmrem.fromScene(studyo, 0.02).texture;
  studyo.traverse((n) => {
    if (n instanceof THREE.Mesh) {
      n.geometry.dispose();
      (n.material as THREE.Material).dispose();
    }
  });
  pmrem.dispose();
  ortam = {
    renderer,
    sahne,
    harita,
    onceki: {
      toneMapping: renderer.toneMapping,
      renkUzayi: renderer.outputColorSpace as THREE.ColorSpace,
      environment: sahne.environment,
      background: sahne.background,
    },
  };
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  // düz, opak zemin: parçanın parlaklığı CSS gradyanından ayrılır (ortam haritası arka plana çizilmez)
  sahne.background = new THREE.Color(ZEMIN);
  modUygula();
}

/** Ortamı kaldırır, renderer ayarlarını ortamKur'dan önceki hâline döndürür (ekran kapanınca). */
export function ortamBirak(): void {
  if (!ortam) return;
  const { renderer, sahne, harita, onceki } = ortam;
  renderer.toneMapping = onceki.toneMapping;
  renderer.outputColorSpace = onceki.renkUzayi;
  sahne.environment = onceki.environment;
  sahne.background = onceki.background;
  harita.dispose();
  ortam = null;
  kayitlar.length = 0;
}

/** Ağı mod geçişine kaydeder; `gercekci` malzeme dizisi (malzeme grubu sırasıyla). Analiz için `color` özniteliği. */
export function agKaydet(ag: THREE.Mesh, gercekci: THREE.Material[]): void {
  kayitlar.push({ ag, gercekci });
  ag.material = malzemeSec(gercekci);
}

export function agBirak(ag: THREE.Mesh): void {
  const i = kayitlar.findIndex((k) => k.ag === ag);
  if (i >= 0) kayitlar.splice(i, 1);
}

function malzemeSec(gercekci: THREE.Material[]): THREE.Material | THREE.Material[] {
  if (mod === "gercekci") return gercekci;
  return mod === "teknik" ? TEKNIK : ANALIZ;
}

function modUygula(): void {
  if (ortam) {
    const pbr = mod === "gercekci";
    ortam.sahne.environment = pbr ? ortam.harita : ortam.onceki.environment;
    ortam.renderer.toneMapping = pbr ? THREE.ACESFilmicToneMapping : ortam.onceki.toneMapping;
  }
  for (const k of kayitlar) k.ag.material = malzemeSec(k.gercekci);
}

/** Görünüm modunu değiştirir; analiz modunda PBR kapalı, gercekci'ye dönüşte aynı malzeme nesneleri. */
export function gorunumModu(yeni: GorunumModu): void {
  mod = yeni;
  modUygula();
}

export function aktifMod(): GorunumModu {
  return mod;
}

export function ortamVar(): boolean {
  return ortam !== null && ortam.sahne.environment !== null;
}
