"""SPEC 10 testleri için geçici ara katman: `cam.model.Fixture` (A0 arayüzü) yokken testler toplanabilsin.

A0 main'e girene dek `cam.baglama` import edilemez (`from cam.model import Fixture`). Bu durumda burada
verilen her ad, çağrılınca veya özniteliği istenince NotImplementedError fırlatan bir yer tutucudur:
testler yerelde
"uygulanmamış" (xfail), CI'da (`--uygulanmamis-hata`) kırmızıdır; hiçbiri atlanmaz.
`cam.model.Fixture` var olduğu anda ara katman devreden çıkar: adlar doğrudan `cam.baglama` ve `cam.model`'den
gelir, başka her import hatası olduğu gibi yükselir.
"""

from __future__ import annotations

import cam.model

ADLAR = [
    "AssemblySetup",
    "Chuck3",
    "Clamp",
    "FixtureCollision",
    "FixtureMap",
    "Primitive",
    "SetupSim",
    "Vise",
    "check_clamping",
    "chuck_for",
    "clamp_for",
    "envelope",
    "fixture_collisions",
    "fixture_map",
    "fixture_top",
    "from_assembly",
    "from_fixture",
    "make_fixture",
    "mesh_topmap",
    "primitive_topmap",
    "primitives_wcs",
    "simulate_setup",
    "to_assembly",
    "vise_for",
]


class _YerTutucu:
    """A0 gelmeden kullanılan ad: çağrı ve öznitelik erişimi NotImplementedError."""

    def __init__(self, ad: str) -> None:
        self._ad = ad

    def _hata(self):
        raise NotImplementedError(f"SPEC 10: {self._ad} — cam.model.Fixture (A0) henüz yok")

    def __call__(self, *a, **k):
        self._hata()

    def __getattr__(self, ad: str):
        if ad.startswith("__"):
            raise AttributeError(ad)
        self._hata()


if hasattr(cam.model, "Fixture"):
    import cam.baglama as _b

    Fixture = cam.model.Fixture
    globals().update({ad: getattr(_b, ad) for ad in ADLAR})
else:
    Fixture = _YerTutucu("Fixture")
    globals().update({ad: _YerTutucu(ad) for ad in ADLAR})

__all__ = ["Fixture", *ADLAR]
