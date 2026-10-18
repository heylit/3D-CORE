"""
CalculiX (ccx) girdi dosyası (.inp) yazıcısı (SPEC 13).

Eşleme: `bar1d` (1B) → T3D2, `tet4` (3B) → C3D4; malzeme `*ELASTIC` E, ν; sınır koşulları
`*BOUNDARY`, yükler `*CLOAD`. 1B modelde bütün düğümlerde uy = uz = 0 tutulur.
Gerçel sayılar `format(x, ".12e")` ile yazılır: ccx bir sayı alanını en çok 20 karakter okur.
Birimler N, mm, MPa (CalculiX birimsizdir, olduğu gibi aktarılır).
Kaynak: CalculiX CrunchiX User's Manual 2.21 (C3D4, T3D2, *SOLID SECTION, *EL PRINT).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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


def to_inp_thermal(
    model: Model,
    k: float | Mapping[str, float],
    temperatures: Sequence,
    nodal_heat: Mapping[int, float],
) -> str:
    """Kararlı hal ısıl modeli CalculiX girdisine çevirir (SPEC 56).

    tet4 → DC3D4, k → *CONDUCTIVITY, sabit sıcaklık → *BOUNDARY node, 11, 11, T,
    düğüm ısısı [mW] → *CFLUX node, 11, değer, çıktı *NODE PRINT NT.
    `temperatures`: `core.isil.Temperature` benzeri (node, T) kayıtları. Hatalar → ModelError.
    """
    model.validate()
    if model.dim != 3 or not model.elements or any(e.type != "tet4" for e in model.elements):
        raise ModelError("CalculiX ısıl yazıcısı: sadece 3B tet4 modeli")
    k_mat: dict[str, float] = {}
    for m in model.materials:
        if isinstance(k, Mapping):
            if m.name not in k and any(e.material == m.name for e in model.elements):
                raise ModelError(f"CalculiX ısıl yazıcısı: '{m.name}' malzemesi için k yok")
            kk = k.get(m.name)
        else:
            kk = k
        if kk is not None:
            kk = float(kk)
            if not (np.isfinite(kk) and kk > 0.0):
                raise ModelError(f"Isıl iletkenlik k > 0 olmalı (k={kk})")
            k_mat[m.name] = kk

    out = ["*HEADING", f"3D-CORE isil: {' '.join(model.name.split())}", "*NODE, NSET=NALL"]
    out += [f"{n.id}, {_g(n.x)}, {_g(n.y)}, {_g(n.z)}" for n in model.nodes]
    gruplar: dict[str, list[Element]] = {}
    for e in model.elements:
        gruplar.setdefault(e.material, []).append(e)
    mat_adi = {m.name: f"M{i}" for i, m in enumerate(model.materials, start=1)}
    for g, elemanlar in enumerate(gruplar.values(), start=1):
        out.append(f"*ELEMENT, TYPE=DC3D4, ELSET=G{g}")
        out += [", ".join(str(i) for i in [e.id, *_dugum_sirasi(e, model)]) for e in elemanlar]
    out.append("*ELSET, ELSET=EALL")
    out += [f"G{g}" for g in range(1, len(gruplar) + 1)]
    for ad in gruplar:
        out += [f"*MATERIAL, NAME={mat_adi[ad]}", "*CONDUCTIVITY", _g(k_mat[ad])]
    for g, ad in enumerate(gruplar, start=1):
        out.append(f"*SOLID SECTION, ELSET=G{g}, MATERIAL={mat_adi[ad]}")

    out += ["*STEP", "*HEAT TRANSFER, STEADY STATE", "1.0, 1.0"]
    if temperatures:
        out.append("*BOUNDARY")
        for t in temperatures:
            model.node(t.node)
            out.append(f"{t.node}, 11, 11, {_g(t.T)}")
    if nodal_heat:
        out.append("*CFLUX")
        for nid, deger in nodal_heat.items():
            model.node(nid)
            if not np.isfinite(deger):
                raise ModelError(f"Düğüm {nid}: düğüm ısısı sonlu olmalı ({deger})")
            out.append(f"{nid}, 11, {_g(deger)}")
    out += ["*NODE PRINT, NSET=NALL", "NT", "*END STEP"]
    return "\n".join(out) + "\n"
