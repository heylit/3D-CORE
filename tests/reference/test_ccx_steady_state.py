"""SPEC 68c K5 — CalculiX `*STEADY STATE DYNAMICS` çapraz kontrolü (ccx yoksa atlanır).

Ürün yazıcısı `fileio.calculix.to_inp_steady_state` çıktısı ccx'te çözülür. ccx keyfi frekans listesi
almaz (f_min, f_max, n_points, bias; aralığı öz frekanslarda böler), bu yüzden karşılaştırma ccx'in
`.dat` dosyasına yazdığı frekanslarda yapılır. ccx 2.21 her frekans için iki `displacements` bloğu
yazar: önce gerçel, sonra sanal kısım (aynı "time" = frekans değeri).

Önemli gözlem (ccx 2.21 ile denendi): ccx'in C3D4 kütle matrisi tek integrasyon noktalıdır,
M_e = ρV/16 · (1 1ᵀ ⊗ I₃); bizim tutarlı kütlemiz (SPEC 45) ρV/20 · (1 + δ_ab) ⊗ I₃. Bu konsolda
ccx f₁ = 1325.02 Hz, bizimki 1323.67 Hz. Bu yüzden ccx sonucu burada testin kendi yoğun modal
toplamıyla (aynı K, ccx'in kütlesi, aynı ζ ve mod sayısı, kalıntı yok) 1e-4 içinde karşılaştırılır:
yazıcının adımı, yükleri, sönümü ve mod sayısını doğru yazdığını gösterir. Çözücümüzün ccx ile
doğrudan 1e-4 karşılaştırması bu kütle farkı yüzünden mümkün değil (koordinatöre soruldu).
Kaynak: CalculiX CrunchiX User's Manual 2.21 (*FREQUENCY, *STEADY STATE DYNAMICS, *MODAL DAMPING).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import numpy as np
import pytest
import scipy.linalg as sla

from core.assembly import assemble_F, assemble_K
from core.model import BC, Load, Material, Model, ModelError
from fileio.calculix import to_inp_steady_state
from tests.benchmarks.tet_ag import kutu_agi, yuz_dugumleri
from tests.reference.calculix import CCX

needs_ccx = pytest.mark.skipif(CCX is None, reason="CalculiX (ccx) kurulu değil")
E, NU, RHO = 210_000.0, 0.3, 7.85e-9
ZETA, N_MODES = 0.02, 20
_NUM = r"[-+]?\d+\.\d+E[-+]\d+"


def konsol(rho: float = RHO) -> Model:
    """K3 konsolu: Kuhn tet4 100 × 10 × 10, 10 × 2 × 2; x = 0 ankastre, uç yüz merkezinde Fz, Fy."""
    m = kutu_agi(100.0, 10.0, 10.0, 10, 2, 2, Material("celik", E, NU, rho), name="ssd_konsol")
    for n in yuz_dugumleri(m, 0, 0.0):
        m.bcs.extend(BC(n, d) for d in ("ux", "uy", "uz"))
    uc = yuz_dugumleri(m, 0, 100.0)
    m.loads = [Load(uc[4], "uz", 10.0), Load(uc[4], "uy", 4.0)]
    return m


def parse_ssd(text: str) -> list[tuple[float, dict[int, np.ndarray]]]:
    """`.dat` → [(f, {düğüm: (ux, uy, uz) karmaşık})]; bloklar (gerçel, sanal) çiftleri halinde."""
    bloklar: list[tuple[float, dict[int, list[float]]]] = []
    blok = None
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith("displacements"):
            t = float(re.findall(_NUM, line, flags=re.IGNORECASE)[-1])
            blok = {}
            bloklar.append((t, blok))
            continue
        head = line.split()
        if not head or not head[0].isdigit():
            if low and blok is not None and not head[0].isdigit():
                blok = None
            continue
        if blok is not None:
            blok[int(head[0])] = [float(v) for v in re.findall(_NUM, line, flags=re.IGNORECASE)[:3]]
    assert len(bloklar) % 2 == 0, "her frekans için gerçel + sanal blok beklenir"
    out = []
    for (t_re, b_re), (t_im, b_im) in zip(bloklar[::2], bloklar[1::2], strict=True):
        assert t_re == t_im
        out.append((t_re, {n: np.array(b_re[n]) + 1j * np.array(b_im[n]) for n in b_re}))
    return out


def ccx_mass(model: Model) -> np.ndarray:
    """ccx C3D4 kütlesi (tek integrasyon noktası): ρV/16 · (1 1ᵀ ⊗ I₃), yoğun."""
    M = np.zeros((model.n_dof, model.n_dof))
    for e in model.elements:
        X = np.array([model.node(n).xyz for n in e.nodes])
        rhoV = model.material(e.material).rho * abs(np.linalg.det(X[1:] - X[0])) / 6.0
        d = np.array([model.dof_index(n, a) for n in e.nodes for a in ("ux", "uy", "uz")])
        M[np.ix_(d, d)] += rhoV * np.kron(np.ones((4, 4)) / 16.0, np.eye(3))
    return M


def ref_modal(model: Model, M: np.ndarray, fs: np.ndarray, zeta: float, n_modes: int) -> np.ndarray:
    """Testin kendi modal toplamı: U = Σ_{r≤m} φ_r(φ_rᵀF)/(ω_r² − ω² + 2iζω_rω), φᵀMφ = 1."""
    tut = {model.dof_index(b.node, b.dof) for b in model.bcs}
    s = np.array([i for i in range(model.n_dof) if i not in tut])
    K = assemble_K(model).toarray()[np.ix_(s, s)]
    w2, P = sla.eigh(K, M[np.ix_(s, s)], subset_by_index=[0, n_modes - 1])
    w = np.sqrt(w2)
    q = P.T @ assemble_F(model)[s]
    U = np.zeros((len(fs), model.n_dof), dtype=complex)
    for k, fk in enumerate(fs):
        W = 2 * np.pi * fk
        U[k, s] = P @ (q / (w2 - W * W + 2j * zeta * w * W))
    return U


def test_k5_yazici_girdi_metni():
    txt = to_inp_steady_state(konsol(), 200.0, 3000.0, 5, zeta=ZETA, n_modes=N_MODES).upper()
    for anahtar in (
        "*DENSITY",
        "*FREQUENCY",
        "*STEADY STATE DYNAMICS",
        "*MODAL DAMPING",
        "*CLOAD",
        "*BOUNDARY",
    ):
        assert anahtar in txt, anahtar
    assert txt.index("*FREQUENCY") < txt.index("*STEADY STATE DYNAMICS")


@pytest.mark.parametrize(
    "kw",
    [
        pytest.param({"f_min": -1.0}, id="f_min<0"),
        pytest.param({"f_max": 100.0}, id="f_max<f_min"),
        pytest.param({"n_points": 0}, id="n_points=0"),
        pytest.param({"zeta": 0.0}, id="zeta=0"),
        pytest.param({"zeta": 1.0}, id="zeta=1"),
        pytest.param({"n_modes": 0}, id="n_modes=0"),
    ],
)
def test_k5_yazici_hatali(kw):
    p = {"f_min": 200.0, "f_max": 3000.0, "n_points": 5, "zeta": ZETA, "n_modes": N_MODES}
    p.update(kw)
    with pytest.raises(ModelError):
        to_inp_steady_state(konsol(), p.pop("f_min"), p.pop("f_max"), p.pop("n_points"), **p)


@pytest.mark.parametrize("rho", [0.0, -1e-9])
def test_k5_yazici_yogunluk(rho):
    with pytest.raises(ModelError):
        to_inp_steady_state(konsol(rho), 200.0, 3000.0, 5, zeta=ZETA, n_modes=N_MODES)


@needs_ccx
def test_k5_ccx_steady_state(tmp_path: Path):
    m = konsol()
    (tmp_path / "ssd.inp").write_text(to_inp_steady_state(m, 200.0, 9000.0, 4, zeta=ZETA, n_modes=N_MODES))
    p = subprocess.run(
        [CCX, "-i", "ssd"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=300,
        stdin=subprocess.DEVNULL,
    )
    dat = tmp_path / "ssd.dat"
    assert p.returncode == 0 and dat.exists() and "error" not in p.stdout.lower(), p.stdout[-3000:]
    sonuc = parse_ssd(dat.read_text())
    assert len(sonuc) >= 10
    fs = np.array([f for f, _ in sonuc])
    assert fs.min() == pytest.approx(200.0, rel=1e-6) and fs.max() == pytest.approx(9000.0, rel=1e-6)
    U = ref_modal(m, ccx_mass(m), fs, ZETA, N_MODES)
    uc = yuz_dugumleri(m, 0, 100.0)[4]
    for k, (_, u) in enumerate(sonuc):
        for dof in ("uy", "uz"):
            beklenen = abs(U[k, m.dof_index(uc, dof)])
            assert abs(u[uc][("ux", "uy", "uz").index(dof)]) == pytest.approx(beklenen, rel=1e-4), (
                fs[k],
                dof,
            )
