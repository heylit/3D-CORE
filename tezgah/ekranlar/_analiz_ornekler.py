"""
SPEC 47c — Analiz ekranının örnek işleri (uydurma geometri; gizlilik kuralı).

- `delikli_plaka`: 200×100×5 plaka [0,200]×[0,100]×[0,5], merkezde Ø10 delik (100, 50); çelik E = 210000,
  ν = 0.3, Re = 235. Kilitli örnek koşulları: x = 0 yüzü ux; x = 0 ∩ y = 50 düğümleri uy;
  x = 0 ∩ y = 50 ∩ z = 0 düğümü uz; x = 200 yüzüne t = (100, 0, 0) MPa çekme.
  Delik çevresinde `Refine` küresi.
  Analitik: Heywood Kt_g (d/W = 0.1) ve Kirsch σ_xx(y).
- `konsol_kiris`: 200×20×20 çubuk; x = 0 yüzü tam mesnet; x = 200 yüzüne t = (0, 0, −2.5) MPa (P = 1000 N).
  Analitik: δ = P·L³/(3·E·I) ve Timoshenko δ_T.

Parçalar OCCT (build123d) ister; kurucular çağrılınca kurulur, import anında değil.
"""

from __future__ import annotations

from collections.abc import Callable

from tezgah.ekranlar._analiz_kopru import AnalizTanimi


def delikli_plaka() -> AnalizTanimi:
    """Delikli plaka örneği (seçimler ve kilitli koşullar dahil)."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


def konsol_kiris() -> AnalizTanimi:
    """Konsol kiriş örneği (seçimler ve kilitli koşullar dahil)."""
    raise NotImplementedError("SPEC 47c: uygulanmadı")


# ad → kurucu; GET /api/ekran/analiz/ornekler bu sırayla listeler
ORNEKLER: dict[str, Callable[[], AnalizTanimi]] = {
    "delikli_plaka": delikli_plaka,
    "konsol_kiris": konsol_kiris,
}
