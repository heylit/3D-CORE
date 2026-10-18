"""
SPEC 25 — montaj köprüsü (`tezgah/montaj.py`): K8–K14.

Beklenen değerler köprüden değil, SPEC 07 (`assy.tree`, `assy.bom`), SPEC 08 (`assy.solver`), SPEC 09
(`assy.girisim`, `Part.common`), SPEC 02 (`Part.volume`, `geometry.mesh.mesh_volume`) ve Teori bölümündeki
kapalı formlardan hesaplanır.

- K10'un saf testleri OCCT istemez (yalnız `Assembly` + kısıtlar). Serbest bileşenin T'si birimdir: böylece
  SPEC 08 Jacobian'ındaki Δt'nin referans noktası (bileşen başlangıcı) dünya başlangıcıyla çakışır ve vida
  ekseni noktası `p = ω × Δt / |ω|²` doğrudan dünya koordinatıdır.
- Örnek `yatak_grubu` testleri build123d ve SPEC 09'u (`Part.fuse` / `common`) ister; yoksa atlanır.
  Örnekte bileşenler montaj sırasıyla tanınır (SPEC: plaka, rulman, mil, dört pim).
"""

from __future__ import annotations

import dataclasses
import json
import math
import struct

import numpy as np
import pytest

from assy.bom import bom, mass_center, total_mass, unit_masses
from assy.model import Assembly, AssyError, MateKind
from assy.solver import dof, solve
from assy.tree import apply, flatten, walk
from tests.tezgah import montaj_ornekleri as mo
from tezgah.montaj import (
    ETIKET_TOL,
    SIMETRI_ACI,
    SIMETRI_TOL,
    ag_coz,
    donel_simetrik,
    girisim_agi,
    girisimler,
    kontroller,
    montaj,
    montaj_json,
    parca_agi,
    serbestlik,
    sira_adimlari,
    yaklasma,
)

EZ = np.array([0.0, 0.0, 1.0])


# ---------------------------------------------------------------- yardımcılar


def _occt():
    pytest.importorskip("build123d")


def _spec09():
    """SPEC 09 boolean'ları Part arayüzünde (Part.common / fuse); yoksa atla."""
    _occt()
    from geometry.part import Part

    if not (hasattr(Part, "common") and hasattr(Part, "fuse")):
        pytest.skip("SPEC 09 (Part.common / Part.fuse) henüz yok")


def _girisim_modulu():
    _spec09()
    return pytest.importorskip("assy.girisim", reason="SPEC 09 (assy.girisim) henüz yok")


def _ornek(L: float | None = None):
    _spec09()
    from tezgah.ornekler_25 import yatak_grubu

    return yatak_grubu(None if L is None else {"kademeli_mil": {"L": L}})


def _beklenen_montaj(tanim) -> Assembly:
    asm = flatten(tanim.agac, tanim.sabit)
    asm.mates = list(tanim.kisitlar)
    return asm


def _cozulmus(tanim) -> Assembly:
    asm = _beklenen_montaj(tanim)
    solve(asm).apply(asm)
    return asm


def _alt_montaj(tanim, yerlesmis: list[str]) -> Assembly:
    """Teori: yerleşmiş bileşenler (başlangıç T'leriyle) ve iki ucu da yerleşmiş kısıtlar."""
    tam = _beklenen_montaj(tanim)
    ys = set(yerlesmis)
    return Assembly(
        name=tam.name,
        components=[c for c in tam.components if c.name in ys],
        mates=[m for m in tam.mates if m.a.component in ys and m.b.component in ys],
    )


def _kimlik(tanim, yol: str) -> str:
    return next(n.part for y, n, _ in walk(tanim.agac) if y == yol)


def _birim_kutleler(tanim) -> dict[str, float]:
    return unit_masses(tanim.parcalar, {k: rho for k, (_, rho) in tanim.malzemeler.items()})


def _json_tur(x):
    return json.loads(json.dumps(x, allow_nan=False))


def _T(x) -> np.ndarray:
    return np.array(x, dtype=float).reshape(4, 4)


def _ag_oku(veri: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Belgedeki biçimin bağımsız okuyucusu:
    uint32 sema, nv, nt, 0; float32[nv·3]; uint32[nt·3]; 8'e tamamlı."""
    sema, nv, nt, sifir = struct.unpack_from("<IIII", veri, 0)
    assert sema == 1 and sifir == 0
    a = 12 * nv + (-12 * nv % 8)
    b = 12 * nt + (-12 * nt % 8)
    assert len(veri) == 16 + a + b
    V = np.frombuffer(veri, dtype="<f4", count=3 * nv, offset=16).reshape(nv, 3)
    T = np.frombuffer(veri, dtype="<u4", count=3 * nt, offset=16 + a).reshape(nt, 3)
    assert nt == 0 or int(T.max()) < nv
    return V.astype(float), T.astype(np.int64)


def _mesh_volume(V, T) -> float:
    from geometry.mesh import mesh_volume

    return float(mesh_volume(np.asarray(V, dtype=float), np.asarray(T, dtype=np.int64)))


# ---------------------------------------------------------------- K10: parça serbestliği (saf)


def _twist_tabani(s) -> np.ndarray:
    """Serbestlik → sıfır uzayı tabanı (6, k): öteleme (u, 0) ve vida (p × ω + h·ω, ω), ω = yön.

    p = ω × Δt/|ω|², h = ω·Δt/|ω|² tanımının tersi: Δt = h·ω + p × ω (p ⊥ ω).
    """
    sutun = [
        np.concatenate([np.asarray(u, float), np.zeros(3)]) for u in np.asarray(s.oteleme).reshape(-1, 3)
    ]
    for v in s.vida:
        w = np.asarray(v.yon, float)
        p = np.asarray(v.nokta, float)
        sutun.append(np.concatenate([v.hatve * w + np.cross(p, w), w]))
    return np.array(sutun).T if sutun else np.zeros((6, 0))


def _alt_uzay_farki(A: np.ndarray, B: np.ndarray) -> float:
    """En büyük asal açının sinüsü: ‖(I − Q_B Q_Bᵀ) Q_A‖₂ (boyutlar eşit olmalı)."""
    assert A.shape == B.shape
    QA, _ = np.linalg.qr(A)
    QB, _ = np.linalg.qr(B)
    return float(np.linalg.norm(QA - QB @ (QB.T @ QA), 2))


def _eksene_uzaklik(p, q, a) -> float:
    d = np.asarray(p, float) - np.asarray(q, float)
    return float(np.linalg.norm(d - np.dot(d, a) * a))


def test_part_freedom_fixed_is_zero():
    """K10: sabit bileşenin serbestliği 0."""
    s = serbestlik(mo.iki_bilesen("es_eksen"), "taban")
    assert s.sayi == 0 and np.asarray(s.oteleme).size == 0 and s.vida == []


def test_part_freedom_unconstrained():
    """K10: kısıtsız 6: 3 öteleme (Tx Ty Tz), 3 vida h = 0; sıfır uzayı R⁶."""
    s = serbestlik(mo.iki_bilesen("yok"), "parca")
    assert s.sayi == 6
    U = np.asarray(s.oteleme, float).reshape(-1, 3)
    assert U.shape == (3, 3)
    np.testing.assert_allclose(U @ U.T, np.eye(3), atol=1e-12)  # ortonormal
    assert len(s.vida) == 3
    for v in s.vida:
        assert abs(v.hatve) <= 1e-9
        assert np.linalg.norm(v.yon) == pytest.approx(1.0, abs=1e-12)
    assert {"Tx", "Ty", "Tz"} <= set(s.etiketler) and len(s.etiketler) == 6
    assert _alt_uzay_farki(_twist_tabani(s), np.eye(6)) <= 1e-9


def test_part_freedom_concentric():
    """K10: CONCENTRIC 2: eksen boyunca öteleme + eksen üstünde h = 0 vida;
    sıfır uzayı analitik uzayla ≤ 1e-9."""
    s = serbestlik(mo.iki_bilesen("es_eksen"), "parca")
    q = np.array(mo.Q)
    assert s.sayi == 2
    U = np.asarray(s.oteleme, float).reshape(-1, 3)
    assert U.shape == (1, 3)
    assert np.linalg.norm(np.cross(U[0], EZ)) <= 1e-9
    assert len(s.vida) == 1
    v = s.vida[0]
    assert np.linalg.norm(np.cross(v.yon, EZ)) <= 1e-9
    assert _eksene_uzaklik(v.nokta, q, EZ) <= 1e-9
    assert abs(v.hatve) <= 1e-9
    assert sorted(s.etiketler) == ["Rz", "Tz"]
    # Analitik: (e_z, 0) ve q ekseni etrafında dönme (q × e_z, e_z)
    N = np.array([[0, 0, 1, 0, 0, 0], [*np.cross(q, EZ), *EZ]], dtype=float).T
    assert _alt_uzay_farki(_twist_tabani(s), N) <= 1e-9


def test_part_freedom_concentric_plane():
    """K10: CONCENTRIC + düzlem 1: eksen üstünde saf dönme (|yön × a| ≤ 1e-9, p eksene ≤ 1e-9 mm, h = 0)."""
    s = serbestlik(mo.iki_bilesen("es_eksen+duzlem"), "parca")
    assert s.sayi == 1
    assert np.asarray(s.oteleme).size == 0
    assert len(s.vida) == 1
    v = s.vida[0]
    assert np.linalg.norm(np.cross(v.yon, EZ)) <= 1e-9
    assert _eksene_uzaklik(v.nokta, mo.Q, EZ) <= 1e-9
    assert abs(v.hatve) <= 1e-9
    assert s.etiketler == ["Rz"]


def test_part_freedom_three_planes():
    """K10: üç düzlem çifti (normaller x, y, z) 0."""
    s = serbestlik(mo.iki_bilesen("uc_duzlem"), "parca")
    assert s.sayi == 0 and s.vida == [] and s.etiketler == []


def test_part_freedom_matches_solver_dof():
    """K10: iki bileşenli montajda (taban sabit) serbestlik sayısı SPEC 08 `dof` ile aynı."""
    for k in ("yok", "es_eksen", "es_eksen+duzlem", "uc_duzlem"):
        asm = mo.iki_bilesen(k)
        assert serbestlik(asm, "parca").sayi == dof(asm), k


def test_label_tolerance_constant():
    assert ETIKET_TOL == 1e-9
    assert SIMETRI_ACI == 37.0
    assert SIMETRI_TOL == 1e-6


def test_part_freedom_example():
    """K10, örnek: tam montajda rulman 1, mil 1, pim 1 (eş eksen + taban düzlemi: eksen etrafında dönme)."""
    tanim = _ornek()
    asm = _cozulmus(tanim)
    s = tanim.sira
    assert len(s) == 7
    for yol in s[1:]:
        f = serbestlik(asm, yol)
        assert f.sayi == 1, yol
        assert len(f.vida) == 1 and abs(f.vida[0].hatve) <= 1e-9, yol
        assert np.linalg.norm(np.cross(f.vida[0].yon, EZ)) <= 1e-9, yol
    assert serbestlik(asm, s[0]).sayi == 0


# ---------------------------------------------------------------- K8: ağaç, BOM, kütle


def test_montaj_is_flatten_plus_mates():
    """`montaj()` = flatten(agac, sabit) + kısıtlar (çözülmemiş)."""
    _occt()
    tanim = mo.deney()
    asm = montaj(tanim)
    bek = _beklenen_montaj(tanim)
    assert [c.name for c in asm.components] == [c.name for c in bek.components]
    for c, b in zip(asm.components, bek.components, strict=True):
        assert c == b
    assert asm.mates == bek.mates


@pytest.mark.parametrize("hangi", ["deney", "ornek"])
def test_tree_bom_mass(hangi):
    """K8: agac == Node.to_dict(); bom assy.bom.bom() ile aynı sıra ve değer; kütle toplam ve merkez (1e-12,
    çözülmüş konumlarla); bilesenler flatten sırasıyla, T'ler solve sonucuyla birebir; parça hacimleri."""
    if hangi == "deney":
        _occt()
        tanim = mo.deney()
    else:
        tanim = _ornek()
    J = _json_tur(montaj_json(tanim))
    assert J["sema"] == 1 and J["ad"] == tanim.ad
    assert J["agac"] == _json_tur(tanim.agac.to_dict())
    m = _birim_kutleler(tanim)
    assert J["bom"] == _json_tur([dataclasses.asdict(b) for b in bom(tanim.agac, m)])
    assert J["kutle"]["toplam"] == pytest.approx(total_mass(tanim.agac, m), rel=1e-12)
    asm = _cozulmus(tanim)
    merkez = mass_center(apply(tanim.agac, asm), tanim.parcalar, m)
    np.testing.assert_allclose(J["kutle"]["merkez"], merkez, rtol=0, atol=1e-12)
    B = J["bilesenler"]
    assert [b["yol"] for b in B] == [c.name for c in asm.components]
    for b, c in zip(B, asm.components, strict=True):
        assert b["parca"] == c.part
        assert b["sabit"] == c.fixed
        np.testing.assert_allclose(_T(b["T"]), c.T, rtol=0, atol=1e-12)
    P = {p["kimlik"]: p for p in J["parcalar"]}
    assert set(P) == set(tanim.parcalar)
    for k, part in tanim.parcalar.items():
        assert P[k]["malzeme"] == tanim.malzemeler[k][0]
        assert P[k]["rho"] == tanim.malzemeler[k][1]
        assert P[k]["hacim"] == pytest.approx(part.volume, rel=1e-12)
        kaynak = tanim.kaynaklar.get(k)
        assert P[k]["kaynak"] == (None if kaynak is None else {"is": kaynak[0], "tur": kaynak[1]})


def test_example_tree_and_sources():
    """Örnek: 7 yaprak (plaka, rulman, mil, 4 pim), mil kaynağı torna işi; bağ L ∈ [5, 30] → mil."""
    tanim = _ornek()
    yapraklar = [y for y, n, _ in walk(tanim.agac) if n.part is not None]
    assert sorted(yapraklar) == sorted(tanim.sira)
    mil = _kimlik(tanim, tanim.sira[2])
    assert tanim.kaynaklar[mil] == ("kademeli_mil", "torna")
    assert tanim.sabit == (tanim.sira[0],)
    pim = {_kimlik(tanim, y) for y in tanim.sira[3:]}
    assert len(pim) == 1  # dört pim aynı parça: BOM'da adet 4
    J = montaj_json(tanim)
    adet = {b["item"]: b["qty"] for b in J["bom"]}
    assert adet[pim.pop()] == 4
    (bag,) = J["baglar"]
    assert bag["parametre"] == {"is": "kademeli_mil", "anahtar": "L", "deger": 20.0, "min": 5.0, "max": 30.0}
    assert bag["parcalar"] == [mil]


def test_example_part_volumes():
    """Örnek parçaların hacimleri SPEC 25 ölçülerinden (kapalı form, rel 1e-6)."""
    tanim = _ornek()
    V = {y: tanim.parcalar[_kimlik(tanim, y)].volume for y in tanim.sira[:4]}
    plaka = 120 * 80 * 30 - math.pi / 4 * 40.02**2 * 10 - 4 * math.pi / 4 * 8.02**2 * 20
    rulman = math.pi / 4 * (40**2 - 24.02**2) * 10
    pim = math.pi / 4 * 8**2 * 24
    assert V[tanim.sira[0]] == pytest.approx(plaka, rel=1e-6)
    assert V[tanim.sira[1]] == pytest.approx(rulman, rel=1e-6)
    assert V[tanim.sira[3]] == pytest.approx(pim, rel=1e-6)
    L = 20.0
    mil = math.pi / 4 * (24**2 * L + 35**2 * 30 + 44**2 * 30)
    assert V[tanim.sira[2]] >= mil * (1 - 1e-6)  # Ø50 kalan kısım da eklenir


# ---------------------------------------------------------------- K9: montaj sırası


def _adim_kontrol(tanim):
    A = sira_adimlari(tanim)
    assert [a["i"] for a in A] == list(range(len(tanim.sira)))
    assert [a["yol"] for a in A] == list(tanim.sira)
    for i, a in enumerate(A):
        yerlesmis = list(tanim.sira[: i + 1])
        alt = _alt_montaj(tanim, yerlesmis)
        r = solve(alt)
        assert set(a["T_sonra"]) == set(yerlesmis)
        for yol in yerlesmis:
            np.testing.assert_allclose(
                _T(a["T_sonra"][yol]), r.T[yol], rtol=0, atol=1e-12, err_msg=f"adım {i} {yol}"
            )
        assert a["dof_toplam"] == dof(alt)
        assert set(a["serbestlik"]) >= {a["yol"]}
    return A


def test_sequence_steps_small():
    """K9: her adımda T_sonra yerleşmiş bileşenler ve
    iki ucu yerleşmiş kısıtlardan kurulan alt montajın solve'u."""
    _occt()
    A = _adim_kontrol(mo.deney())
    assert A[0]["dof_toplam"] == 0
    assert A[1]["dof_toplam"] == 1  # eş eksen + düzlem: eksen etrafında dönme


def test_sequence_steps_example():
    """K9, örnek: 7 adım; her adım alt montajın solve sonucu."""
    _adim_kontrol(_ornek())


@pytest.mark.parametrize(
    ("sira", "neden"),
    [
        (["grup/ust", "taban"], "ilk adım sabit değil"),
        (["taban", "yok"], "bilinmeyen yol"),
        (["taban", "grup/ust", "grup/ust"], "yinelenen yol"),
        (["taban"], "yaprak sırada yok"),
        (["taban", "grup"], "yaprak olmayan yol"),
    ],
)
def test_sequence_invalid(sira, neden):
    """K9: geçersiz sıra → AssyError."""
    _occt()
    with pytest.raises(AssyError):
        sira_adimlari(mo.deney(sira=sira))


# ---------------------------------------------------------------- K11: yaklaşma ve patlatma


def _kosegen(part) -> float:
    lo, hi = part.bbox
    return float(np.linalg.norm(np.asarray(hi) - np.asarray(lo)))


@pytest.mark.parametrize(
    ("ust", "yer", "kisit", "a"),
    [
        ("blok", "ust", "es_eksen+duzlem", (0, 0, 1)),  # eş eksen yönü
        ("blok", "alt", "es_eksen+duzlem", (0, 0, -1)),  # işaret kuralı: karşı tarafta → −a
        ("blok", "yan", "duzlem", (1, 0, 0)),  # CONCENTRIC yok → düzlem normali
        ("blok", "ust", "yok", (0, 0, 1)),  # kısıt yok → +Z
        ("tapa", "ust", "es_eksen+duzlem", (0, 0, 1)),
    ],
)
def test_approach(ust, yer, kisit, a):
    """K11: yaklaşma yönü kuralı ve mesafe = bileşenin sınır kutusu köşegeni."""
    _occt()
    tanim = mo.deney(ust=ust, yer=yer, kisit=kisit)
    asm = _beklenen_montaj(tanim)
    yon, mesafe = yaklasma(tanim, asm, "grup/ust", ["taban"])
    np.testing.assert_allclose(yon, a, rtol=0, atol=1e-12)
    assert mesafe == pytest.approx(_kosegen(tanim.parcalar[ust]), rel=1e-12)


def test_approach_diagonal_closed_form():
    """K11: blok 20 × 10 × 5 → köşegen √525."""
    _occt()
    tanim = mo.deney()
    _, mesafe = yaklasma(tanim, _beklenen_montaj(tanim), "grup/ust", ["taban"])
    assert mesafe == pytest.approx(math.sqrt(20**2 + 10**2 + 5**2), rel=1e-9)


def _patlatma_kontrol(A, tanim):
    for a in A:
        yol = a["yol"]
        y = np.asarray(a["yaklasma"], float)
        assert np.linalg.norm(y) == pytest.approx(1.0, abs=1e-12)
        T1, T0 = _T(a["T_sonra"][yol]), _T(a["T_once"][yol])
        np.testing.assert_allclose(T0[:3, :3], T1[:3, :3], rtol=0, atol=1e-12)
        np.testing.assert_allclose(T0[:3, 3], T1[:3, 3] + a["mesafe"] * y, rtol=0, atol=1e-12)
        np.testing.assert_array_equal(T0[3], [0, 0, 0, 1])
        assert a["mesafe"] == pytest.approx(_kosegen(tanim.parcalar[_kimlik(tanim, yol)]), rel=1e-12)


def test_approach_explode_small():
    """K11: T_once = T_sonra + mesafe·a ötelemesi (dönme aynı), 1e-12."""
    _occt()
    tanim = mo.deney()
    _patlatma_kontrol(sira_adimlari(tanim), tanim)


def test_approach_example():
    """K11, örnek: rulman ve mil +Z'den; T_once / T_sonra kuralı her adımda."""
    tanim = _ornek()
    A = sira_adimlari(tanim)
    for i in (1, 2):
        np.testing.assert_allclose(A[i]["yaklasma"], [0, 0, 1], rtol=0, atol=1e-12)
    _patlatma_kontrol(A, tanim)


# ---------------------------------------------------------------- K12: girişim


def test_interference_example():
    """K12: L = 20'de tek girişim çifti (mil, plaka), hacim π·144·10 (rel 1e-6), SPEC 09 değeriyle aynı;
    temas eden rulman tabanı ve omuz girişim sayılmaz."""
    gm = _girisim_modulu()
    tanim = _ornek(20.0)
    G = girisimler(tanim)
    assert len(G) == 1
    g = G[0]
    plaka, mil = tanim.sira[0], tanim.sira[2]
    assert {g["a"], g["b"]} == {plaka, mil}
    assert g["hacim"] == pytest.approx(math.pi * 144 * 10, rel=1e-6)
    agac = apply(tanim.agac, _cozulmus(tanim))
    parcalar = {k: v for k, v in tanim.parcalar.items()}
    spec09 = [c for c in gm.check(agac, parcalar) if c.kind == gm.ClashKind.GIRISIM]
    assert len(spec09) == 1 and {spec09[0].a, spec09[0].b} == {plaka, mil}
    assert g["hacim"] == pytest.approx(spec09[0].volume, rel=1e-12)
    assert g["bosluk"] == pytest.approx(spec09[0].distance, abs=1e-12)
    assert g["ag"] == f"/api/montaj/{tanim.ad}/ag/girisim/{g.get('i', 0)}"


def test_interference_clear_at_L10():
    """K12: L = 10'da girişim listesi boş (mil ucu cep tabanına değer)."""
    _girisim_modulu()
    assert girisimler(_ornek(10.0)) == []


@pytest.mark.slow
@pytest.mark.parametrize("L", [15.0, 25.0])
def test_interference_volume_formula(L):
    """K12: V = π·12²·(L − 10)."""
    _girisim_modulu()
    (g,) = girisimler(_ornek(L))
    assert g["hacim"] == pytest.approx(math.pi * 144 * (L - 10), rel=1e-6)


def test_interference_mesh():
    """K12: kesişim ağının kapalı hacmi girişim hacmiyle rel 1e-2; ağ dünya koordinatında (z ∈ [−20, −10])."""
    _girisim_modulu()
    tanim = _ornek(20.0)
    (g,) = girisimler(tanim)
    V, T = _ag_oku(girisim_agi(tanim, 0))
    assert _mesh_volume(V, T) == pytest.approx(g["hacim"], rel=1e-2)
    assert V[:, 2].min() == pytest.approx(-20.0, abs=0.02)
    assert V[:, 2].max() == pytest.approx(-10.0, abs=0.02)
    V2, T2 = ag_coz(girisim_agi(tanim, 0))
    np.testing.assert_array_equal(V2, V.astype(np.float32))
    np.testing.assert_array_equal(np.asarray(T2, dtype=np.int64), T)


def test_interference_mesh_unknown_index():
    """Bilinmeyen girişim indeksi sessizce boş ağ vermez."""
    _girisim_modulu()
    with pytest.raises((IndexError, KeyError, ValueError)):
        girisim_agi(_ornek(10.0), 0)


# ---------------------------------------------------------------- K13: serbestlik kontrolü


def _serbestlik_kontrolleri(tanim) -> list[dict]:
    K = [k for k in kontroller(tanim) if k["kimlik"].startswith("serbestlik")]
    assert K, "serbestlik kontrolü yok"
    for k in K:
        assert k["durum"] in ("tamam", "uyari", "hata")
        assert k["spec"]
    return K


def test_freedom_check_example():
    """K13: örnekte rulman, mil ve pimler (dönel simetrik, yalnız eksen etrafında dönme) → tamam."""
    tanim = _ornek()
    assert all(k["durum"] == "tamam" for k in _serbestlik_kontrolleri(tanim))
    kimlikler = {k["kimlik"] for k in kontroller(tanim)}
    assert {"kisit_artigi", "girisim", "kutle"} <= kimlikler


def test_freedom_check_pin_without_plane():
    """K13: pimin düzlem kısıtı silinince uyari ("eksik kısıt: Tz")."""
    tanim = _ornek()
    pim = tanim.sira[3]
    once = len(tanim.kisitlar)
    tanim.kisitlar = [
        m
        for m in tanim.kisitlar
        if not (m.kind is MateKind.COINCIDENT and pim in (m.a.component, m.b.component))
    ]
    assert len(tanim.kisitlar) == once - 1
    K = _serbestlik_kontrolleri(tanim)
    uyari = [k for k in K if k["durum"] == "uyari"]
    assert uyari
    assert any("eksik kısıt" in k["aciklama"] and "Tz" in k["aciklama"] for k in uyari)


def test_freedom_check_non_symmetric_block():
    """K13: dönel simetrik olmayan blok tek CONCENTRIC + düzlemle bağlanınca uyari;
    aynı bağla silindir tamam."""
    _spec09()
    K = _serbestlik_kontrolleri(mo.deney(ust="blok"))
    assert any(k["durum"] == "uyari" and "eksik kısıt" in k["aciklama"] for k in K)
    K = _serbestlik_kontrolleri(mo.deney(ust="tapa"))
    assert all(k["durum"] == "tamam" for k in K)


def test_rotational_symmetry():
    """K13: 37° dönel simetri sınaması (SPEC 09 common)."""
    _spec09()
    from geometry.features import block, cylinder

    sil = cylinder(5.0, 8.0)
    assert donel_simetrik(sil, EZ, np.zeros(3))
    assert not donel_simetrik(sil, EZ, np.array([1.0, 0.0, 0.0]))  # eksen dışı
    kare = block(10.0, 10.0, 4.0)  # 90° simetrik ama 37° değil
    assert not donel_simetrik(kare, EZ, np.array([5.0, 5.0, 0.0]))
    assert not donel_simetrik(sil, np.array([1.0, 0.0, 0.0]), np.array([0.0, 0.0, 4.0]))


# ---------------------------------------------------------------- K14: parça ağları


@pytest.mark.parametrize("hangi", ["deney", "ornek"])
def test_meshes(hangi):
    """K14: her parçanın ikili ağının kapalı hacmi Part.volume ile rel 1e-2; köşeler parçanın kendi
    koordinatında (sınır kutusu Part.bbox, 0.02 mm içinde); bayt uzunlukları başlıktaki nv, nt ile tutarlı."""
    if hangi == "deney":
        _occt()
        tanim = mo.deney()
    else:
        tanim = _ornek()
    for kimlik, part in tanim.parcalar.items():
        veri = parca_agi(tanim, kimlik)
        V, T = _ag_oku(veri)
        assert _mesh_volume(V, T) == pytest.approx(part.volume, rel=1e-2), kimlik
        lo, hi = part.bbox
        np.testing.assert_allclose(V.min(axis=0), lo, atol=0.02, err_msg=kimlik)
        np.testing.assert_allclose(V.max(axis=0), hi, atol=0.02, err_msg=kimlik)
        V2, T2 = ag_coz(veri)
        assert V2.dtype == np.float32 and V2.shape == V.shape
        np.testing.assert_array_equal(np.asarray(T2, dtype=np.int64), T)


def test_mesh_unknown_part():
    _occt()
    with pytest.raises((KeyError, AssyError)):
        parca_agi(mo.deney(), "yok")
