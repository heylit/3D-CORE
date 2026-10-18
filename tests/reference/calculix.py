"""
CalculiX (ccx) çapraz kontrol yardımcıları: `core.model.Model` -> .inp, ccx çalıştır, .dat oku.

Kendi çözücümüzden bağımsız bir FEM çözücüsüyle aynı modeli çözüp sonuçları karşılaştırmak için.
Sadece testlerde kullanılır ve `fileio.calculix`'ten hiçbir şey import etmez: SPEC 13'ün ürün
yazıcısı (`fileio.calculix.to_inp`) `solve_ccx(..., inp=...)` ile aynı ccx
çalıştırıcısı ve okuyucuyla denenir.

Eşleme (1B çubuk, `bar1d`): düğüm (x, 0, 0), eleman T3D2 (2 düğümlü 3B kafes), kesit
`*SOLID SECTION` alanı A, malzeme `*ELASTIC` E, ν. 1B modelde y ve z serbestlikleri bütün
düğümlerde tutulur, böylece ccx'teki problem bizimkiyle aynı olur.
Eşleme (3B katı, `tet4`, SPEC 13): eleman C3D4 (tek integrasyon noktalı doğrusal tetrahedron), kesit
`*SOLID SECTION` (alan satırı yok). C3D4 düğüm sırası pozitif hacimli olmalı:
(x2 − x1) × (x3 − x1) · (x4 − x1) > 0; negatifse 2. ve 3. düğüm yer değiştirir.
Sayılar `format(x, ".12e")` ile yazılır: ccx bir sayı alanının en çok 20 karakterini okur
(`repr(-7.850462293417722e-16)` 22 karakterdir ve reddedilir).
Birimler: N, mm, MPa (CalculiX birimsizdir, olduğu gibi aktarılır).
Kaynak: CalculiX CrunchiX User's Manual 2.21 (*NODE, *ELEMENT, *SOLID SECTION, *BOUNDARY, *CLOAD,
*NODE PRINT, *EL PRINT).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.model import DOF_NAMES, Model, ModelError

CCX = shutil.which("ccx") or shutil.which("ccx_2.21") or shutil.which("ccx2.21")


@dataclass
class CcxResult:
    u: dict[int, tuple[float, float, float]]  # düğüm id -> (ux, uy, uz) [mm]
    rf: dict[int, tuple[float, float, float]]  # düğüm id -> tepki (fx, fy, fz) [N]
    sxx: dict[int, float]  # eleman id -> eksenel gerilme [MPa]
    s: dict[int, tuple[float, ...]]  # eleman id -> (sxx, syy, szz, sxy, sxz, syz) [MPa], ilk int. noktası


def num(x: float) -> str:
    """ccx sayı alanı: 13 anlamlı basamak, en çok 20 karakter."""
    return format(float(x), ".12e")


def to_inp(model: Model) -> str:
    """Modeli CalculiX girdi dosyası metnine çevirir: 1B `bar1d` → T3D2, 3B `tet4` → C3D4."""
    model.validate()
    if model.dim == 3 and model.elements and all(e.type == "tet4" for e in model.elements):
        return _to_inp_tet4(model)
    if model.dim != 1 or any(e.type != "bar1d" for e in model.elements):
        raise ModelError("CalculiX yardımcısı sadece 1B 'bar1d' ve 3B 'tet4' modelini destekliyor")
    out = ["*HEADING", f"3D-CORE capraz kontrol: {model.name}", "*NODE, NSET=NALL"]
    out += [f"{n.id}, {num(n.x)}, 0.0, 0.0" for n in model.nodes]

    # Her (malzeme, kesit) çifti bir eleman kümesi
    groups: dict[tuple[str, str], list] = {}
    for e in model.elements:
        groups.setdefault((e.material, e.section), []).append(e)
    mat_names = {m.name: f"M{i}" for i, m in enumerate(model.materials, start=1)}
    for k, elems in enumerate(groups.values(), start=1):
        out.append(f"*ELEMENT, TYPE=T3D2, ELSET=G{k}")
        out += [f"{e.id}, {e.nodes[0]}, {e.nodes[1]}" for e in elems]
    out.append("*ELSET, ELSET=EALL")
    out += [f"G{k}" for k in range(1, len(groups) + 1)]
    for m in model.materials:
        out += [f"*MATERIAL, NAME={mat_names[m.name]}", "*ELASTIC", f"{num(m.E)}, {num(m.nu)}"]
    for k, (mat, sec) in enumerate(groups, start=1):
        out += [f"*SOLID SECTION, ELSET=G{k}, MATERIAL={mat_names[mat]}", num(model.section(sec).A)]

    out += ["*STEP", "*STATIC", "*BOUNDARY", "NALL, 2, 3"]  # 1B: uy = uz = 0
    for bc in model.bcs:
        k = DOF_NAMES[bc.dof] + 1
        out.append(f"{bc.node}, {k}, {k}, {num(bc.value)}")
    out += _cload(model)
    out += ["*NODE PRINT, NSET=NALL", "U, RF", "*EL PRINT, ELSET=EALL", "S", "*END STEP"]
    return "\n".join(out) + "\n"


def _cload(model: Model) -> list[str]:
    if not model.loads:
        return []
    return ["*CLOAD"] + [f"{ld.node}, {DOF_NAMES[ld.dof] + 1}, {num(ld.value)}" for ld in model.loads]


def c3d4_order(model: Model, nodes: list[int]) -> list[int]:
    """C3D4 için pozitif hacimli düğüm sırası (negatifse 2. ve 3. düğüm yer değiştirir)."""
    X = [model.node(n).xyz for n in nodes]
    det = float(np.dot(np.cross(X[1] - X[0], X[2] - X[0]), X[3] - X[0]))
    if det == 0.0:
        raise ModelError(f"Sıfır hacimli tetrahedron: {nodes}")
    return list(nodes) if det > 0 else [nodes[0], nodes[2], nodes[1], nodes[3]]


def _to_inp_tet4(model: Model) -> str:
    """3B `tet4` modeli → C3D4. Her malzeme bir eleman kümesi."""
    out = ["*HEADING", f"3D-CORE capraz kontrol: {model.name}", "*NODE, NSET=NALL"]
    out += [f"{n.id}, {num(n.x)}, {num(n.y)}, {num(n.z)}" for n in model.nodes]
    groups: dict[str, list] = {}
    for e in model.elements:
        groups.setdefault(e.material, []).append(e)
    mat_names = {m.name: f"M{i}" for i, m in enumerate(model.materials, start=1)}
    for k, elems in enumerate(groups.values(), start=1):
        out.append(f"*ELEMENT, TYPE=C3D4, ELSET=G{k}")
        out += [f"{e.id}, " + ", ".join(str(n) for n in c3d4_order(model, e.nodes)) for e in elems]
    out.append("*ELSET, ELSET=EALL")
    out += [f"G{k}" for k in range(1, len(groups) + 1)]
    for m in model.materials:
        out += [f"*MATERIAL, NAME={mat_names[m.name]}", "*ELASTIC", f"{num(m.E)}, {num(m.nu)}"]
    for k, mat in enumerate(groups, start=1):
        out += [f"*SOLID SECTION, ELSET=G{k}, MATERIAL={mat_names[mat]}"]
    out += ["*STEP", "*STATIC"]
    if model.bcs:
        out.append("*BOUNDARY")
        for bc in model.bcs:
            k = DOF_NAMES[bc.dof] + 1
            out.append(f"{bc.node}, {k}, {k}, {num(bc.value)}")
    out += _cload(model)
    out += ["*NODE PRINT, NSET=NALL", "U, RF", "*EL PRINT, ELSET=EALL", "S", "*END STEP"]
    return "\n".join(out) + "\n"


_NUM = r"[-+]?\d+\.\d+E[-+]\d+"


def parse_dat(text: str) -> CcxResult:
    """`.dat` dosyasından yer değiştirme, tepki ve gerilme bloklarını okur."""
    u: dict[int, tuple[float, float, float]] = {}
    rf: dict[int, tuple[float, float, float]] = {}
    sxx: dict[int, float] = {}
    s: dict[int, tuple[float, ...]] = {}
    block = None
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith("displacements"):
            block = u
            continue
        if low.startswith("forces"):
            block = rf
            continue
        if low.startswith("stresses"):
            block = sxx
            continue
        if not low:
            continue
        nums = re.findall(_NUM, line, flags=re.IGNORECASE)
        head = line.split()
        if block is None or not head[0].isdigit():
            continue
        if block is sxx:
            # T3D2 ve C3D4'te her integrasyon noktası aynı; ilki alınır
            sxx.setdefault(int(head[0]), float(nums[0]))
            s.setdefault(int(head[0]), tuple(float(v) for v in nums[:6]))
        else:
            block[int(head[0])] = tuple(float(v) for v in nums[:3])
    if not u:
        raise RuntimeError("ccx .dat dosyasında yer değiştirme bloğu yok")
    return CcxResult(u, rf, sxx, s)


def solve_ccx(model: Model, workdir: Path, inp: str | None = None) -> CcxResult:
    """Modeli ccx ile çözer. `inp` verilirse (ör. `fileio.calculix.to_inp` çıktısı) bu yardımcının
    yazıcısı yerine o metin çözülür. ccx kurulu değilse çağıran test atlanmış olmalı."""
    if CCX is None:
        raise RuntimeError("ccx bulunamadı")
    workdir = Path(workdir)
    (workdir / "model.inp").write_text(to_inp(model) if inp is None else inp)
    p = subprocess.run(
        [CCX, "-i", "model"],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=120,
        stdin=subprocess.DEVNULL,
    )
    dat = workdir / "model.dat"
    if p.returncode != 0 or not dat.exists() or "error" in p.stdout.lower():
        raise RuntimeError(f"ccx başarısız (kod {p.returncode}):\n{p.stdout[-3000:]}\n{p.stderr[-2000:]}")
    return parse_dat(dat.read_text())
