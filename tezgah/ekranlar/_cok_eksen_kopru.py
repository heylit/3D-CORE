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

import dataclasses
import hashlib
import importlib
import json
import math
from collections import OrderedDict
from typing import TYPE_CHECKING

import numpy as np

from cam.model import CamError
from tezgah import SEMA
from tezgah.ekranlar._cok_eksen_ornekler import PARAMETRELER

if TYPE_CHECKING:
    from cam.model import Toolpath
    from cam.multiaxis.collision import MachineEvent
    from cam.multiaxis.machine import Body, Box, Capsule, MachineModel
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


# ---------------------------------------------------------------- ortak hesap (önbellekli)

_BELLEK: OrderedDict[tuple, tuple[object, object]] = OrderedDict()
BELLEK_BOYU = 32


def _bellek(tur: str, is_: CokEksenIsi, hesap):
    """`hesap(is_)` sonucunu işin içeriğine göre saklar. Anahtar: ad, profil, girdiler, kurulum ve takım
    sözlükleri ve yolların kimlikleri (örnekler yolları paylaşır; yollar değiştirilmez). Değer yolları da
    tutar, böylece kimlikler yeniden kullanılmaz."""
    yollar = (tuple(is_.ops), tuple(is_.ham))
    anahtar = (
        tur,
        parmak_izi(is_),
        json.dumps(is_.setup.to_dict(), sort_keys=True),
        json.dumps(is_.tool.to_dict(), sort_keys=True, default=str),
        tuple(map(id, yollar[0])),
        tuple(map(id, yollar[1])),
    )
    if anahtar in _BELLEK:
        _BELLEK.move_to_end(anahtar)
        return _BELLEK[anahtar][1]
    sonuc = hesap(is_)
    _BELLEK[anahtar] = (yollar, sonuc)
    while len(_BELLEK) > BELLEK_BOYU:
        _BELLEK.popitem(last=False)
    return sonuc


def _kaynak(is_: CokEksenIsi) -> list[Toolpath]:
    """Nokta dizisini üreten yollar: 5 eksen `ops`, 3+2 `ham` (frame'li yerel yol, `to_machine` girdisi)."""
    return list(is_.ops) if is_.tur == "5eksen" else list(is_.ham)


def _govdeler(model: MachineModel) -> list[Body]:
    """Görüntülenen gövdeler: tezgâhın kendi gövdeleri, sonra işin otomatik gövdeleri (`IsTezgahi`)."""
    return list(model.bodies) + list(getattr(model, "otomatik", ()))


def _eklemler(tp: Toolpath, kin, wcs, L: float) -> np.ndarray:
    """Yolun eklem değerleri (n+1, 3+k): SPEC 41 `to_machine` (= SPEC 42 `joint_path`); bir noktada sınır
    içinde çözüm yoksa SPEC 44 kuralı: o nokta sınırsız kinematikle, öncekinin açılarından devam."""
    from cam.multiaxis.indexed import to_machine, to_world
    from cam.multiaxis.kinematics import inverse
    from tezgah.ekranlar._cok_eksen_ornekler import serbest

    try:
        return np.asarray(to_machine(tp, kin, wcs, L), dtype=float)
    except CamError:
        pass
    w = to_world(tp)
    P = w.points()
    A = [m.axis for m in w.moves]
    A = [A[0] if A else (0.0, 0.0, 1.0)] + A
    kin_s = serbest(kin)
    Q, prev = [], None
    for p, a in zip(P, A, strict=True):
        try:
            q = inverse(kin, p, a, L, wcs, prev)
        except CamError:
            q = inverse(kin_s, p, a, L, wcs, prev)
        prev = tuple(float(v) for v in q[3:])
        Q.append(q)
    return np.array(Q)


def _g93(tp: Toolpath, q: np.ndarray) -> np.ndarray:
    """SPEC 42 `inverse_time` yalnız ilerlemeli hareketler için (koordinatör kararı): G0'lar feed = 1 ile
    hesaba girer (G0'da ilerleme yok, `inverse_time` onu reddeder), sonra 0 yazılır."""
    from cam.model import MoveType
    from cam.multiaxis.linearize import inverse_time

    hizli = np.array([m.type is MoveType.RAPID for m in tp.moves], dtype=bool)
    moves = [dataclasses.replace(m, feed=1.0) if h else m for m, h in zip(tp.moves, hizli, strict=True)]
    g = np.asarray(inverse_time(dataclasses.replace(tp, moves=moves), q), dtype=float)
    g[hizli] = 0.0
    return g


def _hesap_kur(is_: CokEksenIsi) -> dict:
    from cam.model import Move, MoveType, Plane
    from cam.multiaxis.indexed import to_world
    from cam.sim.timing import Machine, move_time

    kin, wcs, L = is_.model.kinematics, is_.setup.wcs, is_.L
    makine = Machine()
    Q, P, A, Z, ISL, H, G, araliklar = [], [], [], [], [], [], [], []
    k0, t = 0, 0.0
    onceki: np.ndarray | None = None
    for j, tp in enumerate(_kaynak(is_)):
        w = to_world(tp) if tp.frame is not None else tp
        if len(w.moves) != len(tp.moves):
            raise CamError(f"Çok eksen: '{tp.name}' yolunda yay var; nokta dizisi hareketlerle eşleşmez")
        p = w.points()
        a = [m.axis if m.axis is not None else (0.0, 0.0, 1.0) for m in w.moves]
        a = np.array([a[0]] + a, dtype=float)
        zaman = np.empty(len(p))
        if onceki is None:
            zaman[0] = t
        else:
            if np.array_equal(onceki, p[0]):
                raise CamError(
                    f"Çok eksen: '{tp.name}' önceki işlemin bittiği yerden başlıyor (bağlantı adımı yok)"
                )
            t += move_time(onceki, p[0], Move(MoveType.RAPID, tuple(p[0])), Plane.XY, makine)
            zaman[0] = t
        for i, m in enumerate(w.moves):
            t += move_time(p[i], p[i + 1], m, Plane.XY, makine)
            zaman[i + 1] = t
        q = _eklemler(tp, kin, wcs, L)
        g = np.concatenate([[0.0], _g93(tp, q)])
        hizli = np.array([j > 0] + [m.type is MoveType.RAPID for m in tp.moves], dtype=np.uint8)
        for liste, v in ((Q, q), (P, p), (A, a), (Z, zaman), (G, g), (H, hizli)):
            liste.append(v)
        ISL.append(np.full(len(p), j, dtype=np.int16))
        araliklar.append((k0, k0 + len(p) - 1))
        k0 += len(p)
        onceki = p[-1]
    return {
        "q": np.vstack(Q),
        "konum": np.vstack(P),
        "a": np.vstack(A),
        "zaman": np.concatenate(Z),
        "islem": np.concatenate(ISL),
        "hizli": np.concatenate(H),
        "g93": np.concatenate(G),
        "araliklar": araliklar,
    }


def _hesap(is_: CokEksenIsi) -> dict:
    """Nokta dizisinin bütün sütunları ve işlem aralıkları (k0, k1)."""
    return _bellek("hesap", is_, _hesap_kur)


def _olaylar(is_: CokEksenIsi) -> list[MachineEvent]:
    from cam.multiaxis.collision import check

    return _bellek(
        "olaylar",
        is_,
        lambda x: check(x.model, x.setup, list(x.ops), x.L, tcp=True, clearance=x.clearance),
    )


def _sapma_kur(is_: CokEksenIsi) -> dict:
    from cam.multiaxis.kinematics import forward
    from cam.multiaxis.linearize import deviation

    kin, wcs, L = is_.model.kinematics, is_.setup.wcs, is_.L
    H = _hesap(is_)
    u = (np.arange(SAPMA_ARA) + 1) / (SAPMA_ARA + 1)
    e, tcp = [], []
    for k0, k1 in H["araliklar"]:
        q, p, a = H["q"][k0 : k1 + 1], H["konum"][k0 : k1 + 1], H["a"][k0 : k1 + 1]
        for i in range(k1 - k0):
            e.append(deviation(kin, wcs, L, q[i], q[i + 1], p[i], p[i + 1], a[i], a[i + 1], 0.5))
            tcp.append([forward(kin, q[i] + ui * (q[i + 1] - q[i]), L, wcs)[0] for ui in u])
    return {
        "e": np.array(e, dtype=float).reshape(-1, 2),
        "tcp": np.array(tcp, dtype=float).reshape(-1, SAPMA_ARA, 3),
    }


def _sapma(is_: CokEksenIsi) -> dict:
    """Segment başına (e_p, e_a) ve TCP kapalı ara noktaları (float64)."""
    return _bellek("sapma", is_, _sapma_kur)


def _say(v) -> float | None:
    return None if v is None else float(v)


def _kontrol(kimlik, baslik, deger, birim, durum, aciklama, spec) -> dict:
    return {
        "kimlik": kimlik,
        "baslik": baslik,
        "deger": None if deger is None else float(deger),
        "birim": birim,
        "durum": durum,
        "aciklama": aciklama,
        "spec": spec,
    }


def _kutu_agi(b: Box) -> tuple[np.ndarray, np.ndarray]:
    """Kutunun 8 köşesi (center + R·(±half)) ve dışa bakan 12 üçgen."""
    s = np.array([[i, j, k] for i in (-1, 1) for j in (-1, 1) for k in (-1, 1)], dtype=float)
    V = np.array(b.center) + (s * np.array(b.half)) @ b.matrix.T
    yuzler = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    T = [t for a, b_, c, d in yuzler for t in ((a, b_, c), (a, c, d))]
    return V, np.array(T, dtype=np.int64)


def _kapsul_agi(c: Capsule) -> tuple[np.ndarray, np.ndarray]:
    """Kapsül: iki yarım küre (her biri `GOVDE_DILIM // 4` enlem halkası + kutup) ve aradaki silindir;
    her köşe p–q doğru parçasına tam r uzaklıkta."""
    p, q, r = np.array(c.p), np.array(c.q), c.r
    w = q - p
    boy = float(np.linalg.norm(w))
    z = w / boy if boy > 0 else np.array([0.0, 0.0, 1.0])
    x = np.cross(z, [1.0, 0.0, 0.0] if abs(z[0]) < 0.9 else [0.0, 1.0, 0.0])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    m, h = GOVDE_DILIM, max(1, GOVDE_DILIM // 4)
    al = 2 * math.pi * np.arange(m) / m
    halka = np.cos(al)[:, None] * x + np.sin(al)[:, None] * y  # (m, 3) birim
    V = [p - r * z]
    for i in range(1, h + 1):  # p yarım küresi: kutuptan ekvatora
        th = math.pi / 2 * i / h
        V += list(p - r * math.cos(th) * z + r * math.sin(th) * halka)
    for i in range(h, 0, -1):  # q yarım küresi: ekvatordan kutba
        th = math.pi / 2 * i / h
        V += list(q + r * math.cos(th) * z + r * math.sin(th) * halka)
    V.append(q + r * z)
    V = np.array(V)
    n_halka = 2 * h
    T = []
    for j in range(m):
        T.append((0, 1 + (j + 1) % m, 1 + j))
    for i in range(n_halka - 1):
        a0, b0 = 1 + i * m, 1 + (i + 1) * m
        for j in range(m):
            j1 = (j + 1) % m
            T += [(a0 + j, a0 + j1, b0 + j1), (a0 + j, b0 + j1, b0 + j)]
    son, ust = 1 + (n_halka - 1) * m, len(V) - 1
    for j in range(m):
        T.append((son + j, son + (j + 1) % m, ust))
    return V, np.array(T, dtype=np.int64)


# ---------------------------------------------------------------- JSON


def olaylar(is_: CokEksenIsi) -> list[dict]:
    """SPEC 44 `check(model, setup, ops, L, tcp=True, clearance=is_.clearance)` → olay sözlükleri
    (`kind, k, t, a, b, distance, detail`), aynı sırada ve değerde; ek alan `zaman` [s] =
    zaman[k−1] + t·(zaman[k] − zaman[k−1]) (k: SPEC 05 adım indeksi, t: hareket içi parametre; K10 eki)."""
    zaman = _hesap(is_)["zaman"]

    def ekle(e) -> dict:
        d = dataclasses.asdict(e)
        z0, z1 = float(zaman[e.k - 1]), float(zaman[e.k])
        d["zaman"] = z0 + e.t * (z1 - z0)
        return d

    return [ekle(e) for e in _olaylar(is_)]


def sapma_ozeti(is_: CokEksenIsi) -> dict:
    """`{"tol_p", "tol_a", "e_p_max", "e_a_max"}`: `ops`'un her segmentinde `deviation(..., t=0.5)`
    değerlerinin en büyükleri."""
    e = _sapma(is_)["e"]
    return {
        "tol_p": is_.tol_p,
        "tol_a": is_.tol_a,
        "e_p_max": float(e[:, 0].max()) if len(e) else 0.0,
        "e_a_max": float(e[:, 1].max()) if len(e) else 0.0,
    }


def kontroller(is_: CokEksenIsi, sim: list[SimResult5] | None = None) -> list[dict]:
    """Kanıt paneli (SPEC 47 "Kontroller (Çok eksen)"):

    `tezgah_carpma`, `eksen_siniri` (SPEC 44; olay sayısı > 0 → hata), `dogrusallastirma` (SPEC 42;
    `e_p_max > tol_p` ya da `e_a_max > tol_a` → hata). `sim` verilirse ek olarak `govde_carpma` (SPEC 43
    `collisions` > 0 → hata), `cakma` (`gouge_volume` > `GOUGE_TOL` → hata; parça yoksa yok), `sure` (bilgi,
    `tamam`). `sim` yoksa SPEC 43 kontrolleri listede yoktur.
    """
    olay = _olaylar(is_)
    out = []
    for kimlik, baslik, ne in (
        ("tezgah_carpma", "Tezgâh çarpışması", "gövde çifti"),
        ("eksen_siniri", "Eksen sınırı", "eksen"),
    ):
        e = [x for x in olay if x.kind == kimlik]
        if e:
            ilk = e[0]
            kim = f"{ilk.a} × {ilk.b}" if ilk.b else ilk.a
            aciklama = f"{len(e)} olay; ilki adım {ilk.k}, {ne} {kim}: {ilk.detail}"
        else:
            aciklama = "Olay yok"
        out.append(_kontrol(kimlik, baslik, len(e), "olay", "hata" if e else "tamam", aciklama, "SPEC 44"))
    oz = sapma_ozeti(is_)
    asim = oz["e_p_max"] > is_.tol_p or oz["e_a_max"] > is_.tol_a
    aciklama = (
        f"e_p = {oz['e_p_max']:.4g} mm (tol {is_.tol_p:g}), e_a = {oz['e_a_max']:.4g}° (tol {is_.tol_a:g})"
    )
    out.append(
        _kontrol(
            "dogrusallastirma",
            "Doğrusallaştırma sapması",
            oz["e_p_max"],
            "mm",
            "hata" if asim else "tamam",
            aciklama,
            "SPEC 42",
        )  # fmt: skip
    )
    if sim is None:
        return out
    oz = sim_ozeti(sim)
    c = oz["collisions"]
    aciklama = f"{len(c)} kayıt; ilki {c[0]['kind']} (adım {c[0]['k']})" if c else "Çarpışma yok"
    out.append(
        _kontrol(
            "govde_carpma", "Gövde çarpışması", len(c), "kayıt", "hata" if c else "tamam", aciklama, "SPEC 43"
        )
    )
    if oz["gouge_volume"] is not None:
        g = oz["gouge_volume"]
        durum = "hata" if g > GOUGE_TOL else "tamam"
        out.append(
            _kontrol(
                "cakma", "Çakma", g, "mm³", durum, f"Çakma hacmi {g:.4g} mm³ (eşik {GOUGE_TOL:g})", "SPEC 43"
            )
        )
    t = oz["total_time"]
    out.append(_kontrol("sure", "Süre", t, "s", "tamam", f"Simülasyon süresi {t:.1f} s", "SPEC 43"))
    return out


def sim_ozeti(sim: list[SimResult5]) -> dict:
    """Zincirleme `simulate5` sonuçları → `CokEksen["sim"]`: son sonucun `removed_volume` (V_stok − son
    `TriDexel.volume()`), `rest_volume()` / `gouge_volume()` (parça yoksa None), toplam süre,
    tüm çarpışmalar."""
    son = sim[-1]
    parca = son.part is not None
    return {
        "removed_volume": float(sum(r.removed_volume for r in sim)),
        "rest_volume": float(son.rest_volume()) if parca else None,
        "gouge_volume": float(son.gouge_volume()) if parca else None,
        "total_time": float(sum(r.total_time for r in sim)),
        "collisions": [dataclasses.asdict(c) for r in sim for c in r.collisions],
    }


def cok_json(is_: CokEksenIsi, sim: list[SimResult5] | None = None) -> dict:
    """`CokEksen` sözlüğü (modül belgesi). `sim` None → `"sim": None`."""
    from cam.multiaxis.machine import Box

    kin = is_.model.kinematics
    pr = is_.model.profile
    eksenler = []
    for ad, lim in (("X", pr.x), ("Y", pr.y), ("Z", pr.z)):
        eksenler.append(
            {"ad": ad, "tur": "dogrusal", "min": _say(lim and lim.min), "max": _say(lim and lim.max)}
        )
    for a in kin.rotary:
        eksenler.append({"ad": a.name, "tur": "doner", "min": _say(a.min), "max": _say(a.max)})
    govdeler = [
        {"ad": b.name, "halka": b.link, "sekil": "kutu" if isinstance(b.shape, Box) else "kapsul"}
        for b in _govdeler(is_.model)
    ]
    H = _hesap(is_)
    islemler = []
    for j, (tp, (k0, k1)) in enumerate(zip(_kaynak(is_), H["araliklar"], strict=True)):
        fr = is_.cerceveler[j] if j < len(is_.cerceveler) else None
        yon = is_.yonelimler[j] if j < len(is_.yonelimler) else None
        islemler.append(
            {
                "i": j,
                "ad": tp.name,
                "takim": tp.tool.name,
                "t0": float(H["zaman"][k0]),
                "t1": float(H["zaman"][k1]),
                "k0": k0,
                "k1": k1,
                "cerceve": None if fr is None else fr.to_dict(),
                "yonelim": None if yon is None else dataclasses.asdict(yon),
            }
        )
    return {
        "sema": SEMA,
        "ad": is_.ad,
        "tur": is_.tur,
        "profil": is_.profil,
        "tezgah": {"ad": pr.name, "eksenler": eksenler, "govdeler": govdeler},
        "wcs": is_.setup.wcs.to_dict(),
        "L": is_.L,
        "parametreler": {p: getattr(is_, p) for p in PARAMETRELER},
        "islemler": islemler,
        "olaylar": olaylar(is_),
        "sim": None if sim is None else sim_ozeti(sim),
        "sapma": sapma_ozeti(is_),
        "kontroller": kontroller(is_, sim),
    }


def parmak_izi(is_: CokEksenIsi, **ek: object) -> str:
    """Girdinin parmak izi: (ad, profil, `PARAMETRELER` değerleri, `ek`) JSON'unun SHA-256'sı (hex).
    Pahalı uçların (simule) önbellek anahtarı (SPEC 47 "Ortak veri kuralları", K21)."""
    girdi = {"ad": is_.ad, "profil": is_.profil, **{p: getattr(is_, p) for p in PARAMETRELER}, **ek}
    metin = json.dumps(girdi, sort_keys=True, allow_nan=False)
    return hashlib.sha256(metin.encode("utf-8")).hexdigest()


def parametre_uygula(is_: CokEksenIsi, anahtar: str, deger: float) -> CokEksenIsi:
    """`anahtar ∈ PARAMETRELER` değişmiş YENİ iş (örnek yeniden kurulur); `is_` değişmez.

    Bilinmeyen anahtar → CamError; geçersiz değer (`tol_p ≤ 0`, `L ≤ 0` …) → çekirdeğin hatası.
    """
    from tezgah.ekranlar._cok_eksen_ornekler import ornek

    if anahtar not in PARAMETRELER:
        raise CamError(f"Çok eksen: bilinmeyen parametre {anahtar!r} ({', '.join(PARAMETRELER)})")
    girdi = {p: getattr(is_, p) for p in PARAMETRELER}
    girdi[anahtar] = deger
    return ornek(is_.ad, is_.profil, **girdi)


def sure(is_: CokEksenIsi) -> float:
    """İşin toplam süresi [s] (nokta dizisindeki son kümülatif süre).
    `sure_farki = sure(yeni) − sure(eski)`."""
    return float(_hesap(is_)["zaman"][-1])


# ---------------------------------------------------------------- simülasyon


def simule(is_: CokEksenIsi, cell: float = SIM_HUCRE) -> list[SimResult5]:
    """Zincirleme tri-dexel: `simulate5([ops[0]], stock, cell, part=part)`, sonra her j için
    `simulate5([ops[j]], stock, cell, part=part, initial=önceki.tridexel)`. İşlem başına bir sonuç."""
    from cam.sim.simulate5 import simulate5

    out: list[SimResult5] = []
    for op in is_.ops:
        onceki = out[-1].tridexel if out else None
        out.append(simulate5([op], is_.stock, cell, part=is_.part, initial=onceki))
    return out


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
    H = _hesap(is_)
    n, k = len(H["zaman"]), len(is_.model.kinematics.rotary)
    return b"".join(
        [
            _baslik_ikili(n, k),
            _blok(H["konum"].astype(np.float32).ravel()),
            _blok(H["zaman"].astype(np.float64)),
            _blok(H["islem"].astype(np.int16)),
            _blok(H["hizli"].astype(np.uint8)),
            _blok(H["a"].astype(np.float32).ravel()),
            _blok(H["q"].astype(np.float64).ravel()),
            _blok(H["g93"].astype(np.float32)),
        ]
    )


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
    from cam.multiaxis.machine import poses

    halka = [b.link for b in _govdeler(is_.model)]
    Q = _hesap(is_)["q"]
    P = np.empty((len(Q), len(halka), 12), dtype=np.float32)
    for i, q in enumerate(Q):
        d = poses(is_.model, q, is_.setup, is_.tool)
        for b, h in enumerate(halka):
            R, t = d[h]
            P[i, b, :9] = np.asarray(R).astype(np.float32).ravel()
            P[i, b, 9:] = np.asarray(t).astype(np.float32)
    return _baslik_ikili(len(Q), len(halka)) + _blok(P.ravel())


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
    S = _sapma(is_)
    e, tcp = S["e"], S["tcp"]
    return b"".join(
        [
            _baslik_ikili(len(e), SAPMA_ARA),
            _blok(e.astype(np.float32).ravel()),
            _blok(tcp.astype(np.float32).ravel()),
        ]
    )


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
    parca = [_baslik_ikili(len(dexeller))]
    for T in dexeller:
        parca.append(_blok(np.array([T.x0, T.y0, T.z0, T.dx, T.dy, T.dz], dtype=np.float64)))
        parca.append(_blok(np.array([T.nx, T.ny, T.nz], dtype=np.uint32)))
        for eksen, (dis, ic) in (("z", (T.nx, T.ny)), ("x", (T.ny, T.nz)), ("y", (T.nx, T.nz))):
            araliklar = [T.intervals(eksen, i, j) for i in range(dis) for j in range(ic)]
            sayi = np.array([len(a) for a in araliklar], dtype=np.int64)
            if sayi.size and sayi.max() > np.iinfo(np.uint16).max:
                raise CamError(f"Dexel dizisi: bir ışında {int(sayi.max())} aralık (uint16 sınırı aşıldı)")
            uc = [v for a in araliklar for ab in a for v in ab]
            parca.append(_blok(np.array([len(araliklar)], dtype=np.uint32)))
            parca.append(_blok(sayi.astype(np.uint16)))
            parca.append(_blok(np.array(uc, dtype=np.float32)))
    return b"".join(parca)


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
    from cam.multiaxis.machine import Box

    govde = {b.name: b for b in _govdeler(model)}.get(ad)
    if govde is None:
        raise KeyError(ad)
    V, T = _kutu_agi(govde.shape) if isinstance(govde.shape, Box) else _kapsul_agi(govde.shape)
    return b"".join(
        [
            _baslik_ikili(len(V), len(T)),
            _blok(V.astype(np.float32).ravel()),
            _blok(T.astype(np.uint32).ravel()),
        ]
    )


def govde_coz(veri: bytes) -> dict[str, np.ndarray]:
    """→ {"V" (nv, 3), "T" (nt, 3)}. Sürüm / boy hatası → CamError."""
    (nv, nt), ofs = _baslik(veri, "Gövde ağı", 2)
    V, ofs = _oku(veri, ofs, "f4", 3 * nv, "Gövde ağı")
    T, ofs = _oku(veri, ofs, "u4", 3 * nt, "Gövde ağı")
    _son(veri, ofs, "Gövde ağı")
    return {"V": V.reshape(nv, 3), "T": T.reshape(nt, 3)}
