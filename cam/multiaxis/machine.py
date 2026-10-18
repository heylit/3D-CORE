"""
SPEC 44 — Tezgâh gövde modeli: halkalar, ilkel gövdeler (kutu, kapsül), halka dönüşümleri.

Halkalar: "taban" (sabit), doğrusal eksenler "X", "Y", "Z", döner eksenler (kinematikteki adlarıyla,
ör. "A", "C"), "is_mili", "is_parcasi". Zincirler (çarpımlar-üstel, her eksen sıfır konumunda tanımlı):
- masa: taban → (masadaki doğrusallar, X, Y, Z sırasıyla) → t1 → t2 → is_parcasi
- kafa: taban → (kafadaki doğrusallar, X, Y, Z sırasıyla) → h1 → h2 → is_mili
Halka dönüşümü x ↦ R·x + t (gövde sıfır konumundaki makine koordinatından şimdiki konumuna):
kafa halkası Trans(Σ kafa doğrusalları) ∘ Rot(h1) ∘ …, masa halkası Trans(−Σ masa doğrusalları) ∘ Rot(t1) ∘ …
(masa doğrusalı +X hareketini masayı −X yönünde götürerek verir; uç–iş parçası ilişkisi SPEC 41 ile aynı).

Otomatik gövdeler (kullanıcı gövdesi bu adları kullanamaz):
- "is_parcasi" halkasında: "ham_malzeme" (Setup.stock), "fikstur_0", "fikstur_1", … (Setup.fixtures);
  WCS'den makineye `Wcs.origin` ile, kutu olarak (silindir ham malzeme sınır kutusuyla).
- "is_mili" halkasında (uç sıfır konumunda tip₀ = g − L·s, s iş mili yönü, uçtan iş miline):
  "takim" kapsül r = D/2, p = tip₀ + r·s, q = tip₀ + max(r, L_f − r)·s;
  "sap" kapsül r = shank/2, tip₀ + L_f·s → tip₀ + H_üst·s;
  "tutucu_0", "tutucu_1", … her SPEC 05 `body_steps` tutucu basamağı j için kapsül r = ρ_j,
  tip₀ + H_j·s → tip₀ + H_{j+1}·s (son basamakta H_üst). H_üst = tutucu varsa stickout + tutucu ölçü boyu
  (= L, ölçü hattı), yoksa L; sapın üstü tutucu varsa stickout.
  Basamaklar dilimsiz alınır (`body_steps(tool, dz=∞)`): her profil kesik konisi tek basamak, yarıçapı
  büyük ucu (güvenli taraf; bir temas birçok ince dilimde ayrı kayıt üretmez).

JSON (`to_dict`):
    {"profile": MachineProfile.to_dict(), "linear_carrier": {"X": "masa"|"kafa", "Y": …, "Z": …},
     "bodies": [{"name", "link", "shape": {"type": "kutu", "center", "half", "R"}
                                         | {"type": "kapsul", "p", "q", "r"}}],
     "ignore": [[a, b], …]}
Birimler: mm, derece.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np

from cam.model import CamError, Kinematics, MachineProfile, Setup, Stock, Tool
from cam.multiaxis.kinematics import rotation
from cam.sim.sweep import body_steps

LINKS_FIXED = ("taban", "X", "Y", "Z", "is_mili", "is_parcasi")
LINEARS = ("X", "Y", "Z")
TOL = 1e-9  # ortonormallik toleransı
_OTOMATIK = re.compile(r"^(ham_malzeme|takim|sap|fikstur_\d+|tutucu_\d+)$")

Pose = tuple[np.ndarray, np.ndarray]


def _vektor(nerede: str, v) -> tuple[float, float, float]:
    try:
        a = np.asarray(v, dtype=float)
    except (TypeError, ValueError) as e:
        raise CamError(f"{nerede}: 3 bileşenli sayı vektörü olmalı ({v!r})") from e
    if a.shape != (3,) or not np.all(np.isfinite(a)):
        raise CamError(f"{nerede}: 3 bileşenli sonlu vektör olmalı ({v!r})")
    return tuple(float(x) for x in a)


@dataclass
class Box:
    """Yönlendirilmiş kutu: merkez, yarı boylar (> 0), R ortonormal (sütunlar kutunun yerel eksenleri)."""

    center: tuple[float, float, float]
    half: tuple[float, float, float]
    R: tuple[tuple[float, float, float], ...] = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

    def __post_init__(self) -> None:
        self.center = _vektor("Kutu merkezi", self.center)
        self.half = _vektor("Kutu yarı boyları", self.half)
        if min(self.half) <= 0:
            raise CamError(f"Kutu: yarı boylar pozitif olmalı ({self.half})")
        try:
            M = np.asarray(self.R, dtype=float)
        except (TypeError, ValueError) as e:
            raise CamError(f"Kutu: R 3x3 olmalı ({self.R!r})") from e
        if M.shape != (3, 3) or not np.all(np.isfinite(M)):
            raise CamError(f"Kutu: R 3x3 sonlu olmalı ({self.R!r})")
        if np.max(np.abs(M.T @ M - np.eye(3))) > TOL or np.linalg.det(M) <= 0:
            raise CamError("Kutu: R ortonormal ve det R = +1 olmalı")
        self.R = tuple(tuple(float(x) for x in r) for r in M)

    @property
    def matrix(self) -> np.ndarray:
        return np.array(self.R, dtype=float)


@dataclass
class Capsule:
    """Kapsül: p–q doğru parçası etrafında r (> 0) yarıçaplı küre süpürmesi; p = q küre."""

    p: tuple[float, float, float]
    q: tuple[float, float, float]
    r: float

    def __post_init__(self) -> None:
        self.p = _vektor("Kapsül p", self.p)
        self.q = _vektor("Kapsül q", self.q)
        try:
            self.r = float(self.r)
        except (TypeError, ValueError) as e:
            raise CamError(f"Kapsül: r sayı olmalı ({self.r!r})") from e
        if not (math.isfinite(self.r) and self.r > 0):
            raise CamError(f"Kapsül: r pozitif sonlu olmalı ({self.r})")


@dataclass
class Body:
    """Bir halkaya bağlı gövde; şekil sıfır konumunda makine koordinatında."""

    name: str
    link: str
    shape: Box | Capsule


def _kin(profile: MachineProfile) -> Kinematics:
    return Kinematics() if profile.kinematics is None else profile.kinematics


@dataclass
class MachineModel:
    """Tezgâh: profil (doğrusal sınırlar, kinematik), doğrusal eksen taşıyıcıları, gövdeler, hariç çiftler."""

    profile: MachineProfile
    linear_carrier: dict[str, str]
    bodies: list[Body]
    ignore: list[tuple[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.profile, MachineProfile):
            raise CamError(f"Tezgâh modeli: profile MachineProfile olmalı ({type(self.profile).__name__})")
        if self.profile.kinematics is not None and not isinstance(self.profile.kinematics, Kinematics):
            raise CamError("Tezgâh modeli: profile.kinematics Kinematics olmalı")
        lc = dict(self.linear_carrier)
        if set(lc) != set(LINEARS):
            raise CamError(
                f"Tezgâh modeli: linear_carrier tam olarak X, Y, Z eksenlerini vermeli ({sorted(lc)})"
            )
        for ad, c in lc.items():
            if c not in ("masa", "kafa"):
                raise CamError(f"Tezgâh modeli: {ad} taşıyıcısı 'masa' veya 'kafa' olmalı ({c!r})")
        self.linear_carrier = {ad: lc[ad] for ad in LINEARS}
        self.bodies = list(self.bodies)
        halkalar = set(self.links)
        adlar: set[str] = set()
        for b in self.bodies:
            if not isinstance(b, Body):
                raise CamError(f"Tezgâh modeli: gövdeler Body olmalı ({type(b).__name__})")
            if not isinstance(b.name, str) or not b.name:
                raise CamError(f"Tezgâh modeli: gövde adı boş olmayan metin olmalı ({b.name!r})")
            if _OTOMATIK.match(b.name):
                raise CamError(f"Tezgâh modeli: '{b.name}' otomatik gövde adı, kullanılamaz")
            if b.name in adlar:
                raise CamError(f"Tezgâh modeli: yinelenen gövde adı '{b.name}'")
            adlar.add(b.name)
            if b.link not in halkalar:
                raise CamError(f"Tezgâh modeli: '{b.name}' gövdesinin halkası bilinmiyor ({b.link!r})")
            if not isinstance(b.shape, (Box, Capsule)):
                raise CamError(f"Tezgâh modeli: '{b.name}' şekli Box veya Capsule olmalı")
        ign = []
        for c in self.ignore:
            c = tuple(c)
            if len(c) != 2 or not all(isinstance(a, str) for a in c):
                raise CamError(f"Tezgâh modeli: ignore çifti iki gövde adı olmalı ({c!r})")
            for a in c:
                if a not in adlar and not _OTOMATIK.match(a):
                    raise CamError(f"Tezgâh modeli: ignore içinde bilinmeyen gövde '{a}'")
            ign.append((c[0], c[1]))
        self.ignore = ign

    @property
    def kinematics(self) -> Kinematics:
        return _kin(self.profile)

    @property
    def links(self) -> tuple[str, ...]:
        return LINKS_FIXED + tuple(a.name for a in self.kinematics.rotary)

    def chain(self, link: str) -> str:
        """Halkanın zinciri: "taban", "masa" veya "kafa"."""
        if link == "taban":
            return "taban"
        if link in LINEARS:
            return self.linear_carrier[link]
        if link == "is_mili":
            return "kafa"
        if link == "is_parcasi":
            return "masa"
        for a in self.kinematics.rotary:
            if a.name == link:
                return a.carrier
        raise CamError(f"Tezgâh modeli: bilinmeyen halka {link!r}")

    def to_dict(self) -> dict:
        def sekil(s: Box | Capsule) -> dict:
            if isinstance(s, Box):
                return {
                    "type": "kutu",
                    "center": list(s.center),
                    "half": list(s.half),
                    "R": [list(r) for r in s.R],
                }
            return {"type": "kapsul", "p": list(s.p), "q": list(s.q), "r": s.r}

        return {
            "profile": self.profile.to_dict(),
            "linear_carrier": dict(self.linear_carrier),
            "bodies": [{"name": b.name, "link": b.link, "shape": sekil(b.shape)} for b in self.bodies],
            "ignore": [list(c) for c in self.ignore],
        }

    @classmethod
    def from_dict(cls, d: dict) -> MachineModel:
        _anahtarlar("Tezgâh modeli", d, {"profile", "linear_carrier", "bodies"}, {"ignore"})
        bodies = []
        for b in d["bodies"]:
            _anahtarlar("Tezgâh gövdesi", b, {"name", "link", "shape"}, set())
            bodies.append(Body(name=b["name"], link=b["link"], shape=_sekil_from_dict(b["shape"])))
        return cls(
            profile=MachineProfile.from_dict(d["profile"]),
            linear_carrier=dict(d["linear_carrier"]),
            bodies=bodies,
            ignore=[tuple(c) for c in d.get("ignore", [])],
        )


def _anahtarlar(nerede: str, d, zorunlu: set[str], istege_bagli: set[str]) -> None:
    if not isinstance(d, dict):
        raise CamError(f"{nerede}: sözlük olmalı ({type(d).__name__})")
    eksik = zorunlu - set(d)
    fazla = set(d) - zorunlu - istege_bagli
    if eksik or fazla:
        raise CamError(f"{nerede}: eksik anahtar {sorted(eksik)}, bilinmeyen anahtar {sorted(fazla)}")


def _sekil_from_dict(d: dict) -> Box | Capsule:
    tur = d.get("type") if isinstance(d, dict) else None
    if tur == "kutu":
        _anahtarlar("Kutu", d, {"type", "center", "half"}, {"R"})
        R = tuple(tuple(r) for r in d["R"]) if "R" in d else Box.__dataclass_fields__["R"].default
        return Box(center=tuple(d["center"]), half=tuple(d["half"]), R=R)
    if tur == "kapsul":
        _anahtarlar("Kapsül", d, {"type", "p", "q", "r"}, set())
        return Capsule(p=tuple(d["p"]), q=tuple(d["q"]), r=d["r"])
    raise CamError(f"Bilinmeyen gövde şekli: {tur!r} (kutu veya kapsul)")


# ---------------------------------------------------------------- halka dönüşümleri


def _bilesim(a: Pose, b: Pose) -> Pose:
    """a ∘ b: x ↦ R_a (R_b x + t_b) + t_a."""
    return a[0] @ b[0], a[0] @ b[1] + a[1]


def _q(model: MachineModel, q) -> np.ndarray:
    k = len(model.kinematics.rotary)
    try:
        q = np.asarray(q, dtype=float)
    except (TypeError, ValueError) as e:
        raise CamError(f"Eklem değerleri sayı olmalı ({q!r})") from e
    if q.shape != (3 + k,) or not np.all(np.isfinite(q)):
        raise CamError(f"Eklem değerleri (X, Y, Z + {k} açı) sonlu olmalı ({q})")
    return q


def link_poses(model: MachineModel, q) -> dict[str, Pose]:
    """Eklem değerleri q = (X, Y, Z, θ…) → her halkanın dönüşümü (R, t)."""
    q = _q(model, q)
    kin = model.kinematics
    I3 = np.eye(3)
    P: dict[str, Pose] = {"taban": (I3, np.zeros(3))}
    birikim = {"masa": np.zeros(3), "kafa": np.zeros(3)}
    for i, ad in enumerate(LINEARS):
        c = model.linear_carrier[ad]
        birikim[c] = birikim[c].copy()
        birikim[c][i] += q[i]
        P[ad] = (I3, birikim[c].copy() if c == "kafa" else -birikim[c])
    T = {"kafa": (I3, birikim["kafa"].copy()), "masa": (I3, -birikim["masa"])}
    for a, theta in zip(kin.rotary, q[3:], strict=True):
        R = rotation(a.u, float(theta))
        c = np.array(a.pivot)
        T[a.carrier] = _bilesim(T[a.carrier], (R, c - R @ c))
        P[a.name] = T[a.carrier]
    P["is_mili"] = T["kafa"]
    P["is_parcasi"] = T["masa"]
    return P


def poses(model: MachineModel, q, setup: Setup, tool: Tool) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Eklem değerleri q = (X, Y, Z, θ…) → her halkanın dönüşümü {ad: (R (3, 3), t (3,))}."""
    if not isinstance(setup, Setup):
        raise CamError(f"poses: setup Setup olmalı ({type(setup).__name__})")
    if not isinstance(tool, Tool):
        raise CamError(f"poses: tool freze takımı (Tool) olmalı ({type(tool).__name__})")
    return link_poses(model, q)


# ---------------------------------------------------------------- otomatik gövdeler


def _kutu(s, origin: np.ndarray) -> Box:
    if isinstance(s, Stock):
        lo = np.array([s.xmin, s.ymin, s.zmin])
        hi = np.array([s.xmax, s.ymax, s.zmax])
    else:
        lo, hi = s.bbox()
    return Box(center=tuple((lo + hi) / 2 + origin), half=tuple((hi - lo) / 2))


def setup_bodies(setup: Setup) -> list[Body]:
    """ "is_parcasi" halkasının otomatik gövdeleri: ham malzeme ve fikstürler (makine koordinatında)."""
    o = np.array(setup.wcs.origin)
    out = [Body("ham_malzeme", "is_parcasi", _kutu(setup.stock, o))]
    out += [Body(f"fikstur_{i}", "is_parcasi", _kutu(f, o)) for i, f in enumerate(setup.fixtures)]
    return out


def tool_bodies(kin: Kinematics, tool: Tool, L: float) -> list[Body]:
    """ "is_mili" halkasının otomatik gövdeleri: takım, sap, tutucu basamakları (sıfır konumunda)."""
    if not isinstance(tool, Tool):
        raise CamError(f"Tezgâh çarpışması: freze takımı (Tool) gerekli ({type(tool).__name__})")
    if not (math.isfinite(L) and L > 0):
        raise CamError(f"Tezgâh çarpışması: takım boyu L pozitif olmalı ({L})")
    s = np.array(kin.spindle)
    tip0 = np.array(kin.gauge) - L * s

    def kapsul(h0: float, h1: float, r: float) -> Capsule:
        return Capsule(p=tuple(tip0 + h0 * s), q=tuple(tip0 + max(h0, h1) * s), r=r)

    r = tool.D / 2
    L_f = float(tool.flute_length)
    out = [Body("takim", "is_mili", kapsul(r, max(r, L_f - r), r))]
    tutuculu = tool.holder is not None and tool.stickout is not None
    sap_ust = float(tool.stickout) if tutuculu else L
    if sap_ust > L_f:
        out.append(Body("sap", "is_mili", kapsul(L_f, sap_ust, tool.shank / 2)))
    if tutuculu:
        basamak = [(rho, H) for rho, H, tur in body_steps(tool, dz=math.inf) if tur == "tutucu"]
        for j, (rho, H) in enumerate(basamak):
            H_ust = basamak[j + 1][1] if j + 1 < len(basamak) else L
            out.append(Body(f"tutucu_{j}", "is_mili", kapsul(H, H_ust, rho)))
    return out
