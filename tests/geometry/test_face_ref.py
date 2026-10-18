"""A2 arayüz eki — geometry/part.py: FaceRef, Part.names, Part.find, Part.face_refs.

Testler sadece onaylı A2 önerisinden (arayuz/A2-yuz-referansi-onerisi.md) ve geometry/part.py'nin mevcut
arayüzünden yazıldı; uygulama kodu okunmadı. FaceRef testleri saf Python; Part testleri OCCT gerektirir.
Uydurma geometri: build123d Box(10, 20, 30) → 6 düzlemsel yüz, OCCT yüz indeksleri 0..5.
"""

from __future__ import annotations

import dataclasses
import inspect

import numpy as np
import pytest

import geometry.part as gp
from geometry.part import GeometryError, Part

A, B, C = 10.0, 20.0, 30.0  # kutu kenarları [mm]
N_YUZ = 6  # kutunun yüz sayısı


def faceref_cls():
    """geometry.part.FaceRef. A2 iskeleti main'e girene kadar yok: o zaman NotImplementedError, yani test
    yerelde "uygulanmamış", CI'da (--uygulanmamis-hata) kırmızı. Atlanmaz."""
    cls = getattr(gp, "FaceRef", None)
    if cls is None:
        raise NotImplementedError("A2: geometry.part.FaceRef henüz yok")
    return cls


def part_names_var() -> None:
    """Part.__init__'te names parametresi yoksa (A2 iskeleti öncesi) NotImplementedError, TypeError değil."""
    if "names" not in inspect.signature(Part.__init__).parameters:
        raise NotImplementedError("A2: Part(names=...) henüz yok")


def ref(feature, name):
    return faceref_cls()(feature, name)


def TABAN():
    return ref("cep1", "taban")


def YAN():
    return ref("cep1", "yan")


def GIRIS():
    return ref("delik2", "giris")


def kutu(names=None, name: str = "kutu") -> Part:
    from build123d import Box

    part_names_var()
    return Part(Box(A, B, C), name=name, names=names)


# ---------- FaceRef (saf Python) ----------


def test_faceref_str():
    """str → "feature:name"."""
    assert str(ref("cep1", "son")) == "cep1:son"


def test_faceref_name_slash_allowed():
    """name '/' içerebilir."""
    r = ref("cep1", "duvar/2")
    assert r.name == "duvar/2"
    assert str(r) == "cep1:duvar/2"


def test_faceref_parse_roundtrip():
    r = faceref_cls().parse("cep1:son")
    assert r == ref("cep1", "son")
    assert r.feature == "cep1" and r.name == "son"
    assert faceref_cls().parse(str(ref("delik2", "duvar/2"))) == ref("delik2", "duvar/2")


def test_faceref_parse_splits_at_first_colon():
    """Bölme ilk ':'ten: feature ':' içeremez, kalan her şey name'e gider."""
    r = faceref_cls().parse("cep1:a:b")
    assert r.feature == "cep1"
    assert r.name == "a:b"
    assert faceref_cls().parse(str(r)) == r


@pytest.mark.parametrize("s", ["cep1", "", ":son", "cep1:", "a/b:son", ":"])
def test_faceref_parse_invalid(s):
    """Biçim dışı → GeometryError: ':' yok, boş feature / name, feature'da '/'."""
    with pytest.raises(GeometryError):
        faceref_cls().parse(s)


@pytest.mark.parametrize(
    "feature, name",
    [("", "son"), ("cep1", ""), ("cep:1", "son"), ("cep/1", "son"), (1, "son"), ("cep1", 2)],
)
def test_faceref_invalid_fields(feature, name):
    """feature boş değil, ':' ve '/' içermez; name boş değil; alanlar str."""
    with pytest.raises(GeometryError):
        ref(feature, name)


def test_faceref_frozen():
    r = ref("cep1", "son")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.feature = "cep2"  # type: ignore[misc]


def test_faceref_value_equality_and_hash():
    a = ref("cep1", "son")
    b = ref("cep1", "son")
    assert a == b
    assert hash(a) == hash(b)
    assert a != ref("cep1", "taban")
    assert a != ref("cep2", "son")
    assert {a: 1}[b] == 1
    assert len({a, b, ref("cep1", "taban")}) == 2


# ---------- Part.names ----------


@pytest.mark.occt
def test_names_default_empty():
    """names verilmezse (None) boş eşleme; find her ad için hata."""
    p = kutu()
    assert len(p.names) == 0
    assert dict(p.names) == {}
    with pytest.raises(GeometryError):
        p.find(TABAN())


@pytest.mark.occt
def test_names_stored_and_find():
    p = kutu({TABAN(): (0,), YAN(): (1, 2, 3), GIRIS(): (2,)})
    assert dict(p.names) == {TABAN(): (0,), YAN(): (1, 2, 3), GIRIS(): (2,)}
    assert p.find(TABAN()) == (0,)
    assert p.find(YAN()) == (1, 2, 3)
    assert p.find(ref("cep1", "yan")) == (1, 2, 3)  # değer eşitliğiyle arama
    assert isinstance(p.find(YAN()), tuple)


@pytest.mark.occt
def test_names_positional_order():
    """Part(shape, name, holes, names) sırası."""
    from build123d import Box

    part_names_var()
    p = Part(Box(A, B, C), "kutu", (), {TABAN(): (5,)})
    assert p.find(TABAN()) == (5,)


@pytest.mark.occt
def test_names_read_only():
    p = kutu({TABAN(): (0,)})
    with pytest.raises(TypeError):
        p.names[GIRIS()] = (1,)  # type: ignore[index]
    with pytest.raises(TypeError):
        del p.names[TABAN()]  # type: ignore[attr-defined]
    assert dict(p.names) == {TABAN(): (0,)}


@pytest.mark.occt
def test_names_not_aliased_to_input():
    """Girdi sözlüğü sonradan değişse de parçanın adları değişmez."""
    d = {TABAN(): (0,)}
    p = kutu(d)
    d[GIRIS()] = (1,)
    d[TABAN()] = (4,)
    assert dict(p.names) == {TABAN(): (0,)}


@pytest.mark.occt
def test_find_missing_message():
    p = kutu({TABAN(): (0,)})
    with pytest.raises(GeometryError, match="referans bulunamadı") as e:
        p.find(GIRIS())
    assert "delik2:giris" in str(e.value)


@pytest.mark.occt
def test_indices_match_face_order():
    """İndeksler PlanarFace.index ile aynı OCCT yüz sırası: 0..N_YUZ-1 hepsi geçerli."""
    p0 = kutu()
    idx = sorted(f.index for f in p0.planar_faces())
    assert idx == list(range(N_YUZ))
    p = kutu({TABAN(): tuple(idx)})
    assert p.find(TABAN()) == tuple(range(N_YUZ))


# ---------- Doğrulama ----------


@pytest.mark.occt
@pytest.mark.parametrize(
    "names",
    [
        lambda: {"cep1:taban": (0,)},  # anahtar FaceRef değil
        lambda: {("cep1", "taban"): (0,)},
        lambda: {TABAN(): ()},  # boş demet
        lambda: {TABAN(): (2, 1)},  # artan değil
        lambda: {TABAN(): (1, 1)},  # tekrarlı
        lambda: {TABAN(): (0, 2, 2)},
        lambda: {TABAN(): (N_YUZ,)},  # aralık dışı
        lambda: {TABAN(): (-1,)},
        lambda: {TABAN(): (0,), YAN(): (0, 99)},
    ],
)
def test_names_invalid(names):
    """names her test içinde kurulur (FaceRef toplama aşamasında çağrılmaz)."""
    adlar = names()
    with pytest.raises(GeometryError):
        kutu(adlar)


# ---------- face_refs (ters arama) ----------


@pytest.mark.occt
def test_face_refs_reverse_lookup():
    """Bir yüz birden çok ada, bir ad birden çok yüze gidebilir; sonuç ada göre sıralı."""
    p = kutu({YAN(): (1, 2), GIRIS(): (2,), TABAN(): (2, 4)})
    assert p.face_refs(2) == (TABAN(), YAN(), GIRIS())
    assert p.face_refs(1) == (YAN(),)
    assert p.face_refs(4) == (TABAN(),)


@pytest.mark.occt
def test_face_refs_unnamed_face():
    p = kutu({TABAN(): (0,)})
    assert p.face_refs(3) == ()
    assert kutu().face_refs(0) == ()


@pytest.mark.occt
@pytest.mark.parametrize("index", [N_YUZ, -1, 100])
def test_face_refs_out_of_range(index):
    p = kutu({TABAN(): (0,)})
    with pytest.raises(GeometryError):
        p.face_refs(index)


# ---------- Taşıma ve uyumluluk ----------


@pytest.mark.occt
def test_moved_keeps_names():
    """moved(T) adları olduğu gibi taşır (topoloji aynı)."""
    adlar = {TABAN(): (0,), YAN(): (1, 3)}
    p = kutu(adlar)
    T = np.eye(4)
    T[:3, 3] = [100.0, -50.0, 7.0]
    c, s = np.cos(0.3), np.sin(0.3)
    T[:2, :2] = [[c, -s], [s, c]]
    q = p.moved(T)
    assert dict(q.names) == adlar
    assert q.find(YAN()) == (1, 3)
    assert q.face_refs(3) == (YAN(),)


@pytest.mark.occt
def test_boolean_results_unnamed():
    """cut / fuse / common adsız Part döndürmeye devam eder (ad taşıma SPEC 18'de)."""
    from build123d import Box, Pos

    p = kutu({TABAN(): (0,)})
    part_names_var()
    alet = Part(Pos(A / 2, 0, 0) * Box(A, B / 2, C / 2), name="alet", names={GIRIS(): (0,)})
    assert len(p.cut(alet).names) == 0
    assert len(p.fuse(alet).names) == 0
    k = p.common(alet)
    assert k is not None
    assert len(k.names) == 0


@pytest.mark.occt
def test_step_roundtrip_drops_names(tmp_path):
    """Adlar STEP gidiş-dönüşünde taşınmaz."""
    p = kutu({TABAN(): (0,), YAN(): (1, 2)})
    yol = tmp_path / "kutu.step"
    p.to_step(yol)
    q = Part.from_step(yol)
    assert len(q.names) == 0
    with pytest.raises(GeometryError):
        q.find(TABAN())


@pytest.mark.occt
def test_stl_export_with_names(tmp_path):
    """Adlı parça STL'e yazılabilir (adlar dosyaya girmez; STL geri okunmaz)."""
    p = kutu({TABAN(): (0,)})
    yol = tmp_path / "kutu.stl"
    p.to_stl(yol)
    assert yol.stat().st_size > 0
