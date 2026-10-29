# -*- coding: utf-8 -*-
"""Same-season ring rank lookup for mixed spring/summer projects.
Precomputed by scripts/compute_season_ring_rank.py → data/season_ring_rank.json.
"""
from __future__ import annotations
import json
import os

from catalog import DATA, ROOT

CACHE = os.path.join(DATA, 'season_ring_rank.json')
_CACHE = None


def _load():
    global _CACHE
    if _CACHE is None:
        if os.path.exists(CACHE):
            _CACHE = json.load(open(CACHE, encoding='utf-8'))
        else:
            _CACHE = {}
    return _CACHE


def season_ranks(key: str) -> dict:
    """Return {year: {spring: {...}, summer: {...}}} or {}."""
    return (_load().get(key) or {}).get('years') or {}


def season_rank_pct(key: str, season: str, year: str = '2026'):
    """Return int rank_pct for season or None if missing."""
    y = season_ranks(key).get(year) or {}
    info = y.get(season) or {}
    r = info.get('rank')
    if r is None:
        return None
    try:
        return int(round(float(r)))
    except (TypeError, ValueError):
        return None


def season_y3_ranks(key: str, season: str):
    """rank24/25/26 for one season (int|None)."""
    out = {}
    for y, field in (('2024', 'rank24'), ('2025', 'rank25'), ('2026', 'rank26')):
        out[field] = season_rank_pct(key, season, y)
    return out
