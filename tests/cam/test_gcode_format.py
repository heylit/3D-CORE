"""SPEC 04 — sayı biçimi `fmt` ve hazır `Dialect` örnekleri (K1).

Testler sadece SPEC 04 metninden (Teori "Sayı biçimi ve tolerans", "Kontrolör farkları" tablosu,
Arayüz) yazıldı; `cam/gcode/` uygulama kodu okunmadı.

Kural (SPEC 04): koordinat `d` ondalık basamakla, her zaman ondalık noktalı (`10.`, `-2.5`, `0.`);
`-0.` yazılmaz. Gereksiz sondaki sıfırlar yazılmaz (`-2.5`, `-2.500` değil: SPEC örneği).
"""

from __future__ import annotations

import dataclasses

import pytest

from cam.gcode import FANUC, GRBL, Dialect, ModalState, fmt

# ---------------------------------------------------------------- K1: fmt


@pytest.mark.parametrize(
    "v, d, beklenen",
    [
        # SPEC 04 K1'in dört örneği birebir
        (10, 3, "10."),
        (-2.5, 3, "-2.5"),
        (-0.0001, 3, "0."),       # -0.0001 → 3 basamakta -0.000 → "-0." yasak → "0."
        (1.23456, 3, "1.235"),    # 1.23456 → 1.235 (4. basamak 5, sonrası 6: yukarı)
    ],
)
def test_fmt_spec_examples(v, d, beklenen):
    assert fmt(v, d) == beklenen


@pytest.mark.parametrize(
    "v, d, beklenen",
    [
        (0.0, 3, "0."),            # sıfır noktalı yazılır
        (-0.0, 3, "0."),           # IEEE eksi sıfır da "0."
        (-0.0004, 3, "0."),        # |v| < 0.5e-3 → sıfıra yuvarlanır, işaret düşer
        (100.0, 1, "100."),        # F biçimi (feed_decimals = 1)
        (300.04, 1, "300."),       # 300.04 → 300.0 → "300."
        (12.3456789, 1, "12.3"),
        (2.0004, 3, "2."),         # 2.0004 → 2.000 → sondaki sıfırlar atılır
        (-1.9996, 3, "-2."),       # -1.9996 → -2.000
        (1234.5, 3, "1234.5"),
        (123456.789, 3, "123456.789"),  # büyük sayı: bilimsel gösterim yok
        (1e-7, 3, "0."),           # küçük sayı: bilimsel gösterim yok (1e-07 değil)
        (0.5, 3, "0.5"),           # karar: baştaki sıfır yazılır (Python biçimi), ".5" değil
        (-0.25, 3, "-0.25"),
    ],
)
def test_fmt_more_cases(v, d, beklenen):
    assert fmt(v, d) == beklenen


def test_fmt_error_bound_is_half_ulp():
    """Teori: yuvarlama hatası koordinat başına ≤ ε = 0.5·10^-d (d = 3 → 5e-4 mm).

    -0.25..0.25 aralığındaki düzensiz ızgaradaki her değer için |float(fmt(v)) − v| ≤ ε + 1e-12.
    """
    d = 3
    eps = 0.5 * 10.0**-d
    for k in range(-2000, 2001, 7):
        v = k * 0.000123 + 0.0000371
        s = fmt(v, d)
        assert "." in s
        assert "e" not in s.lower()
        assert s != "-0."
        assert abs(float(s) - v) <= eps + 1e-12


# ---------------------------------------------------------------- Dialect örnekleri


def test_dialect_presets_match_spec_table():
    """SPEC 04 "Kontrolör farkları" tablosu: basamak 3/1, satır no, çevrim, c = 0.5 mm."""
    assert isinstance(GRBL, Dialect)
    assert isinstance(FANUC, Dialect)

    assert GRBL.decimals == 3
    assert GRBL.feed_decimals == 1
    assert GRBL.line_numbers is False
    assert GRBL.canned_cycles is False
    assert GRBL.peck_clearance == pytest.approx(0.5, rel=1e-12)

    assert FANUC.decimals == 3
    assert FANUC.feed_decimals == 1
    assert FANUC.line_numbers is True
    assert FANUC.line_step == 10
    assert FANUC.canned_cycles is True
    assert FANUC.peck_clearance == pytest.approx(0.5, rel=1e-12)


def test_dialect_is_frozen():
    """Arayüz: `@dataclass(frozen=True) Dialect`; hazır örnek değiştirilemez."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        GRBL.decimals = 4  # type: ignore[misc]
    yeni = dataclasses.replace(GRBL, peck_clearance=1.0)
    assert yeni.peck_clearance == 1.0
    assert GRBL.peck_clearance == pytest.approx(0.5, rel=1e-12)


def test_modal_state_exported():
    """Arayüz: `ModalState` sınıfı `cam.gcode`'dan dışa açılır."""
    assert isinstance(ModalState, type)
