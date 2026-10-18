"""
SPEC 47b — Çok eksen köprüsü: `CokEksenIsi` → `CokEksen` JSON sözlüğü ve ikili diziler.

Saf fonksiyonlar, yan etkisiz, FastAPI'siz (testler doğrudan çağırır). Birimler mm, s, derece.
Ön yüz mühendislik sayısı hesaplamaz: eklem değerleri, pozlar, olaylar, sapma ve tri-dexel buradan gelir.

CokEksen sözlüğü (SPEC 47 "Ekran 2 / Veri modeli"):
    {
      "sema": 1, "ad": str, "tur": "3arti2" | "5eksen", "profil": "ac_besik" | "ac_besik_dar",
      "tezgah": {"ad", "eksenler": [{"ad", "tur": "dogrusal"|"doner", "min", "max"}],
                 "govdeler": [{"ad", "halka", "sekil": "kutu"|"kapsul"}]},  # sıra = pozlar sırası
      "wcs": Wcs sözlüğü, "L": mm,
      "parametreler": {"lead", "tilt", "tol_p", "tol_a", "L", "clearance"},
      "islemler": [{"i", "ad", "takim", "t0", "t1", "k0", "k1", "cerceve": Frame sözlüğü | None,
                    "yonelim": Orientation sözlüğü | None}],
      "olaylar": [MachineEvent sözlüğü + "zaman"],  # SPEC 44 check() çıktısı + şerit zamanı [s]
      "sim": {"removed_volume", "rest_volume" | None, "gouge_volume" | None, "total_time",
              "collisions": [Collision sözlüğü]} | None,
      "sapma": {"tol_p", "tol_a", "e_p_max", "e_a_max"},
      "kontroller": [Kontrol],
    }
    Kontrol = {"kimlik", "baslik", "deger", "birim", "durum": "tamam"|"uyari"|"hata", "aciklama", "spec"}

Nokta dizisi: k = 0..n-1 küresel nokta indeksi; işlemler art arda, her işlemin başlangıcı ve her
`Move.end`'i bir nokta (`joint_path` / `to_machine` satırları). `islemler[].k0/k1` işlemin kapalı aralığı.

İkili diziler little-endian, her blok 8 baytın katına sıfırla tamamlanır (SPEC 24 `kopru._blok` kuralı).
Her `*_ikili` fonksiyonun `*_coz` eşi vardır; `coz(ikili(x))` bayt düzeyinde geri döner.

Hata: geçersiz girdi `CamError` (ya da çekirdeğin hata türü) fırlatır; sessiz düzeltme yok (altın kural 5).
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import numpy as np

from cam.model import CamError
from tezgah import SEMA

if TYPE_CHECKING:
    from cam.multiaxis.machine import MachineModel
    from cam.sim.tridexel import SimResult5, TriDexel

    from tezgah.ekranlar._cok_eksen_ornekler import CokEksenIsi

GOUGE_TOL = 1e-3  # mm: SPEC 43 çakma eşiği (simulate5 varsayılanı)
SIM_HUCRE = 1.0  # mm: POST /simule tri-dexel hücresi
SAPMA_ARA = 8  # TCP kapalı uç yolunda segment başına ara nokta sayısı
GOVDE_DILIM = 16  # kapsül üçgenlemesinde çevre bölümü

# Bu ekranın kullandığı SPEC 41–44 modülleri; biri yoksa ekran `hazir` değildir (ad: neden metninde).
GEREKEN_MODULLER: tuple[tuple[str, str], ...] = (
    ("cam.multiaxis.kinematics", "SPEC 41"),
    ("cam.multiaxis.indexed", "SPEC 41"),
    ("cam.multiaxis.toolpath5", "SPEC 42"),
    ("cam.multiaxis.linearize", "SPEC 42"),
    ("cam.sim.tridexel", "SPEC 43"),
    ("cam.sim.simulate5", "SPEC 43"),
    ("cam.multiaxis.machine", "SPEC 44"),
    ("cam.multiaxis.collision", "SPEC 44"),
)


def eksik_moduller() -> list[str]:
    """`GEREKEN_MODULLER`'den import edilemeyenlerin "modül (SPEC NN)" metinleri; hepsi varsa boş liste."""
    eksik = []
    for modul, spec in GEREKEN_MODULLER:
        try:
            importlib.import_module(modul)
        except ImportError:
            eksik.append(f"{modul} ({spec})")
    return eksik


# ---------------------------------------------------------------- JSON


def olaylar(is_: CokEksenIsi) -> list[dict]:
    """SPEC 44 `check(model, setup, ops, L, tcp=True, clearance=is_.clearance)` → olay sözlükleri
    (`kind, k, t, a, b, distance, detail`), aynı sırada ve değerde; ek alan `zaman` [s] =
    zaman[k−1] + t·(zaman[k] − zaman[k−1]) (k: SPEC 05 adım indeksi, t: hareket içi parametre; K10 eki)."""
    raise NotImplementedError("SPEC 47b: uygulanmadı")


def sapma_ozeti(is_: CokEksenIsi) -> dict:
    """`{"tol_p", "tol_a", "e_p_max", "e_a_max"}`: `ops`'un her segmentinde `deviation(..., t=0.5)`
    değerlerinin en büyükleri."""
    raise NotImplementedError("SPEC 47b: uygulanmadı")


def kontroller(is_: CokEksenIsi, sim: list[SimResult5] | None = None) -> list[dict]:
    """Kanıt paneli (SPEC 47 "Kontroller (Çok eksen)"):

    `tezgah_carpma`, `eksen_siniri` (SPEC 44; olay sayısı > 0 → hata), `dogrusallastirma` (SPEC 42;
    `e_p_max > tol_p` ya da `e_a_max > tol_a` → hata). `sim` verilirse ek olarak `govde_carpma` (SPEC 43
    `collisions` > 0 → hata), `cakma` (`gouge_volume` > `GOUGE_TOL` → hata; parça yoksa yok), `sure` (bilgi,
    `tamam`). `sim` yoksa SPEC 43 kontrolleri listede yoktur.
    """
    raise NotImplementedError("SPEC 47b: uygulanmadı")


def sim_ozeti(sim: list[SimResult5]) -> dict:
    """Zincirleme `simulate5` sonuçları → `CokEksen["sim"]`: son sonucun `removed_volume` (V_stok − son
    `TriDexel.volume()`), `rest_volume()` / `gouge_volume()` (parça yoksa None), toplam süre,
    tüm çarpışmalar."""
    raise NotImplementedError("SPEC 47b: uygulanmadı")


def cok_json(is_: CokEksenIsi, sim: list[SimResult5] | None = None) -> dict:
    """`CokEksen` sözlüğü (modül belgesi). `sim` None → `"sim": None`."""
    raise NotImplementedError("SPEC 47b: uygulanmadı")


def parmak_izi(is_: CokEksenIsi, **ek: object) -> str:
    """Girdinin parmak izi: (ad, profil, `PARAMETRELER` değerleri, `ek`) JSON'unun SHA-256'sı (hex).
    Pahalı uçların (simule) önbellek anahtarı (SPEC 47 "Ortak veri kuralları", K21)."""
    raise NotImplementedError("SPEC 47b: uygulanmadı")


def parametre_uygula(is_: CokEksenIsi, anahtar: str, deger: float) -> CokEksenIsi:
    """`anahtar ∈ PARAMETRELER` değişmiş YENİ iş (örnek yeniden kurulur); `is_` değişmez.

    Bilinmeyen anahtar → CamError; geçersiz değer (`tol_p ≤ 0`, `L ≤ 0` …) → çekirdeğin hatası.
    """
    raise NotImplementedError("SPEC 47b: uygulanmadı")


def sure(is_: CokEksenIsi) -> float:
    """İşin toplam süresi [s] (nokta dizisindeki son kümülatif süre).
    `sure_farki = sure(yeni) − sure(eski)`."""
    raise NotImplementedError("SPEC 47b: uygulanmadı")


# ---------------------------------------------------------------- simülasyon


def simule(is_: CokEksenIsi, cell: float = SIM_HUCRE) -> list[SimResult5]:
    """Zincirleme tri-dexel: `simulate5([ops[0]], stock, cell, part=part)`, sonra her j için
    `simulate5([ops[j]], stock, cell, part=part, initial=önceki.tridexel)`. İşlem başına bir sonuç."""
    raise NotImplementedError("SPEC 47b: uygulanmadı")


# ---------------------------------------------------------------- ikili diziler


def _blok(a: np.ndarray) -> bytes:
    """Dizinin little-endian baytları, 8'in katına sıfırla tamamlanmış."""
    b = a.astype(a.dtype.newbyteorder("<"), copy=False).tobytes()
    return b + bytes(-len(b) % 8)


def _baslik_ikili(*sayilar: int) -> bytes:
    """uint32 sema + sayılar, 8'in katına tamamlanmış."""
    return _blok(np.array((SEMA, *sayilar), dtype=np.uint32))


def _oku(veri: bytes, ofs: int, dtype: str, n: int, ne: str) -> tuple[np.ndarray, int]:
    dt = np.dtype(dtype).newbyteorder("<")
    boy = dt.itemsize * n
    if ofs + boy > len(veri):
        raise CamError(f"{ne} beklenenden kısa ({len(veri)} bayt)")
    a = np.frombuffer(veri, dtype=dt, count=n, offset=ofs)
    return a.astype(dt.newbyteorder("="), copy=True), ofs + boy + (-boy % 8)


def _baslik(veri: bytes, ne: str, m: int) -> tuple[list[int], int]:
    """Başlığı okur ve sürümü denetler; (sayılar, sonraki ofset)."""
    b, ofs = _oku(veri, 0, "u4", 1 + m, ne)
    if int(b[0]) != SEMA:
        raise CamError(f"{ne} sürümü {int(b[0])}, beklenen {SEMA}")
    return [int(v) for v in b[1:]], ofs


def _son(veri: bytes, ofs: int, ne: str) -> None:
    if ofs != len(veri):
        raise CamError(f"{ne} boyu tutmuyor ({len(veri)} bayt, beklenen {ofs})")


def noktalar_ikili(is_: CokEksenIsi) -> bytes:
    """Nokta dizisi (SPEC 47 `noktalar`).

    Biçim:
        başlık : uint32 sema, uint32 n, uint32 k (döner eksen sayısı)
        konum  : float32[n·3]       takım ucu (WCS)
        zaman  : float64[n]         kümülatif süre [s], azalmayan, zaman[0] = 0
        islem  : int16[n]           işlem indeksi
        hizli  : uint8[n]           1 = noktaya G0 ile gelinir
        a      : float32[n·3]       takım ekseni (WCS, birim)
        q      : float64[n·(3+k)]   eklem değerleri (X Y Z mm, döner eksenler derece, sarma çözülmüş):
                                    5 eksen `joint_path(op, kin, wcs, L)`, 3+2 `to_machine(ham, kin, wcs, L)`
        g93    : float32[n]         `inverse_time(op, q)`; işlemin ilk noktasında ve hızlı harekette 0
    """
    raise NotImplementedError("SPEC 47b: uygulanmadı")


def noktalar_coz(veri: bytes) -> dict[str, np.ndarray]:
    """→ {"konum" (n, 3), "zaman", "islem", "hizli", "a" (n, 3), "q" (n, 3+k), "g93"}.
    Sürüm / boy hatası → CamError."""
    (n, k), ofs = _baslik(veri, "Nokta dizisi", 2)
    out = {}
    for ad, dt, m in (("konum", "f4", 3), ("zaman", "f8", 1), ("islem", "i2", 1), ("hizli", "u1", 1),
                      ("a", "f4", 3), ("q", "f8", 3 + k), ("g93", "f4", 1)):  # fmt: skip
        out[ad], ofs = _oku(veri, ofs, dt, n * m, "Nokta dizisi")
    _son(veri, ofs, "Nokta dizisi")
    out["konum"] = out["konum"].reshape(n, 3)
    out["a"] = out["a"].reshape(n, 3)
    out["q"] = out["q"].reshape(n, 3 + k)
    return out


def pozlar_ikili(is_: CokEksenIsi) -> bytes:
    """Gövde pozları (SPEC 47 `pozlar`): her nokta k ve gövde b için
    `poses(model, q_k, setup, tool)[halka(b)]`.

    Biçim:
        başlık : uint32 sema, uint32 n, uint32 m (gövde sayısı, sıra `CokEksen.tezgah.govdeler`)
        poz    : float32[n·m·12]    R satır öncelikli 9 + t 3
    """
    raise NotImplementedError("SPEC 47b: uygulanmadı")


def pozlar_coz(veri: bytes) -> dict[str, np.ndarray]:
    """→ {"R" (n, m, 3, 3), "t" (n, m, 3)}. Sürüm / boy hatası → CamError."""
    (n, m), ofs = _baslik(veri, "Poz dizisi", 2)
    ham, ofs = _oku(veri, ofs, "f4", n * m * 12, "Poz dizisi")
    _son(veri, ofs, "Poz dizisi")
    ham = ham.reshape(n, m, 12)
    return {"R": ham[:, :, :9].reshape(n, m, 3, 3).copy(), "t": ham[:, :, 9:].copy()}


def sapma_ikili(is_: CokEksenIsi) -> bytes:
    """Doğrusallaştırma sapması (SPEC 47 `sapma`); segment = bir işlemin ardışık iki noktası (s toplam).

    Biçim:
        başlık : uint32 sema, uint32 s, uint32 SAPMA_ARA
        e      : float32[s·2]          (e_p, e_a) = deviation(kin, wcs, L, q0, q1, p0, p1, a0, a1, 0.5)
        tcp    : float32[s·SAPMA_ARA·3] TCP kapalı uç yolu: q(u) = q0 + u·(q1 − q0),
                                        u = (i+1)/(SAPMA_ARA+1), i = 0..SAPMA_ARA-1;
                                        forward(kin, q(u), L, wcs) ucu
    """
    raise NotImplementedError("SPEC 47b: uygulanmadı")


def sapma_coz(veri: bytes) -> dict[str, np.ndarray]:
    """→ {"e" (s, 2), "tcp" (s, SAPMA_ARA, 3)}. Sürüm / boy hatası → CamError."""
    (s, ara), ofs = _baslik(veri, "Sapma dizisi", 2)
    e, ofs = _oku(veri, ofs, "f4", 2 * s, "Sapma dizisi")
    tcp, ofs = _oku(veri, ofs, "f4", 3 * s * ara, "Sapma dizisi")
    _son(veri, ofs, "Sapma dizisi")
    return {"e": e.reshape(s, 2), "tcp": tcp.reshape(s, ara, 3)}


def dexel_ikili(dexeller: list[TriDexel]) -> bytes:
    """İşlem sonu tri-dexel anlık görüntüleri (SPEC 47 `dexel`); yüzey ağı kurulmaz.

    Biçim:
        başlık : uint32 sema, uint32 g (görüntü sayısı)
        her görüntü:
            izgara : float64[6] (x0, y0, z0, dx, dy, dz), uint32[3] (nx, ny, nz)
            her eksen, sıra z, x, y ("z": nx·ny ışın, (i, j) = (x, y); "x": ny·nz, (y, z);
            "y": nx·nz, (x, z)):
                uint32 ışın sayısı, uint16[ışın] aralık sayıları,
                float32[2·Σ] uç çiftleri (ışın parametresinde); ışınlar i dış, j iç döngü
    """
    raise NotImplementedError("SPEC 47b: uygulanmadı")


def dexel_coz(veri: bytes) -> list[dict]:
    """→ görüntü başına {"izgara": {"x0", "y0", "z0", "dx", "dy", "dz", "nx", "ny", "nz"},
    "x" | "y" | "z": list[list[tuple[float, float]]]} (ışın sırası `dexel_ikili` gibi). Hata → CamError."""
    (g,), ofs = _baslik(veri, "Dexel dizisi", 1)
    out = []
    for _ in range(g):
        x, ofs = _oku(veri, ofs, "f8", 6, "Dexel dizisi")
        nn, ofs = _oku(veri, ofs, "u4", 3, "Dexel dizisi")
        izgara = dict(zip(("x0", "y0", "z0", "dx", "dy", "dz"), (float(v) for v in x), strict=True))
        izgara |= dict(zip(("nx", "ny", "nz"), (int(v) for v in nn), strict=True))
        goruntu: dict = {"izgara": izgara}
        for eksen in ("z", "x", "y"):
            (r,), ofs = _oku(veri, ofs, "u4", 1, "Dexel dizisi")
            say, ofs = _oku(veri, ofs, "u2", int(r), "Dexel dizisi")
            uc, ofs = _oku(veri, ofs, "f4", 2 * int(say.sum()), "Dexel dizisi")
            sinir = np.concatenate([[0], np.cumsum(say, dtype=np.int64)]) * 2
            goruntu[eksen] = [
                [(float(uc[a + 2 * i]), float(uc[a + 2 * i + 1])) for i in range((b - a) // 2)]
                for a, b in zip(sinir[:-1], sinir[1:], strict=True)
            ]
        out.append(goruntu)
    _son(veri, ofs, "Dexel dizisi")
    return out


def govde_ikili(model: MachineModel, ad: str) -> bytes:
    """Gövdenin üçgen ağı, kendi halkasının çerçevesinde (kutu: 12 üçgen; kapsül: `GOVDE_DILIM` dilimli).

    Biçim:
        başlık : uint32 sema, uint32 nv, uint32 nt
        V      : float32[nv·3]
        T      : uint32[nt·3]
    Bilinmeyen gövde → KeyError.
    """
    raise NotImplementedError("SPEC 47b: uygulanmadı")


def govde_coz(veri: bytes) -> dict[str, np.ndarray]:
    """→ {"V" (nv, 3), "T" (nt, 3)}. Sürüm / boy hatası → CamError."""
    (nv, nt), ofs = _baslik(veri, "Gövde ağı", 2)
    V, ofs = _oku(veri, ofs, "f4", 3 * nv, "Gövde ağı")
    T, ofs = _oku(veri, ofs, "u4", 3 * nt, "Gövde ağı")
    _son(veri, ofs, "Gövde ağı")
    return {"V": V.reshape(nv, 3), "T": T.reshape(nt, 3)}
