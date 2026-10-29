# -*- coding: utf-8 -*-
"""Parcel overlap dedup: status=1 beats 0; same status → higher land_id wins.

Each parcel (high→low priority) keeps original_boundary − union(higher-priority).
After clip: remaining < min_mu 亩 OR buffer(-shrink_m) empty → 被合并.
Area in projected CRS: mu = area_m2 / 666.667.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely.geometry import MultiPolygon, mapping, shape
from shapely.ops import transform as stf, unary_union
from shapely.validation import make_valid

MU_PER_M2 = 666.667


def status_map_from_lands(path: str) -> Dict[str, int]:
    """land_id (str) → land_status (0/1) from lands_*.json list or dict."""
    raw = json.load(open(path))
    out: Dict[str, int] = {}
    if isinstance(raw, list):
        for row in raw:
            lid = str(row.get('land_id') or row.get('id') or '')
            if not lid:
                continue
            st = row.get('land_status', row.get('status', 1))
            out[lid] = int(st)
    elif isinstance(raw, dict):
        for lid, row in raw.items():
            if isinstance(row, dict):
                st = row.get('land_status', row.get('status', 1))
                out[str(lid)] = int(st)
            else:
                out[str(lid)] = int(row)
    else:
        raise TypeError(f'unsupported lands json type: {type(raw)}')
    return out


def _polys(g):
    if g is None or g.is_empty:
        return []
    if g.geom_type == 'Polygon':
        return [g] if g.area > 0 else []
    if g.geom_type == 'MultiPolygon':
        return [q for q in g.geoms if q.geom_type == 'Polygon' and q.area > 0]
    # GeometryCollection / others
    out = []
    for q in getattr(g, 'geoms', []):
        out.extend(_polys(q))
    return out


def _as_multi(g):
    ps = _polys(g)
    if not ps:
        return MultiPolygon([])
    if len(ps) == 1:
        return ps[0]
    return MultiPolygon(ps)


def dedup_parcels(
    parcels: Sequence[dict],
    status_by_id: Dict[str, int],
    epsg: int,
    min_mu: float = 0.3,
    shrink_m: float = 5.0,
) -> Tuple[List[dict], List[dict], dict]:
    """Return (keep, merged, summary). Clipped geom is WGS84 GeoJSON mapping."""
    to = Transformer.from_crs(4326, epsg, always_xy=True).transform
    back = Transformer.from_crs(epsg, 4326, always_xy=True).transform

    rows: List[dict] = []
    missing_status = 0
    for p in parcels:
        lid = str(p.get('land_id', ''))
        if lid not in status_by_id:
            missing_status += 1
            st = 1  # default enable if unknown
        else:
            st = int(status_by_id[lid])
        g0 = make_valid(shape(p['geom']))
        u = make_valid(stf(to, g0).buffer(0))
        rows.append({
            'land_id': lid,
            'name': p.get('name', ''),
            'village': p.get('village', ''),
            'town': p.get('town', ''),
            'county': p.get('county', ''),
            'land_status': st,
            'orig_mu': round(float(p.get('mu') or 0), 2),
            'orig_mu_geom': round(u.area / MU_PER_M2, 2) if not u.is_empty else 0.0,
            '_u': u,
            '_src': p,
        })

    before_n = len(rows)
    before_mu = round(sum(r['orig_mu'] for r in rows), 2)
    rows.sort(key=lambda r: (int(r['land_status'] == 1), int(r['land_id'] or 0)), reverse=True)

    keep: List[dict] = []
    merged: List[dict] = []
    done: List[dict] = []

    for rank, r in enumerate(rows, 1):
        g = r['_u']
        cov = []
        for q in done:
            try:
                inter = q['_u'].intersection(g)
                if inter.area > 1.0:  # m²
                    tag = '启用' if q['land_status'] == 1 else '停用'
                    cov.append(f"{q['land_id']}({tag})")
            except Exception:
                pass
        if done:
            hits = [q['_u'] for q in done if q['_u'].intersects(g)]
            U = unary_union(hits) if hits else None
        else:
            U = None
        if U is None or U.is_empty:
            rem = g
        else:
            rem = g.difference(U)
        if rem is None or rem.is_empty:
            rem = MultiPolygon([])
        else:
            rem = make_valid(rem.buffer(0))
            rem = _as_multi(rem)

        a_mu = rem.area / MU_PER_M2 if (rem and not rem.is_empty) else 0.0
        drop = (a_mu < min_mu) or rem.is_empty
        if not drop:
            try:
                if rem.buffer(-float(shrink_m)).is_empty:
                    drop = True
            except Exception:
                drop = True

        out = {
            'land_id': r['land_id'],
            'name': r['name'],
            'mu': round(a_mu, 2),
            'village': r['village'],
            'town': r['town'],
            'county': r['county'],
            'land_status': r['land_status'],
            'orig_mu': r['orig_mu'],
            'covered_by': ','.join(cov),
            'rank': rank,
        }
        if drop:
            out['merged'] = True
            merged.append(out)
        else:
            out['geom'] = mapping(stf(back, rem))
            out['merged'] = False
            keep.append(out)
        # keep projected geom on done for further clipping (use original u, not rem)
        done.append({'_u': g, 'land_id': r['land_id'], 'land_status': r['land_status']})

    after_mu = round(sum(p['mu'] for p in keep), 2)
    summary = {
        'before_n': before_n,
        'before_mu': before_mu,
        'kept_n': len(keep),
        'kept_mu': after_mu,
        'merged_n': len(merged),
        'merged_mu_orig': round(sum(p['orig_mu'] for p in merged), 2),
        'mu_removed': round(before_mu - after_mu, 2),
        'kept_by_status': {
            '1': sum(1 for p in keep if p['land_status'] == 1),
            '0': sum(1 for p in keep if p['land_status'] == 0),
        },
        'merged_by_status': {
            '1': sum(1 for p in merged if p['land_status'] == 1),
            '0': sum(1 for p in merged if p['land_status'] == 0),
        },
        'missing_status': missing_status,
        'epsg': epsg,
        'min_mu': min_mu,
        'shrink_m': shrink_m,
        'rule': 'status=1 > status=0; same status → higher land_id; clip high→low; <0.3亩 or buffer(-5m) empty → 被合并',
    }
    return keep, merged, summary


def rasterize_lab(
    keep: Sequence[dict],
    x0: float,
    y1: float,
    out_shape: Tuple[int, int],
    epsg: int,
    res: float,
) -> np.ndarray:
    """LAB labels 1..len(keep). Paint high priority first onto empty cells only.

    keep is assumed already ordered high→low priority (as returned by dedup_parcels).
    """
    H, W = out_shape
    LAB = np.zeros((H, W), dtype=np.int32)
    if not keep:
        return LAB
    tr = from_origin(x0, y1, res, res)
    to = Transformer.from_crs(4326, epsg, always_xy=True).transform
    # paint high priority first: first non-zero wins → iterate keep in order,
    # only write where LAB==0
    for i, p in enumerate(keep, 1):
        g = make_valid(stf(to, shape(p['geom'])).buffer(0))
        if g.is_empty:
            continue
        mask = rasterize(
            [(mapping(g), 1)],
            out_shape=(H, W),
            transform=tr,
            fill=0,
            dtype=np.uint8,
            all_touched=False,
        ).astype(bool)
        write = mask & (LAB == 0)
        LAB[write] = i
    return LAB
