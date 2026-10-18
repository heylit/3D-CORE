"""
SPEC 47b — Çok eksen ekranının örnek işleri (uydurma geometri; gizlilik kuralı).

Tezgâh: `examples/tezgah_ac_besik.json` (SPEC 44, uydurma AC beşik). `ac_besik_dar` aynı tezgâhın `A` sınırı
bilerek dar seçilmiş varyantıdır; `examples/`'ta değil, burada `DAR_PROFIL` ile kurulur.

Örnekler (SPEC 47 "Ekran 2 / Örnek işler"):
- `egik_yuz_3arti2`: 80×60×40 blok, bir kenarı boyunca 30° eğik yüz, eğik yüzde 30×20×3 cep; çerçeve
  `from_normal(o, n, x_hint)`, SPEC 03 cebi yerel çerçevede, `to_world` ile WCS'ye; Ø6 düz freze. Varsayılan
  profil `ac_besik`.
- `kubbe_5eksen`: 60×60 taban, R40 küre kapağı (tepe z = 20); SPEC 06 `Raster` + SPEC 42 `finish5`,
  `Orientation("normal", lead=0, tilt=10)`, Ø6 küresel uç, `linearize(tol_p=1e-3, tol_a=0.05)`. Varsayılan
  profil `ac_besik_dar` (tarayıcıda en az bir `eksen_siniri` olayı görünsün diye); `profil="ac_besik"` ile
  olaysız kurulur.
- `kubbe_carpisma`: `kubbe_5eksen` + takım tutucusunun geçtiği yerde fikstür kutusu; varsayılan profil
  `ac_besik`.

Bu modül `EKRAN` vermez (`_` önekli: A3 import etmez); ekran kaydı yalnız `cok_eksen.py`'nin `EKRAN`'ını
kullanır. SPEC 41–44 modülleri fonksiyonların içinde import edilir: onlar yokken bu modülün importu
başarılıdır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cam.multiaxis.machine import MachineModel
    from cam.multiaxis.toolpath5 import Orientation

    from cam.dropcutter import TriMesh
    from cam.model import Frame, Setup, Stock, Tool, Toolpath

ORNEKLER: tuple[str, ...] = ("egik_yuz_3arti2", "kubbe_5eksen", "kubbe_carpisma")
PROFILLER: tuple[str, ...] = ("ac_besik", "ac_besik_dar")

# Varsayılan girdiler (SPEC 47): POST /parametre anahtarları bu adlardır.
LEAD = 0.0  # derece
TILT = 10.0  # derece
TOL_P = 1e-3  # mm
TOL_A = 0.05  # derece
CLEARANCE = 0.0  # mm, SPEC 44 check() güvenlik payı
PARAMETRELER: tuple[str, ...] = ("lead", "tilt", "tol_p", "tol_a", "L", "clearance")


@dataclass
class CokEksenIsi:
    """Çok eksen ekranında oynatılan bir iş: çekirdeğin (41–44) girdileri ve ürettiği yollar.

    ad      : örnek adı (`ORNEKLER`'den)
    tur     : "3arti2" | "5eksen"
    profil  : "ac_besik" | "ac_besik_dar"
    model   : SPEC 44 `MachineModel` (gövdeler ve `profile.kinematics`)
    setup   : SPEC 14 `Setup` (stok, WCS)
    tool    : işlemlerin takımı
    L       : takım boyu (pivot – uç) [mm]
    ops     : WCS'de, her `Move.axis` dolu yollar (3+2: `to_world` çıktısı; 5 eksen: `linearize` çıktısı)
    ham     : çekirdeğin ilk yolu (5 eksen: `finish5` çıktısı, `linearize` öncesi; 3+2: `frame`'li yerel
              SPEC 03 yolu, `to_machine` girdisi)
    cerceveler : işlem başına 3+2 çerçevesi (`Frame`) ya da None
    yonelimler : işlem başına SPEC 42 `Orientation` ya da None
    part    : parça ağı (çakma hesabı için) ya da None
    lead, tilt, tol_p, tol_a, clearance : kullanıcının değiştirebildiği girdiler (`PARAMETRELER`)
    """

    ad: str
    tur: str
    profil: str
    model: MachineModel
    setup: Setup
    tool: Tool
    L: float
    ops: list[Toolpath]
    ham: list[Toolpath]
    cerceveler: list[Frame | None] = field(default_factory=list)
    yonelimler: list[Orientation | None] = field(default_factory=list)
    part: TriMesh | None = None
    lead: float = LEAD
    tilt: float = TILT
    tol_p: float = TOL_P
    tol_a: float = TOL_A
    clearance: float = CLEARANCE

    @property
    def stock(self) -> Stock:
        return self.setup.stock


def tezgah_modeli(profil: str = "ac_besik") -> MachineModel:
    """`examples/tezgah_ac_besik.json`'dan `MachineModel`; `ac_besik_dar` → aynı model, `A` sınırı dar.

    Bilinmeyen profil → CamError.
    """
    raise NotImplementedError("SPEC 47b: uygulanmadı")


def ornek(ad: str, profil: str | None = None, **girdi: float) -> CokEksenIsi:
    """Örnek işi kurar. `profil` None → örneğin varsayılan profili (modül belgesi).

    `girdi`: `PARAMETRELER` anahtarlarından değerler (verilmeyen varsayılan). Bilinmeyen örnek → KeyError;
    bilinmeyen profil, bilinmeyen girdi anahtarı ya da geçersiz değer (`tol_p ≤ 0`, `L ≤ 0` …) → CamError
    (çekirdeğin metniyle). Her çağrı yeni nesne kurar; önceki işler değişmez.
    """
    raise NotImplementedError("SPEC 47b: uygulanmadı")


def egik_yuz_3arti2(profil: str = "ac_besik", **girdi: float) -> CokEksenIsi:
    """`egik_yuz_3arti2` örneği (modül belgesi)."""
    raise NotImplementedError("SPEC 47b: uygulanmadı")


def kubbe_5eksen(profil: str = "ac_besik_dar", **girdi: float) -> CokEksenIsi:
    """`kubbe_5eksen` örneği (modül belgesi)."""
    raise NotImplementedError("SPEC 47b: uygulanmadı")


def kubbe_carpisma(profil: str = "ac_besik", **girdi: float) -> CokEksenIsi:
    """`kubbe_carpisma` örneği (modül belgesi): `kubbe_5eksen` + fikstür kutusu gövdesi."""
    raise NotImplementedError("SPEC 47b: uygulanmadı")
