"""
SPEC 25 — Montaj köprüsü: ağaç (07), kısıtlar (08), girişim (09) → `Montaj` JSON ve ikili ağlar.

Saf fonksiyonlar, web bağımlılığı yok. Birimler mm, t (kütle), t/mm³ (yoğunluk).

Montaj sözlüğü:
    {
      "sema": 1, "ad",
      "agac": Node.to_dict(),
      "parcalar": [{"kimlik", "ad", "malzeme", "rho", "kaynak": {"is", "tur"} | None, "hacim"}],
      "bilesenler": [{"yol", "parca", "T": 4x4 (satır öncelikli liste), "sabit"}],  # çözülmüş
      "bom": [BomLine sözlüğü], "kutle": {"toplam", "merkez": [x, y, z]},
      "sira": [Adim], "girisimler": [Girisim], "kontroller": [Kontrol], "baglar": [Bag]
    }
    Adim = {"i", "yol", "ad", "yaklasma": [ax, ay, az], "mesafe", "T_once": {yol: 4x4}, "T_sonra": {yol: 4x4},
            "dof_toplam", "serbestlik": {yol: Serbestlik}}
    Serbestlik = {"sayi", "oteleme": [[ux, uy, uz]], "vida": [{"yon", "nokta", "hatve"}], "etiketler": [str]}
    Girisim = {"i", "a", "b", "hacim", "bosluk", "ag": "/api/ekran/montaj/{ad}/ag/girisim/{i}"}

Kısıtlar bileşen adı olarak yaprak yolunu (SPEC 07 `walk`) kullanır.
Hata: yapı hatası `AssyError`, şekil hatası `GeometryError`; sessiz düzeltme yok (altın kural 5).
"""

from __future__ import annotations

import dataclasses
import struct
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from assy.bom import bom, mass_center, total_mass, unit_masses
from assy.girisim import ClashKind, check
from assy.mates import jacobian, rodrigues
from assy.model import Assembly, AssyError, Mate, MateKind, Node, RefKind, transform
from assy.solver import dof, residuals, solve
from assy.tree import apply, flatten, walk

if TYPE_CHECKING:
    from geometry.part import Part
    from tezgah.iplik import Bag

ETIKET_TOL = 1e-9  # 1 − |yön·e| eşiği: dünya eksenine paralel serbestlik etiketi
SIMETRI_ACI = 37.0  # derece: dönel simetri sınaması
SIMETRI_TOL = 1e-6  # rel: common(parça, döndürülmüş) hacmi / parça hacmi


@dataclass
class Vida:
    """Serbest hareket vida ekseni (Murray–Li–Sastry 2.4).

    yön ω/|ω|, eksen noktası ω×Δt/|ω|², hatve ω·Δt/|ω|².
    """

    yon: np.ndarray  # (3,) birim
    nokta: np.ndarray  # (3,)
    hatve: float  # mm/rad


@dataclass
class Serbestlik:
    """Bir bileşenin diğerleri sabitken kalan serbest hareketleri.

    sayi     : 6 − rank(J_c)
    oteleme  : (a, 3) ortonormal öteleme yönleri ({v ∈ N : ω = 0})
    vida     : öteleme alt uzayının N içindeki dik tümleyeninin taban vektörlerinden vida eksenleri
    etiketler: "Tx".."Tz", "Rx".."Rz" (dünya eksenine paralel) ya da "T" / "vida"
    """

    sayi: int
    oteleme: np.ndarray
    vida: list[Vida] = field(default_factory=list)
    etiketler: list[str] = field(default_factory=list)


@dataclass
class MontajTanimi:
    """Bir montaj örneği.

    agac       : SPEC 07 kök düğümü
    parcalar   : parça kimliği → Part (parçanın kendi koordinatında)
    malzemeler : parça kimliği → (malzeme adı, ρ [t/mm³])
    kisitlar   : SPEC 08 kısıtları; Ref.component = yaprak yolu
    sabit      : sabit yaprak yolları (flatten `fixed`)
    sira       : yaprak yolları, montaj sırası; ilk eleman sabit olmalı
    kaynaklar  : parça kimliği → (iş adı, "torna" | "freze") — parça bir işten geliyorsa
    baglar     : parametre bağları (tezgah.iplik.Bag)
    """

    ad: str
    agac: Node
    parcalar: dict[str, Part]
    malzemeler: dict[str, tuple[str, float]]
    kisitlar: list[Mate]
    sabit: tuple[str, ...]
    sira: list[str]
    kaynaklar: dict[str, tuple[str, str]] = field(default_factory=dict)
    baglar: list[Bag] = field(default_factory=list)


RANK_RTOL = 1e-8  # sayısal rank eşiği σ_i > 1e-8·σ_max (SPEC 08 `dof` ile aynı kural)
ALT_TOL = 1e-9  # sıfır uzayı içinde ω = 0 alt uzayı: ω bloğunun tekil değer eşiği
HATVE_TOL = 1e-9  # mm/rad: |h| bundan küçükse saf dönme
KISIT_TOL = 1e-6  # mm: kısıt artığı kontrolünün eşiği
SEMA = 1
EKSENLER = "xyz"


# ---------------------------------------------------------------- montaj ve çözüm


def montaj(tanim: MontajTanimi) -> Assembly:
    """`flatten(agac, sabit)` + kısıtlar: çözülmemiş SPEC 08 montajı."""
    asm = flatten(tanim.agac, tanim.sabit)
    asm.mates = list(tanim.kisitlar)
    return asm


def _cozulmus(tanim: MontajTanimi) -> Assembly:
    asm = montaj(tanim)
    solve(asm).apply(asm)
    return asm


def _duz(T: np.ndarray) -> list[float]:
    """4x4 → 16 sayılık satır öncelikli liste (Montaj JSON biçimi)."""
    return [float(v) for v in np.asarray(T, dtype=float).reshape(16)]


# ---------------------------------------------------------------- parça serbestliği


def _rank(J: np.ndarray) -> tuple[int, np.ndarray]:
    """(rank, Vᵀ): SVD ile sayısal rank; Vᵀ'nin son 6 − rank satırı sıfır uzayının ortonormal tabanı."""
    if J.size == 0:
        return 0, np.eye(J.shape[1])
    _, sigma, Vt = np.linalg.svd(J)
    s_max = float(sigma.max()) if sigma.size else 0.0
    r = 0 if s_max == 0.0 else int(np.sum(sigma > RANK_RTOL * s_max))
    return r, Vt


def _eksene_hizali(B: np.ndarray) -> np.ndarray:
    """B (3, k) sütunlarının uzayında önce dünya eksenleri, kalan Gram–Schmidt ile: (3, k) ortonormal."""
    Q, _ = np.linalg.qr(B)
    secilen: list[np.ndarray] = []
    for e in np.eye(3):
        if len(secilen) == B.shape[1]:
            break
        if np.linalg.norm(Q @ (Q.T @ e)) >= 1.0 - 1e-12:
            secilen.append(e)
    for q in Q.T:
        if len(secilen) == B.shape[1]:
            break
        v = q - sum(np.dot(q, s) * s for s in secilen)
        if np.linalg.norm(v) > 1e-9:
            secilen.append(v / np.linalg.norm(v))
    return np.array(secilen).T.reshape(3, -1)


def _etiket(yon: np.ndarray, harf: str) -> str:
    for i, e in enumerate(np.eye(3)):
        if 1.0 - abs(float(np.dot(yon, e))) <= ETIKET_TOL:
            return f"{harf}{EKSENLER[i]}"
    return "T" if harf == "T" else "vida"


def serbestlik(assembly: Assembly, bilesen: str) -> Serbestlik:
    """Diğer bileşenler sabitken `bilesen`in serbestliği: J_c'nin sıfır uzayı (SPEC 08 `jacobian`) (K10).

    Δt SPEC 08'deki gibi bileşenin başlangıcının (T'nin öteleme kısmı t) ötelemesidir; vida ekseninin noktası
    dünya koordinatında verilir: p = t + ω × Δt / |ω|².
    """
    c = assembly.component(bilesen)
    if c.fixed:
        return Serbestlik(0, np.zeros((0, 3)))
    dokunan = [m for m in assembly.mates if bilesen in (m.a.component, m.b.component)]
    J = np.vstack([jacobian(assembly, m, [bilesen]) for m in dokunan]) if dokunan else np.zeros((0, 6))
    r, Vt = _rank(J)
    N = Vt[r:].T  # (6, k) ortonormal
    k = N.shape[1]
    if k == 0:
        return Serbestlik(0, np.zeros((0, 3)))
    # Öteleme alt uzayı: N c, ω = N[3:] c = 0
    _, s, Wt = np.linalg.svd(N[3:])
    q = int(np.sum(s > ALT_TOL))
    C_ot = Wt[q:].T  # (k, a) ω = 0 yönleri
    C_vida = Wt[:q].T  # (k, q) dik tümleyen
    U = _eksene_hizali(N[:3] @ C_ot) if C_ot.shape[1] else np.zeros((3, 0))
    vidalar = _vida_tabani(N @ C_vida, c.T[:3, 3]) if C_vida.shape[1] else []
    etiketler = [_etiket(u, "T") for u in U.T] + [_etiket(v.yon, "R") for v in vidalar]
    return Serbestlik(k, U.T.copy(), vidalar, etiketler)


def _vida_tabani(W: np.ndarray, t: np.ndarray) -> list[Vida]:
    """W (6, q) vida taban vektörleri → vida eksenleri. ω'ları dünya eksenine hizalı seçilir (mümkünse)."""
    Om = W[3:]
    hedef = _eksene_hizali(Om)  # (3, q): ω uzayının (eksene hizalı) tabanı
    C = np.linalg.lstsq(Om, hedef, rcond=None)[0]  # Om C = hedef
    V = W @ C
    out = []
    for v in V.T:
        dt, w = v[:3], v[3:]
        w2 = float(np.dot(w, w))
        yon = w / np.sqrt(w2)
        out.append(Vida(yon, t + np.cross(w, dt) / w2, float(np.dot(w, dt) / w2)))
    return out


def _serbestlik_dict(s: Serbestlik) -> dict:
    return {
        "sayi": int(s.sayi),
        "oteleme": [[float(v) for v in u] for u in np.asarray(s.oteleme).reshape(-1, 3)],
        "vida": [
            {"yon": [float(v) for v in d.yon], "nokta": [float(v) for v in d.nokta], "hatve": float(d.hatve)}
            for d in s.vida
        ],
        "etiketler": list(s.etiketler),
    }


# ---------------------------------------------------------------- yaklaşma ve sıra


def _kimlik(tanim: MontajTanimi, yol: str) -> str:
    for y, n, _ in walk(tanim.agac):
        if y == yol and n.part is not None:
            return n.part
    raise AssyError(f"Bilinmeyen yaprak yolu: '{yol}'")


def _kutle_merkezi(tanim: MontajTanimi, assembly: Assembly, yol: str) -> np.ndarray:
    T = assembly.component(yol).T
    c = np.asarray(tanim.parcalar[_kimlik(tanim, yol)].center_of_mass, dtype=float)
    return T[:3, :3] @ c + T[:3, 3]


def _kosegen(part: Part) -> float:
    lo, hi = part.bbox
    return float(np.linalg.norm(np.asarray(hi, dtype=float) - np.asarray(lo, dtype=float)))


def _bag_kisitlari(assembly: Assembly, bilesen: str, yerlesmis: list[str]) -> list[tuple[Mate, str]]:
    """`bilesen`i yerleşmiş bir bileşene bağlayan kısıtlar ve karşı bileşen, tanım sırasıyla."""
    ys = set(yerlesmis)
    out = []
    for m in assembly.mates:
        if m.a.component == bilesen and m.b.component in ys:
            out.append((m, m.b.component))
        elif m.b.component == bilesen and m.a.component in ys:
            out.append((m, m.a.component))
    return out


def yaklasma(
    tanim: MontajTanimi, assembly: Assembly, bilesen: str, yerlesmis: list[str]
) -> tuple[np.ndarray, float]:
    """Yaklaşma yönü a (birim) ve mesafe (bileşenin sınır kutusu köşegeni); SPEC 25 kuralı (K11).

    1. yerleşmiş bir bileşenle CONCENTRIC → eksen yönü; 2. yoksa PLANE içeren ilk kısıtın normali;
    3. yoksa +Z.
    İşaret: (bileşenin kütle merkezi − karşı bileşenin kütle merkezi)·a ≥ 0. Kısıt yoksa karşı bileşen sıranın
    ilk yerleşmiş bileşenidir; hiç yerleşmiş bileşen yoksa +a.
    """
    baglar = _bag_kisitlari(assembly, bilesen, yerlesmis)
    a, karsi = np.array([0.0, 0.0, 1.0]), (yerlesmis[0] if yerlesmis else None)
    secilen = next(((m, k) for m, k in baglar if m.kind is MateKind.CONCENTRIC), None)
    if secilen is None:
        secilen = next(((m, k) for m, k in baglar if RefKind.PLANE in (m.a.kind, m.b.kind)), None)
    if secilen is not None:
        m, karsi = secilen
        # karşı tarafın referansı tercih edilir (yerleşmiş); düzlem o tarafta değilse bileşeninki
        refler = (m.b, m.a) if m.a.component == bilesen else (m.a, m.b)
        tur = RefKind.AXIS if m.kind is MateKind.CONCENTRIC else RefKind.PLANE
        ref = next(r for r in refler if r.kind is tur)
        a = np.asarray(assembly.world(ref)[1], dtype=float)
        a = a / np.linalg.norm(a)
    if karsi is not None:
        d = _kutle_merkezi(tanim, assembly, bilesen) - _kutle_merkezi(tanim, assembly, karsi)
        if float(np.dot(d, a)) < 0.0:
            a = -a
    return a, _kosegen(tanim.parcalar[_kimlik(tanim, bilesen)])


def _sira_denetle(tanim: MontajTanimi) -> None:
    yollar = [y for y, n, _ in walk(tanim.agac)]
    yapraklar = [y for y, n, _ in walk(tanim.agac) if n.part is not None]
    gorulen: set[str] = set()
    for yol in tanim.sira:
        if yol not in yollar:
            raise AssyError(f"Montaj sırası: bilinmeyen yol '{yol}'")
        if yol not in yapraklar:
            raise AssyError(f"Montaj sırası: '{yol}' yaprak değil (alt montaj)")
        if yol in gorulen:
            raise AssyError(f"Montaj sırası: '{yol}' iki kez geçiyor")
        gorulen.add(yol)
    eksik = [y for y in yapraklar if y not in gorulen]
    if eksik:
        raise AssyError(f"Montaj sırası: yapraklar sırada yok: {eksik}")
    if tanim.sira[0] not in tanim.sabit:
        raise AssyError(f"Montaj sırası: ilk adım ('{tanim.sira[0]}') sabit bir bileşen olmalı")


def _alt_montaj(tam: Assembly, yerlesmis: list[str]) -> Assembly:
    """Yerleşmiş bileşenler (başlangıç T'leriyle, flatten sırasıyla) ve iki ucu da yerleşmiş kısıtlar."""
    ys = set(yerlesmis)
    return Assembly(
        name=tam.name,
        components=[c for c in tam.components if c.name in ys],
        mates=[m for m in tam.mates if m.a.component in ys and m.b.component in ys],
    )


def _ad(tanim: MontajTanimi, assembly: Assembly, yol: str, yerlesmis: list[str]) -> str:
    ad = yol.rsplit("/", 1)[-1]
    baglar = _bag_kisitlari(assembly, yol, yerlesmis)
    return f"{ad} → {baglar[0][1].rsplit('/', 1)[-1]}" if baglar else ad


def sira_adimlari(tanim: MontajTanimi) -> list[dict]:
    """Montaj sırasının adımları (`Adim` sözlükleri). Geçersiz sıra → AssyError (K9, K11)."""
    _sira_denetle(tanim)
    tam = montaj(tanim)
    adimlar = []
    for i, yol in enumerate(tanim.sira):
        yerlesmis = list(tanim.sira[: i + 1])
        alt = _alt_montaj(tam, yerlesmis)
        dof_toplam = dof(alt)
        r = solve(alt)
        cozulmus = Assembly(
            alt.name, [dataclasses.replace(c, T=r.T[c.name]) for c in alt.components], alt.mates
        )
        a, mesafe = yaklasma(tanim, cozulmus, yol, yerlesmis[:-1])
        T_sonra = {y: np.asarray(r.T[y], dtype=float) for y in yerlesmis}
        T_once = dict(T_sonra)
        T_once[yol] = transform(R=T_sonra[yol][:3, :3], t=T_sonra[yol][:3, 3] + mesafe * a)
        adimlar.append(
            {
                "i": i,
                "yol": yol,
                "ad": _ad(tanim, cozulmus, yol, yerlesmis[:-1]),
                "yaklasma": [float(v) for v in a],
                "mesafe": float(mesafe),
                "T_once": {y: _duz(T) for y, T in T_once.items()},
                "T_sonra": {y: _duz(T) for y, T in T_sonra.items()},
                "dof_toplam": int(dof_toplam),
                "serbestlik": {y: _serbestlik_dict(serbestlik(cozulmus, y)) for y in yerlesmis},
            }
        )
    return adimlar


# ---------------------------------------------------------------- simetri ve girişim


def donel_simetrik(part: Part, yon: np.ndarray, nokta: np.ndarray) -> bool:
    """Parça (nokta, yon) ekseni etrafında 37° döndürülünce common hacmi parça hacmine rel 1e-6 ile eşit mi.

    common: SPEC 09.
    """
    yon = np.asarray(yon, dtype=float)
    yon = yon / np.linalg.norm(yon)
    p = np.asarray(nokta, dtype=float)
    R = rodrigues(np.radians(SIMETRI_ACI) * yon)
    donmus = part.moved(transform(R=R, t=p - R @ p))
    ortak = part.common(donmus)
    if ortak is None:
        return False
    return abs(ortak.volume - part.volume) <= SIMETRI_TOL * part.volume


def _girisimler(tanim: MontajTanimi, asm: Assembly) -> list:
    """SPEC 09 GIRISIM kayıtları (tam, çözülmüş montajda), walk sırasıyla."""
    return [c for c in check(apply(tanim.agac, asm), tanim.parcalar) if c.kind == ClashKind.GIRISIM]


def _girisim_dict(tanim: MontajTanimi, i: int, c) -> dict:
    return {
        "i": i,
        "a": c.a,
        "b": c.b,
        "hacim": float(c.volume),
        "bosluk": float(c.distance),
        "ag": f"/api/ekran/montaj/{tanim.ad}/ag/girisim/{i}",
    }


def cift_hacmi(tanim: MontajTanimi, a: str, b: str) -> float:
    """Tam (çözülmüş) montajda a–b çiftinin SPEC 09 kesişim hacmi; girişim yoksa 0 (K16)."""
    asm = _cozulmus(tanim)
    for yol in (a, b):
        asm.component(yol)  # bilinmeyen yol → AssyError
    for c in _girisimler(tanim, asm):
        if {c.a, c.b} == {a, b}:
            return float(c.volume)
    return 0.0


def girisimler(tanim: MontajTanimi) -> list[dict]:
    """Tam montajda hacmi > 0 olan çiftler (SPEC 09 `assy.girisim.check`), `Girisim` sözlükleri (K12)."""
    return [_girisim_dict(tanim, i, c) for i, c in enumerate(_girisimler(tanim, _cozulmus(tanim)))]


# ---------------------------------------------------------------- kontroller


def _kontrol(kimlik: str, baslik: str, durum: str, deger, birim: str, aciklama: str, spec: str) -> dict:
    return {
        "kimlik": kimlik,
        "baslik": baslik,
        "deger": deger,
        "birim": birim,
        "durum": durum,
        "aciklama": aciklama,
        "spec": spec,
    }


def _serbestlik_kontrolu(tanim: MontajTanimi, asm: Assembly, yol: str) -> dict:
    """SPEC 25 kuralı: 0 → tamam; yalnız saf dönmeler ve her eksende dönel simetrik → tamam; aksi uyarı."""
    s = serbestlik(asm, yol)
    kimlik, baslik = f"serbestlik:{yol}", f"Serbestlik: {yol}"
    if s.sayi == 0:
        return _kontrol(kimlik, baslik, "tamam", 0, "", "Tam kısıtlı", "SPEC 08")
    T = asm.component(yol).T
    R, t = T[:3, :3], T[:3, 3]
    part = tanim.parcalar[_kimlik(tanim, yol)]
    eksik = [_etiket(u, "T") for u in np.asarray(s.oteleme).reshape(-1, 3)]
    for v, etiket in zip(s.vida, s.etiketler[len(eksik) :], strict=True):
        saf = abs(v.hatve) <= HATVE_TOL
        if not (saf and donel_simetrik(part, R.T @ v.yon, R.T @ (v.nokta - t))):
            eksik.append(etiket)
    if not eksik:
        return _kontrol(
            kimlik, baslik, "tamam", s.sayi, "", "Simetri serbestliği (dönel simetrik)", "SPEC 08/09"
        )
    return _kontrol(kimlik, baslik, "uyari", s.sayi, "", f"eksik kısıt: {' '.join(eksik)}", "SPEC 08")


def _kontroller(tanim: MontajTanimi, asm: Assembly, G: list, m: dict[str, float]) -> list[dict]:
    r = residuals(asm)
    r_max = float(np.max(np.abs(r))) if r.size else 0.0
    out = [
        _kontrol(
            "kisit_artigi",
            "Kısıt artığı",
            "tamam" if r_max <= KISIT_TOL else "hata",
            r_max,
            "mm",
            f"max|r| = {r_max:.3e}",
            "SPEC 08",
        )
    ]
    out += [_serbestlik_kontrolu(tanim, asm, c.name) for c in asm.components if not c.fixed]
    V = float(sum(c.volume for c in G))
    aciklama = "Girişim yok" if not G else "; ".join(f"{c.a} – {c.b}: {c.volume:.3f} mm³" for c in G)
    out.append(_kontrol("girisim", "Girişim hacmi", "hata" if G else "tamam", V, "mm³", aciklama, "SPEC 09"))
    M = total_mass(tanim.agac, m)
    out.append(
        _kontrol("kutle", "Toplam kütle", "tamam", M, "t", f"{len(asm.components)} bileşen", "SPEC 07")
    )
    return out


def _birim_kutleler(tanim: MontajTanimi) -> dict[str, float]:
    return unit_masses(tanim.parcalar, {k: rho for k, (_, rho) in tanim.malzemeler.items()})


def kontroller(tanim: MontajTanimi) -> list[dict]:
    """kisit_artigi, serbestlik (SPEC 25 kuralı), girisim, kutle kontrolleri (K13)."""
    asm = _cozulmus(tanim)
    return _kontroller(tanim, asm, _girisimler(tanim, asm), _birim_kutleler(tanim))


# ---------------------------------------------------------------- Montaj JSON


def montaj_json(tanim: MontajTanimi) -> dict:
    """`Montaj` sözlüğü (modül belgesi) (K8)."""
    asm = _cozulmus(tanim)
    G = _girisimler(tanim, asm)
    m = _birim_kutleler(tanim)
    return {
        "sema": SEMA,
        "ad": tanim.ad,
        "agac": tanim.agac.to_dict(),
        "parcalar": [
            {
                "kimlik": k,
                "ad": p.name,
                "malzeme": tanim.malzemeler[k][0],
                "rho": tanim.malzemeler[k][1],
                "kaynak": None
                if k not in tanim.kaynaklar
                else {"is": tanim.kaynaklar[k][0], "tur": tanim.kaynaklar[k][1]},
                "hacim": float(p.volume),
            }
            for k, p in tanim.parcalar.items()
        ],
        "bilesenler": [
            {"yol": c.name, "parca": c.part, "T": _duz(c.T), "sabit": c.fixed} for c in asm.components
        ],
        "bom": [dataclasses.asdict(b) for b in bom(tanim.agac, m)],
        "kutle": {
            "toplam": total_mass(tanim.agac, m),
            "merkez": [float(v) for v in mass_center(apply(tanim.agac, asm), tanim.parcalar, m)],
        },
        "sira": sira_adimlari(tanim),
        "girisimler": [_girisim_dict(tanim, i, c) for i, c in enumerate(G)],
        "kontroller": _kontroller(tanim, asm, G, m),
        "baglar": [
            {
                "parametre": {
                    "is": b.is_ad,
                    "anahtar": b.anahtar,
                    "deger": b.deger,
                    "min": b.min,
                    "max": b.max,
                },
                "parcalar": list(b.parcalar),
            }
            for b in tanim.baglar
        ],
    }


# ---------------------------------------------------------------- ikili ağlar


def _hizala(b: bytes) -> bytes:
    return b + bytes(-len(b) % 8)


def ag_ikili(V: np.ndarray, T: np.ndarray) -> bytes:
    """Üçgen ağ, little-endian (K14).

    uint32 sema, uint32 nv, uint32 nt, uint32 0, float32[nv·3], uint32[nt·3]; bloklar 8'e tamamlanır.
    """
    V = np.asarray(V, dtype=float).reshape(-1, 3)
    T = np.asarray(T).reshape(-1, 3)
    if T.size and (T.min() < 0 or T.max() >= len(V)):
        raise ValueError(f"Ağ: üçgen indeksi köşe sayısı dışında (nv = {len(V)})")
    return (
        struct.pack("<IIII", SEMA, len(V), len(T), 0)
        + _hizala(V.astype("<f4").tobytes())
        + _hizala(T.astype("<u4").tobytes())
    )


def ag_coz(veri: bytes) -> tuple[np.ndarray, np.ndarray]:
    """`ag_ikili` çıktısı → (V (nv, 3) float32, T (nt, 3) uint32)."""
    sema, nv, nt, sifir = struct.unpack_from("<IIII", veri, 0)
    if sema != SEMA or sifir != 0:
        raise ValueError(f"Ağ: bilinmeyen biçim (sema {sema})")
    a, b = 12 * nv + (-12 * nv % 8), 12 * nt + (-12 * nt % 8)
    if len(veri) != 16 + a + b:
        raise ValueError(f"Ağ: uzunluk {len(veri)} ≠ {16 + a + b}")
    V = np.frombuffer(veri, dtype="<f4", count=3 * nv, offset=16).reshape(nv, 3).astype(np.float32)
    T = np.frombuffer(veri, dtype="<u4", count=3 * nt, offset=16 + a).reshape(nt, 3).astype(np.uint32)
    return V, T


def parca_agi(tanim: MontajTanimi, kimlik: str, tol: float = 0.01) -> bytes:
    """Parçanın kendi koordinatındaki ağı (`Part.mesh`), `ag_ikili` biçiminde (K14). Bilinmeyen → KeyError."""
    if kimlik not in tanim.parcalar:
        raise KeyError(f"Bilinmeyen parça: '{kimlik}'")
    return ag_ikili(*tanim.parcalar[kimlik].mesh(tol))


def girisim_agi(tanim: MontajTanimi, i: int, tol: float = 0.01) -> bytes:
    """i. girişimin kesişim katısının dünya koordinatındaki ağı, `ag_ikili` biçiminde (K12).

    Bilinmeyen indeks → IndexError.
    """
    asm = _cozulmus(tanim)
    G = _girisimler(tanim, asm)
    if not 0 <= i < len(G):
        raise IndexError(f"Girişim {i} yok ({len(G)} girişim)")
    c = G[i]
    A = tanim.parcalar[_kimlik(tanim, c.a)].moved(asm.component(c.a).T)
    B = tanim.parcalar[_kimlik(tanim, c.b)].moved(asm.component(c.b).T)
    ortak = A.common(B)
    if ortak is None:
        raise AssyError(f"Girişim {i}: kesişim katısı bulunamadı ({c.a} – {c.b})")
    return ag_ikili(*ortak.mesh(tol))
