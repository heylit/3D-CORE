"""
SPEC 24 — Örnek işler ve parametre → iş üretimi.

Örnek işler uydurma geometridir (gizlilik kuralı). İşlemler `cam` paketinin herkese açık
fonksiyonlarıyla (SPEC 03 `face`, `contour`, `pocket`; SPEC 04 `DrillOp`) üretilir.

"flans-plakasi": 120 × 80 × 20 mm alüminyum blok; işlemler sırasıyla
    0 "yuzey"  (alın frezeleme)     parametreler: D, ap, F, rpm
    1 "kontur" (dış kontur)          parametreler: D, ap, F, rpm
    2 "cep"    (orta cep)            parametreler: D, ap, F, rpm, stepover
    3 "delik"  (köşe delikleri G83)  parametreler: D, q, F, rpm
`D` takım çapı [mm], `ap` paso derinliği [mm], `F` ilerleme [mm/dk], `rpm` devir [dev/dk],
`stepover` yanal adım [mm], `q` gagalama derinliği [mm].
"""

from __future__ import annotations

from tezgah.kopru import IsTanimi

ORNEK_ISLER: tuple[str, ...] = ("flans-plakasi",)


def ornek_is(ad: str, parametreler: dict[int, dict[str, float]] | None = None) -> IsTanimi:
    """`ad` örnek işini kurar. `parametreler` {işlem indeksi: {anahtar: değer}} varsayılanları ezer.

    Bilinmeyen iş, işlem indeksi ya da anahtar → KeyError. Çekirdeğin reddettiği değer (ör. D ≤ 0,
    cep takımdan dar) çekirdeğin `CamError` / `ModelError`'ını olduğu gibi geçirir.
    """
    raise NotImplementedError("SPEC 24: uygulanmadı")


def parametre_uygula(tanim: IsTanimi, islem: int, anahtar: str, deger: float) -> IsTanimi:
    """`tanim`'ın parametrelerinde tek değeri değiştirip işi yeniden üretir; `tanim` değişmez."""
    raise NotImplementedError("SPEC 24: uygulanmadı")
