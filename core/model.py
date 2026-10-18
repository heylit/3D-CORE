"""
3D-CORE veri modeli.

Tüm katmanlar (eleman, birleştirme, çözücü, post-process, görselleştirme)
SADECE bu dosyadaki sınıflar üzerinden konuşur.

Birim sistemi (zorunlu, her yerde aynı):
    uzunluk  : mm
    kuvvet   : N
    gerilme  : MPa (= N/mm²)
    E modülü : MPa
    alan     : mm²
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np


class ModelError(ValueError):
    """Modelde tutarsızlık veya çözülemez durum (eksik mesnet, bilinmeyen düğüm...)."""


# Serbestlik derecesi (DOF) isimleri -> düğüm içi indeks
DOF_NAMES = {"ux": 0, "uy": 1, "uz": 2}

# Model boyutu -> düğüm başına DOF sayısı
DOFS_PER_NODE = {1: 1, 2: 2, 3: 3}


@dataclass
class Material:
    name: str
    E: float  # MPa
    nu: float = 0.3  # Poisson oranı
    rho: float = 0.0  # t/mm³ (ileride dinamik analiz için)

    def __post_init__(self) -> None:
        if self.E <= 0:
            raise ModelError(f"Malzeme '{self.name}': E pozitif olmalı (E={self.E})")


@dataclass
class Section:
    name: str
    A: float  # mm²

    def __post_init__(self) -> None:
        if self.A <= 0:
            raise ModelError(f"Kesit '{self.name}': A pozitif olmalı (A={self.A})")


@dataclass
class Node:
    id: int
    x: float
    y: float = 0.0
    z: float = 0.0

    @property
    def xyz(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z], dtype=float)


@dataclass
class Element:
    id: int
    type: str  # "bar1d", ileride "truss2d", "tri3", "tet4"...
    nodes: list[int]  # düğüm id'leri
    material: str  # Material.name
    section: str | None = None  # Section.name (çubuk/kafes elemanları için)


@dataclass
class BC:
    """Sınır koşulu: bir düğümün bir DOF'una değer atar (0 = ankastre)."""

    node: int
    dof: str  # "ux", "uy", "uz"
    value: float = 0.0  # mm


@dataclass
class Load:
    """Düğüm kuvveti."""

    node: int
    dof: str
    value: float  # N


@dataclass
class Model:
    dim: int = 1
    nodes: list[Node] = field(default_factory=list)
    elements: list[Element] = field(default_factory=list)
    materials: list[Material] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    bcs: list[BC] = field(default_factory=list)
    loads: list[Load] = field(default_factory=list)
    name: str = "isimsiz"

    # ---------- sorgular ----------

    @property
    def dofs_per_node(self) -> int:
        return DOFS_PER_NODE[self.dim]

    @property
    def n_dof(self) -> int:
        return len(self.nodes) * self.dofs_per_node

    def node(self, node_id: int) -> Node:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise ModelError(f"Bilinmeyen düğüm: {node_id}")

    def material(self, name: str) -> Material:
        for m in self.materials:
            if m.name == name:
                return m
        raise ModelError(f"Bilinmeyen malzeme: {name}")

    def section(self, name: str | None) -> Section:
        for s in self.sections:
            if s.name == name:
                return s
        raise ModelError(f"Bilinmeyen kesit: {name}")

    def node_index(self, node_id: int) -> int:
        """Düğümün global sıra numarası (nodes listesindeki konumu)."""
        for i, n in enumerate(self.nodes):
            if n.id == node_id:
                return i
        raise ModelError(f"Bilinmeyen düğüm: {node_id}")

    def dof_index(self, node_id: int, dof: str) -> int:
        """Global DOF numarası = düğüm_sırası * dofs_per_node + dof_içi_indeks."""
        if dof not in DOF_NAMES:
            raise ModelError(f"Bilinmeyen DOF adı: {dof}")
        local = DOF_NAMES[dof]
        if local >= self.dofs_per_node:
            raise ModelError(f"{self.dim}B modelde '{dof}' DOF'u yok")
        return self.node_index(node_id) * self.dofs_per_node + local

    # ---------- doğrulama ----------

    def validate(self) -> None:
        """Tutarsızlık varsa ModelError fırlatır. Çözücü çağırmadan önce çalıştırılır."""
        if self.dim not in DOFS_PER_NODE:
            raise ModelError(f"Geçersiz boyut: {self.dim}")

        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ModelError("Tekrarlanan düğüm id'si var")

        eids = [e.id for e in self.elements]
        if len(eids) != len(set(eids)):
            raise ModelError("Tekrarlanan eleman id'si var")

        for e in self.elements:
            for nid in e.nodes:
                self.node(nid)
            self.material(e.material)
            if e.section is not None:
                self.section(e.section)

        for bc in self.bcs:
            self.dof_index(bc.node, bc.dof)
        for ld in self.loads:
            self.dof_index(ld.node, ld.dof)

    # ---------- JSON girdi/çıktı ----------

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Model:
        m = cls(
            dim=d.get("dim", 1),
            name=d.get("name", "isimsiz"),
            nodes=[Node(**n) for n in d.get("nodes", [])],
            elements=[Element(**e) for e in d.get("elements", [])],
            materials=[Material(**m) for m in d.get("materials", [])],
            sections=[Section(**s) for s in d.get("sections", [])],
            bcs=[BC(**b) for b in d.get("bcs", [])],
            loads=[Load(**ld) for ld in d.get("loads", [])],
        )
        m.validate()
        return m

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def from_json(cls, path: str | Path) -> Model:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class Result:
    """Çözüm sonucu. Tüm diziler global DOF sırasındadır."""

    u: np.ndarray  # yer değiştirmeler [mm], boyut n_dof
    reactions: np.ndarray  # mesnet tepkileri [N], boyut n_dof (serbest DOF'larda 0)
    element_forces: dict[int, float] = field(default_factory=dict)  # eleman id -> eksenel kuvvet [N]
    element_stresses: dict[int, float] = field(default_factory=dict)  # eleman id -> eksenel gerilme [MPa]

    def displacement(self, model: Model, node_id: int, dof: str = "ux") -> float:
        return float(self.u[model.dof_index(node_id, dof)])

    def reaction(self, model: Model, node_id: int, dof: str = "ux") -> float:
        return float(self.reactions[model.dof_index(node_id, dof)])
