"""
CalculiX (ccx) çapraz kontrol yardımcıları: `core.model.Model` -> .inp, ccx çalıştır, .dat oku.

Kendi çözücümüzden bağımsız bir FEM çözücüsüyle aynı modeli çözüp sonuçları karşılaştırmak için.
Sadece testlerde kullanılır; SPEC 13 (`fileio/` CalculiX dışa aktarımı) gelince o yazıcı da burada
aynı sonuçlarla denenebilir.

Eşleme (1B çubuk, `bar1d`): düğüm (x, 0, 0), eleman T3D2 (2 düğümlü 3B kafes), kesit
`*SOLID SECTION` alanı A, malzeme `*ELASTIC` E, ν. 1B modelde y ve z serbestlikleri bütün
düğümlerde tutulur, böylece ccx'teki problem bizimkiyle aynı olur.
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

from core.model import DOF_NAMES, Model, ModelError

CCX = shutil.which("ccx") or shutil.which("ccx_2.21") or shutil.which("ccx2.21")


@dataclass
class CcxResult:
    u: dict[int, tuple[float, float, float]]  # düğüm id -> (ux, uy, uz) [mm]
    rf: dict[int, tuple[float, float, float]]  # düğüm id -> tepki (fx, fy, fz) [N]
    sxx: dict[int, float]  # eleman id -> eksenel gerilme [MPa]


def to_inp(model: Model) -> str:
    """Modeli CalculiX girdi dosyası metnine çevirir (şimdilik sadece 1B `bar1d`)."""
    model.validate()
    if model.dim != 1 or any(e.type != "bar1d" for e in model.elements):
        raise ModelError("CalculiX yazıcısı şimdilik sadece 1B 'bar1d' modelini destekliyor")
    out = ["*HEADING", f"3D-CORE capraz kontrol: {model.name}", "*NODE, NSET=NALL"]
    out += [f"{n.id}, {n.x!r}, 0.0, 0.0" for n in model.nodes]

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
        out += [f"*MATERIAL, NAME={mat_names[m.name]}", "*ELASTIC", f"{m.E!r}, {m.nu!r}"]
    for k, (mat, sec) in enumerate(groups, start=1):
        out += [f"*SOLID SECTION, ELSET=G{k}, MATERIAL={mat_names[mat]}", f"{model.section(sec).A!r}"]

    out += ["*STEP", "*STATIC", "*BOUNDARY", "NALL, 2, 3"]  # 1B: uy = uz = 0
    for bc in model.bcs:
        k = DOF_NAMES[bc.dof] + 1
        out.append(f"{bc.node}, {k}, {k}, {bc.value!r}")
    if model.loads:
        out.append("*CLOAD")
        out += [f"{ld.node}, {DOF_NAMES[ld.dof] + 1}, {ld.value!r}" for ld in model.loads]
    out += ["*NODE PRINT, NSET=NALL", "U, RF", "*EL PRINT, ELSET=EALL", "S", "*END STEP"]
    return "\n".join(out) + "\n"


_NUM = r"[-+]?\d+\.\d+E[-+]\d+"


def parse_dat(text: str) -> CcxResult:
    """`.dat` dosyasından yer değiştirme, tepki ve gerilme bloklarını okur."""
    u: dict[int, tuple[float, float, float]] = {}
    rf: dict[int, tuple[float, float, float]] = {}
    sxx: dict[int, float] = {}
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
            sxx.setdefault(int(head[0]), float(nums[0]))  # her integrasyon noktası aynı (T3D2)
        else:
            block[int(head[0])] = tuple(float(v) for v in nums[:3])
    if not u:
        raise RuntimeError("ccx .dat dosyasında yer değiştirme bloğu yok")
    return CcxResult(u, rf, sxx)


def solve_ccx(model: Model, workdir: Path) -> CcxResult:
    """Modeli ccx ile çözer. ccx kurulu değilse çağıran test atlanmış olmalı."""
    if CCX is None:
        raise RuntimeError("ccx bulunamadı")
    workdir = Path(workdir)
    (workdir / "model.inp").write_text(to_inp(model))
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
