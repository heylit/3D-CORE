"""SPEC 57 §4 — En az bağlama: tam küme örtüsü."""

from __future__ import annotations

import itertools
from collections.abc import Hashable, Iterator


def covers(universe: set, cover: dict[Hashable, set]) -> Iterator[tuple[Hashable, ...]]:
    """Örtülebilen elemanları örten alt kümeler: önce boyut, boyut içinde `cover` ekleme sırası (sözlük)."""
    keys = list(cover)
    hedef = set(universe) & set().union(*cover.values()) if keys else set()
    for k in range(len(keys) + 1):
        for alt in itertools.combinations(keys, k):
            if hedef <= set().union(*(cover[a] for a in alt)):
                yield alt


def min_cover(universe: set, cover: dict[Hashable, set]) -> tuple[Hashable, ...]:
    """Tam arama ile en küçük örtü; örtülemeyen eleman varsa örtülebilenlerin en küçük örtüsü.

    Örtülemeyen kalan dönmez; çağıran `universe − ⋃ cover[k]` ile bulur (durum/57 netleştirme 3).
    """
    return next(covers(universe, cover))
