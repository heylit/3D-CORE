"""
SPEC 54 Karar 3 — Dosyadan parça açma: STEP / STL okumanın §1 biçimli sarmalayıcısı.

`Part.from_step` ya da `geometry.mesh.read_stl` çağrılır; çıkan her hata
`<dosya adı>: <ne oldu> — <ne yapılabilir>` biçimli `GeometryError`'a çevrilir, neden `__cause__`'da kalır.
"""

from __future__ import annotations

from pathlib import Path

from geometry.part import GeometryError, Part

UZANTILAR = (".step", ".stp", ".stl")

YENIDEN_STEP = "dosyayı CAD programınızda STEP AP214 olarak yeniden dışa aktarın"


def _step_bozuk_mu(yol: Path) -> str | None:
    """Okumadan önce STEP'in iskeletini denetler; bozuksa ne eksik olduğunu döndürür."""
    metin = yol.read_bytes().decode("latin-1")
    if not metin.lstrip().startswith("ISO-10303-21;"):
        return "STEP başlığı (ISO-10303-21;) yok"
    if "END-ISO-10303-21;" not in metin:
        return "dosya yarıda kesilmiş (END-ISO-10303-21; yok)"
    if metin.count("ENDSEC;") < 2:
        return "sözdizimi bozuk (HEADER ya da DATA bölümünün ENDSEC; satırı yok)"
    return None


def _step_oku(yol: Path, ad: str) -> Part:
    bozuk = _step_bozuk_mu(yol)
    if bozuk is not None:
        raise GeometryError(f"{yol.name}: {bozuk} — {YENIDEN_STEP}")
    try:
        return Part.from_step(yol, name=ad)
    except Exception as e:  # noqa: BLE001 — OCCT / build123d istisnası da kullanıcı diline çevrilir
        raise GeometryError(
            f"{yol.name}: dosyada katı cisim bulunamadı (yalnız yüz, kabuk ya da okunamayan şekil var) — "
            "parçayı katı (solid) olarak yeniden dışa aktarın"
        ) from e


def _stl_oku(yol: Path, ad: str) -> Part:
    from geometry.mesh import read_stl

    try:
        return read_stl(yol, name=ad)
    except Exception as e:  # noqa: BLE001
        if isinstance(e, GeometryError) and ("kapalı" in str(e) or "kabuk" in str(e)):
            ne = "üçgen ağı kapalı değil (eksik üçgen ya da delik var)"
        else:
            ne = "STL okunamadı ya da kapalı bir katı oluşturmuyor"
        raise GeometryError(
            f"{yol.name}: {ne} — ağı bir mesh programında onarıp kapalı katı olarak yeniden dışa aktarın"
        ) from e


def parca_oku(yol: str | Path, ad: str | None = None) -> Part:
    """STEP ya da STL dosyasından tek katı parça; bozuk / boş / katısız / kapalı olmayan → GeometryError."""
    yol = Path(yol)
    uzanti = yol.suffix.lower()
    if uzanti not in UZANTILAR:
        raise GeometryError(f"{yol.name}: desteklenmeyen dosya türü — STEP (.step, .stp) ya da STL seçin")
    if not yol.is_file():
        raise GeometryError(f"{yol.name}: dosya bulunamadı — yolu denetleyin ya da dosyayı yeniden seçin")
    if yol.stat().st_size == 0:
        raise GeometryError(f"{yol.name}: dosya boş (0 bayt) — dosyayı CAD programında yeniden dışa aktarın")
    ad = ad or yol.stem
    if uzanti == ".stl":
        return _stl_oku(yol, ad)
    return _step_oku(yol, ad)
