"""
CalculiX (ccx) girdi dosyası (.inp) yazıcısı (SPEC 13).

Eşleme: `bar1d` (1B) → T3D2, `tet4` (3B) → C3D4; malzeme `*ELASTIC` E, ν; sınır koşulları
`*BOUNDARY`, yükler `*CLOAD`. 1B modelde bütün düğümlerde uy = uz = 0 tutulur.
Gerçel sayılar `format(x, ".12e")` ile yazılır: ccx bir sayı alanını en çok 20 karakter okur.
Birimler N, mm, MPa (CalculiX birimsizdir, olduğu gibi aktarılır).
Kaynak: CalculiX CrunchiX User's Manual 2.21 (C3D4, T3D2, *SOLID SECTION, *EL PRINT).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.model import DOF_NAMES, Element, Model, ModelError

# Eleman tipi -> (CalculiX tipi, izin verilen model boyutu)
CCX_TIPI = {"bar1d": ("T3D2", 1), "tet4": ("C3D4", 3)}


def _g(x: float) -> str:
    """Gerçel sayı alanı: 13 anlamlı basamak, en çok 20 karakter."""
    return format(float(x), ".12e")


def _dugum_sirasi(e: Element, model: Model) -> list[int]:
    """C3D4 için pozitif hacimli düğüm sırası.

    det[x2−x1, x3−x1, x4−x1] < 0 ise 2. ve 3. düğüm yer değiştirir.
    """
    if e.type != "tet4":
        return list(e.nodes)
    X = np.array([model.node(nid).xyz for nid in e.nodes])
    if np.linalg.det(X[1:] - X[0]) < 0:
        n1, n2, n3, n4 = e.nodes
        return [n1, n3, n2, n4]
    return list(e.nodes)


def _denetle(model: Model) -> str:
    """Modelin yazılabilir olduğunu denetler, eleman tipini döndürür. Aksi halde ModelError."""
    model.validate()
    tipler = {e.type for e in model.elements}
    if not tipler:
        raise ModelError("CalculiX yazıcısı: modelde eleman yok")
    if len(tipler) > 1:
        raise ModelError(f"CalculiX yazıcısı: tek modelde tek eleman tipi olmalı ({sorted(tipler)})")
    (tip,) = tipler
    if tip == "tet10":
        raise NotImplementedError("SPEC 67a: CalculiX C3D10 yazımı")
    if tip not in CCX_TIPI:
        raise ModelError(f"CalculiX yazıcısı: desteklenmeyen eleman tipi '{tip}'")
    _, dim = CCX_TIPI[tip]
    if model.dim != dim:
        raise ModelError(f"CalculiX yazıcısı: '{tip}' sadece {dim}B modelde yazılır (dim={model.dim})")
    if tip == "bar1d":
        for e in model.elements:
            if e.section is None:
                raise ModelError(f"Eleman {e.id}: bar1d için kesit gerekli")
    return tip


def to_inp(model: Model) -> str:
    """Modeli CalculiX girdi metnine çevirir. Desteklenmeyen model → ModelError."""
    tip = _denetle(model)
    ccx_tipi, _ = CCX_TIPI[tip]
    out = ["*HEADING", f"3D-CORE: {' '.join(model.name.split())}", "*NODE, NSET=NALL"]
    out += [f"{n.id}, {_g(n.x)}, {_g(n.y)}, {_g(n.z)}" for n in model.nodes]

    # Her (malzeme, kesit) çifti bir eleman kümesi
    gruplar: dict[tuple[str, str | None], list[Element]] = {}
    for e in model.elements:
        gruplar.setdefault((e.material, e.section), []).append(e)
    mat_adi = {m.name: f"M{i}" for i, m in enumerate(model.materials, start=1)}
    for k, elemanlar in enumerate(gruplar.values(), start=1):
        out.append(f"*ELEMENT, TYPE={ccx_tipi}, ELSET=G{k}")
        out += [", ".join(str(i) for i in [e.id, *_dugum_sirasi(e, model)]) for e in elemanlar]
    out.append("*ELSET, ELSET=EALL")
    out += [f"G{k}" for k in range(1, len(gruplar) + 1)]
    for m in model.materials:
        out += [f"*MATERIAL, NAME={mat_adi[m.name]}", "*ELASTIC", f"{_g(m.E)}, {_g(m.nu)}"]
    for k, (mat, kesit) in enumerate(gruplar, start=1):
        out.append(f"*SOLID SECTION, ELSET=G{k}, MATERIAL={mat_adi[mat]}")
        if tip == "bar1d":
            out.append(_g(model.section(kesit).A))

    out += ["*STEP", "*STATIC", "*BOUNDARY"]
    if model.dim == 1:
        out.append("NALL, 2, 3")  # 1B: uy = uz = 0
    for bc in model.bcs:
        k = DOF_NAMES[bc.dof] + 1
        out.append(f"{bc.node}, {k}, {k}, {_g(bc.value)}")

    # Aynı düğüm ve DOF'taki yükler toplanır (çözücümüz gibi)
    yukler: dict[tuple[int, int], float] = {}
    for ld in model.loads:
        anahtar = (ld.node, DOF_NAMES[ld.dof] + 1)
        yukler[anahtar] = yukler.get(anahtar, 0.0) + ld.value
    if yukler:
        out.append("*CLOAD")
        out += [f"{nid}, {k}, {_g(v)}" for (nid, k), v in yukler.items()]

    out += [
        "*NODE PRINT, NSET=NALL",
        "U, RF",
        "*EL PRINT, ELSET=EALL",
        "S",
        "*NODE FILE",
        "U",
        "*EL FILE",
        "S",
        "*END STEP",
    ]
    return "\n".join(out) + "\n"


def write_inp(model: Model, path: str | Path) -> None:
    """to_inp çıktısını dosyaya yazar."""
    Path(path).write_text(to_inp(model), encoding="utf-8")
