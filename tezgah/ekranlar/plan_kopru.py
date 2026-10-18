"""
SPEC 47a — Plan ekranının köprüsü: SPEC 29 planı → `Plan` JSON, özellik eşlemesi, plan farkı, kontroller.

Saf fonksiyonlar; FastAPI'siz test edilir. Ön yüz hesap yapmaz: buradaki her sayı SPEC 27 / 29 / 05 / 22
fonksiyonlarının çıktısıdır. Şema SPEC 47 "Ekran 1: Plan / Veri modeli".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cam.plan import MillPlan
    from cam.plan_turn import TurnPlan
    from cam.plan_verify import PlanCheck

    from cam.library import ToolLibrary
    from tezgah.ekranlar.plan_ornekler import PlanGirdisi

SEMA = 1

# SPEC 29 §1 gerekçe ve not kodlarının düz Türkçesi (ön yüz yalnız bunu gösterir).
GEREKCE_METNI: dict[str, str] = {
    "kesme_verisi_yok": "Bu türde, bu malzeme için kesme verisi olan takım yok",
    "takim_yok": "Uygun tür, çap ya da genişlikte takım yok",
    "takim_sigmiyor": "Aday takımların hiçbiri bölgeye sığmıyor",
    "kesici_boy_yetmez": "Sığan takımların kesici boyu derinliğe yetmiyor",
    "ustten_erisilemez": "Delik ekseni −Z değil: üstten erişilemez",
    "havsa_takimi_yok": "Havşa takımı yok: delik açılır, havşa açılmaz",
    "kilavuz_cevrimi_yok": "Kılavuz çevrimi (G84) yok: yalnız kılavuz matkabı deliği açılır",
    "baglama_carpismasi": "İşlem bağlama elemanına çarpıyor",
    "on_delik_yok": "Ham malzeme dolu: iç profil için ön delik yok",
    "genel_girinti": "Profilli kanal işlemi yok",
}
NOT_METNI: dict[str, str] = {
    "kose_artigi": "Köşede kalan malzeme",
    "yan_paso_kisildi": "Yan paso kısıldı",
    "delik_tasma_kisildi": "Delik taşması kısıldı",
    "ikinci_baglama": "Alt yüz için ikinci bağlama",
}


def ozellik_adresleri(plan: MillPlan | TurnPlan) -> list[str]:
    """SPEC 27 sonucundaki her özelliğin adresi, SPEC 29 §1 sırasıyla ("faces[0]", "holes[3]", ...)."""
    raise NotImplementedError("SPEC 47a: ozellik_adresleri")


def grup_ac(feature: str) -> list[str]:
    """İşlemin `feature` alanını tek adreslere açar: "holes[1,4]" → ["holes[1]", "holes[4]"]."""
    raise NotImplementedError("SPEC 47a: grup_ac")


def ozellik_eslemesi(plan: MillPlan | TurnPlan) -> list[dict]:
    """`Ozellik` kayıtları: her adres tam bir kez, `planlandi` (işlem adlarıyla) ya da `planlanamadi`."""
    raise NotImplementedError("SPEC 47a: ozellik_eslemesi")


def islem_sureleri(plan: MillPlan | TurnPlan) -> list[float]:
    """İşlem başına süre [s]: freze SPEC 05 süre tahmini, torna SPEC 22 süre fonksiyonu."""
    raise NotImplementedError("SPEC 47a: islem_sureleri")


def plan_json(
    ad: str,
    plan: MillPlan | TurnPlan,
    lib: ToolLibrary,
    kapali: frozenset[int] = frozenset(),
    secenekler: dict[str, Any] | None = None,
    dogrulama: PlanCheck | None = None,
) -> dict:
    """`Plan` sözlüğü (SPEC 47 şeması; `islemler` = `summary()` + süre, `gcode` bağlama başına)."""
    raise NotImplementedError("SPEC 47a: plan_json")


def plan_farki(eski: dict, yeni: dict) -> dict:
    """İki `Plan` sözlüğünün `Fark`'ı; işlemler `(feature, kind)` çiftiyle eşlenir."""
    raise NotImplementedError("SPEC 47a: plan_farki")


def dogrulama_sozlugu(check: PlanCheck) -> dict:
    """`PlanCheck` → JSON sözlüğü (çarpışmalar dahil)."""
    raise NotImplementedError("SPEC 47a: dogrulama_sozlugu")


def kontroller(plan_sozluk: dict) -> list[dict]:
    """SPEC 47 Plan kontrolleri; `dogrulama` yoksa doğrulama kontrolleri listede yoktur."""
    raise NotImplementedError("SPEC 47a: kontroller")


def kutuphane_suz(lib: ToolLibrary, kapali: frozenset[int]) -> ToolLibrary:
    """`kapali` kimlikli takımlar çıkarılmış yeni kütüphane; `lib` değişmez. Bilinmeyen kimlik → CamError."""
    raise NotImplementedError("SPEC 47a: kutuphane_suz")


def ag_ikili(V, T) -> bytes:
    """Parça ağı (SPEC 25 biçimi): başlık `uint32` nv, nt; `float32[nv·3]`, `uint32[nt·3]`."""
    raise NotImplementedError("SPEC 47a: ag_ikili")


def ag_coz(veri: bytes) -> tuple:
    """`ag_ikili`'nin tersi: (V (nv, 3) float32, T (nt, 3) uint32)."""
    raise NotImplementedError("SPEC 47a: ag_coz")


@dataclass
class PlanOturumu:
    """Bir örneğin sunucudaki durumu: girdi, kapalı takımlar, seçenekler, önbellekli plan ve doğrulama."""

    girdi: PlanGirdisi
    kapali: frozenset[int] = frozenset()
    secenekler: dict[str, Any] = field(default_factory=dict)

    def plan(self) -> MillPlan | TurnPlan:
        """Güncel girdiyle plan (önbellekli; aynı girdi yeniden hesaplanmaz)."""
        raise NotImplementedError("SPEC 47a: PlanOturumu.plan")

    def json(self) -> dict:
        """Güncel `Plan` sözlüğü."""
        raise NotImplementedError("SPEC 47a: PlanOturumu.json")

    def ne_olurdu(
        self,
        takim_kapat: list[int] = (),
        takim_ac: list[int] = (),
        secenek: dict[str, Any] | None = None,
    ) -> dict:
        """Durumu değiştirir, yeniden planlar: `{"plan": Plan, "fark": Fark}`. Hata → durum değişmez."""
        raise NotImplementedError("SPEC 47a: PlanOturumu.ne_olurdu")

    def dogrula(self) -> dict:
        """`verify_mill` / `verify_turn` (parmak izine göre önbellekli); dönen `Plan`'da `dogrulama` dolu."""
        raise NotImplementedError("SPEC 47a: PlanOturumu.dogrula")

    def isler(self, bag: int) -> tuple[str, Any]:
        """Bağlama `bag`'ın iş adı ve SPEC 24 `IsTanimi`'si (torna: `TornaIsi`); bilinmeyen → CamError."""
        raise NotImplementedError("SPEC 47a: PlanOturumu.isler")
