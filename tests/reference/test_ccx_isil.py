"""
SPEC 56 — kararlı hal ısıl çözüm ↔ CalculiX `DC3D4` çapraz kontrolü (K10).

K6 küpü (20³, x = 0 ve x = 20'de T = 0, k = 15, Q = 1) Kuhn ağında çözülür. Üretim, düğüm ısısı olarak
(tutarlı yük `Q V / 4` her köşeye; bu dosyada elle hesaplanır) `*CFLUX` ile ccx'e verilir. ccx `NT` sonuçları
bizim `T` ile göreli 1e-6 içinde eşit olmalı (`.dat` 7 anlamlı basamak). ccx `RFL` (tutulu düğümdeki ısı)
`K T`'dir; bizim tepki ısısı `R = K T − F`, karşılaştırma `R + F` ile yapılır.

İki yazıcı denenir:
- bu dosyanın kendi küçük DC3D4 yazıcısı (ccx eşlemesinin ve bizim çözücünün bağımsız kontrolü),
- ürün yazıcısı `fileio.calculix.to_inp_thermal`.
ccx yoksa ccx testleri atlanır; `.inp` biçim testleri her ortamda çalışır.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import numpy as np
import pytest

import mesh
from core.isil import Temperature, solve_thermal
from core.model import Material, Model
from tests.benchmarks.tet_ag import kutu_agi
from tests.reference.calculix import CCX, num

needs_ccx = pytest.mark.skipif(CCX is None, reason="CalculiX (ccx) kurulu değil")

L6, K6_k, Q6 = 20.0, 15.0, 1.0
_NUM = r"[-+]?\d+\.\d+E[-+]\d+"


def kup(n: int = 2, iki_malzeme: bool = False) -> Model:
    m = kutu_agi(L6, L6, L6, n, n, n, Material("celik", 210_000.0, 0.3), kaydirma=0.15, tohum=8)
    if iki_malzeme:
        m.materials.append(Material("al", 70_000.0, 0.33))
        for e in m.elements[::3]:
            e.material = "al"
    return m


def k_degeri(iki_malzeme: bool):
    return {"celik": K6_k, "al": 40.0} if iki_malzeme else K6_k


def sinir(m: Model) -> list[Temperature]:
    ids = mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (1, 0, 0)))
    ids += mesh.select_nodes(m, mesh.on_plane((L6, 0, 0), (1, 0, 0)))
    return [Temperature(n, 0.0) for n in ids]


def hacim(m: Model, e) -> float:
    X = np.array([m.node(i).xyz for i in e.nodes])
    return abs(np.linalg.det(X[1:] - X[0])) / 6.0


def dugum_isisi(m: Model, Q: float) -> dict[int, float]:
    """Tutarlı üretim yükü fQ = Q V / 4 her köşeye (doğrusal tetrahedron, SPEC 56 Teori)."""
    F: dict[int, float] = {}
    for e in m.elements:
        for i in e.nodes:
            F[i] = F.get(i, 0.0) + Q * hacim(m, e) / 4.0
    return F


def dc3d4_sira(m: Model, nodes: list[int]) -> list[int]:
    X = [m.node(i).xyz for i in nodes]
    det = float(np.dot(np.cross(X[1] - X[0], X[2] - X[0]), X[3] - X[0]))
    return list(nodes) if det > 0 else [nodes[0], nodes[2], nodes[1], nodes[3]]


def kendi_inp(m: Model, k, temps: list[Temperature], heat: dict[int, float]) -> str:
    """Bu testin bağımsız DC3D4 yazıcısı (CalculiX 2.21: *HEAT TRANSFER, *CONDUCTIVITY, *CFLUX, NT)."""
    kmap = k if isinstance(k, dict) else {mat.name: k for mat in m.materials}
    out = ["*HEADING", "SPEC 56 capraz kontrol", "*NODE, NSET=NALL"]
    out += [f"{n.id}, {num(n.x)}, {num(n.y)}, {num(n.z)}" for n in m.nodes]
    gruplar: dict[str, list] = {}
    for e in m.elements:
        gruplar.setdefault(e.material, []).append(e)
    for g, (mat, elems) in enumerate(gruplar.items(), start=1):
        out.append(f"*ELEMENT, TYPE=DC3D4, ELSET=G{g}")
        out += [f"{e.id}, " + ", ".join(map(str, dc3d4_sira(m, e.nodes))) for e in elems]
        out += [f"*MATERIAL, NAME=M{g}", "*CONDUCTIVITY", num(kmap[mat])]
        out.append(f"*SOLID SECTION, ELSET=G{g}, MATERIAL=M{g}")
    out += ["*STEP", "*HEAT TRANSFER, STEADY STATE", "*BOUNDARY"]
    out += [f"{t.node}, 11, 11, {num(t.T)}" for t in temps]
    out.append("*CFLUX")
    out += [f"{nid}, 11, {num(v)}" for nid, v in sorted(heat.items())]
    out += ["*NODE PRINT, NSET=NALL", "NT, RFL", "*END STEP"]
    return "\n".join(out) + "\n"


def ccx_coz(inp: str, workdir: Path) -> tuple[dict[int, float], dict[int, float]]:
    """ccx'i çalıştırır; (.dat) → (NT, RFL) sözlükleri."""
    (workdir / "isil.inp").write_text(inp)
    p = subprocess.run(
        [CCX, "-i", "isil"],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=120,
        stdin=subprocess.DEVNULL,
    )
    dat = workdir / "isil.dat"
    if p.returncode != 0 or not dat.exists() or "error" in p.stdout.lower():
        raise RuntimeError(f"ccx başarısız (kod {p.returncode}):\n{p.stdout[-3000:]}\n{p.stderr[-2000:]}")
    NT: dict[int, float] = {}
    RFL: dict[int, float] = {}
    blok = None
    for satir in dat.read_text().splitlines():
        low = satir.strip().lower()
        if low.startswith("temperatures"):
            blok = NT
            continue
        if low.startswith("heat generation"):
            blok = RFL
            continue
        if low and not low.split()[0].isdigit():
            blok = None
            continue
        sayilar = re.findall(_NUM, satir, flags=re.IGNORECASE)
        if blok is not None and low and sayilar:
            blok[int(low.split()[0])] = float(sayilar[0])
    if not NT:
        raise RuntimeError("ccx .dat dosyasında sıcaklık bloğu yok")
    return NT, RFL


def karsilastir(m: Model, r, NT: dict[int, float], RFL: dict[int, float], temps, heat: dict) -> None:
    T_ref = np.array([NT[n.id] for n in m.nodes])
    np.testing.assert_allclose(r.T, T_ref, rtol=1e-6, atol=1e-6 * np.max(np.abs(T_ref)))
    if RFL:
        tutulu = sorted({t.node for t in temps})
        indeks = {int(nid): i for i, nid in enumerate(r.node_ids)}
        # tanım farkı (mekanikteki RF = K u gibi): ccx RFL = K T, bizde R = K T − F
        R = np.array([r.R[indeks[n]] + heat.get(n, 0.0) for n in tutulu])
        R_ref = np.array([RFL[n] for n in tutulu])
        np.testing.assert_allclose(R, R_ref, rtol=0, atol=1e-5 * np.max(np.abs(R_ref)))


@needs_ccx
@pytest.mark.parametrize("iki_malzeme", [False, True], ids=["tek", "iki-malzeme"])
def test_own_dc3d4_writer_matches_solver(iki_malzeme, tmp_path):
    m = kup(iki_malzeme=iki_malzeme)
    k = k_degeri(iki_malzeme)
    temps = sinir(m)
    r = solve_thermal(m, k, temperatures=temps, Q=Q6)
    heat = dugum_isisi(m, Q6)
    NT, RFL = ccx_coz(kendi_inp(m, k, temps, heat), tmp_path)
    karsilastir(m, r, NT, RFL, temps, heat)


@needs_ccx
@pytest.mark.parametrize("iki_malzeme", [False, True], ids=["tek", "iki-malzeme"])
def test_fileio_thermal_inp_matches_solver(iki_malzeme, tmp_path):
    """K10: `fileio.calculix.to_inp_thermal` çıktısı ccx'te → NT = bizim T (göreli 1e-6)."""
    from fileio.calculix import to_inp_thermal

    m = kup(iki_malzeme=iki_malzeme)
    k = k_degeri(iki_malzeme)
    temps = sinir(m)
    r = solve_thermal(m, k, temperatures=temps, Q=Q6)
    heat = dugum_isisi(m, Q6)
    NT, _ = ccx_coz(to_inp_thermal(m, k, temps, heat), tmp_path)
    karsilastir(m, r, NT, {}, temps, heat)


# --- ccx'siz biçim denetimi -------------------------------------------------------------------


def _anahtarlar(inp: str) -> list[str]:
    satirlar = [s.strip() for s in inp.splitlines()]
    return [s.upper() for s in satirlar if s.startswith("*") and not s.startswith("**")]


def _blok(inp: str, anahtar: str) -> list[list[str]]:
    sonuc: list[list[str]] = []
    icinde = False
    for s in inp.splitlines():
        s = s.strip()
        if not s or s.startswith("**"):
            continue
        if s.startswith("*"):
            icinde = s[1:].split(",")[0].strip().upper() == anahtar
            continue
        if icinde:
            sonuc.append([a.strip() for a in s.split(",") if a.strip()])
    return sonuc


def test_fileio_thermal_inp_format():
    """DC3D4 pozitif hacimli, *HEAT TRANSFER STEADY STATE, *CONDUCTIVITY, *BOUNDARY 11, *CFLUX 11, NT çıktısı;
    her sayı alanı ≤ 20 karakter."""
    from fileio.calculix import to_inp_thermal

    m = kup(iki_malzeme=True)
    temps = sinir(m)
    heat = dugum_isisi(m, Q6)
    inp = to_inp_thermal(m, k_degeri(True), temps, heat)
    anahtarlar = _anahtarlar(inp)
    assert any("DC3D4" in a for a in anahtarlar if a.startswith("*ELEMENT"))
    assert any(a.startswith("*HEAT TRANSFER") and "STEADY STATE" in a for a in anahtarlar)
    assert sum(a.startswith("*CONDUCTIVITY") for a in anahtarlar) == 2
    iletkenlik = sorted(float(s[0]) for s in _blok(inp, "CONDUCTIVITY"))
    assert iletkenlik == pytest.approx([K6_k, 40.0], rel=5e-13)

    X = {n.id: n.xyz for n in m.nodes}
    elemanlar = _blok(inp, "ELEMENT")
    assert len(elemanlar) == len(m.elements)
    for s in elemanlar:
        P = [X[int(v)] for v in s[1:5]]
        assert np.dot(np.cross(P[1] - P[0], P[2] - P[0]), P[3] - P[0]) > 0

    sinir_satirlari = _blok(inp, "BOUNDARY")
    assert {int(s[0]) for s in sinir_satirlari} == {t.node for t in temps}
    assert all(s[1] == "11" and (len(s) < 3 or s[2] == "11") for s in sinir_satirlari)
    akilar = {int(s[0]): float(s[2]) for s in _blok(inp, "CFLUX")}
    assert all(s[1] == "11" for s in _blok(inp, "CFLUX"))
    assert set(akilar) == set(heat)
    for nid, v in heat.items():
        assert akilar[nid] == pytest.approx(v, rel=5e-13)
    assert any("NT" in [a.upper() for a in s] for s in _blok(inp, "NODE PRINT"))

    for s in inp.splitlines():
        if s.strip().startswith("*"):
            continue
        for alan in s.split(","):
            alan = alan.strip()
            try:
                float(alan)
            except ValueError:
                continue
            assert len(alan) <= 20, alan
