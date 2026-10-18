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
}

/** Önbellekli: aynı Gorunum (değerce) → aynı nesne. */
export function malzemeOlustur(_g: Gorunum): THREE.MeshPhysicalMaterial {
  throw new Error("SPEC 65b: malzemeOlustur uygulanmadı");
}

/** RoomEnvironment + PMREMGenerator ile scene.environment; ACESFilmic ton eşleme, SRGB çıkış. Dosya indirmez. */
export function ortamKur(_renderer: THREE.WebGLRenderer, _sahne: THREE.Scene): void {
  throw new Error("SPEC 65b: ortamKur uygulanmadı");
}

/** Görünüm modunu değiştirir; analiz modunda PBR kapalı, gercekci'ye dönüşte aynı malzeme nesneleri. */
export function gorunumModu(_mod: GorunumModu): void {
  throw new Error("SPEC 65b: gorunumModu uygulanmadı");
}
