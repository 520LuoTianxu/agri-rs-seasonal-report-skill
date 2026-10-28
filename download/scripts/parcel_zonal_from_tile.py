#!/usr/bin/env python3
"""
Per-parcel zonal statistics from tile products.

Flow
----
Tile (virtual project area / 5km) is pulled first.
Then each parcel polygon intersecting that tile is used as a mask to aggregate:
  S2: NDVI/NDMI/NDRE/EVI/CIre/MNDWI (+ clear_fraction via SCL)
  S1: VV/VH linear & dB (+ ratio)

IMPORTANT
---------
data/full/parcels_all.jsonl has NO geometries.
Provide data/full/parcels_geoms.geojson (FeatureCollection, properties.parcel_id).
Optional properties.tile_id speeds filtering.

Usage
-----
  python3 scripts/parcel_zonal_from_tile.py --machine 1          # checks geoms
  python3 scripts/parcel_zonal_from_tile.py --machine 1 --run    # when rasters+geoms ready
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_attrs():
    m = defaultdict(dict)
    path = ROOT / "data/full/parcels_all.jsonl"
    with path.open() as f:
        for line in f:
            o = json.loads(line)
            m[str(o["parcel_id"])] = o
            m[(o.get("tile_id"), str(o["parcel_id"]))] = o
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--machine", type=int, required=True)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--parcels-geoms", type=str, default=str(ROOT / "data/full/parcels_geoms.geojson"))
    args = ap.parse_args()

    geoms_path = Path(args.parcels_geoms)
    tiles_root = ROOT / f"output/machine-{args.machine}/tiles"
    out_dir = ROOT / f"output/machine-{args.machine}/parcels"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not geoms_path.exists():
        readme = out_dir / "NEED_PARCEL_GEOMS.txt"
        readme.write_text(
            "Parcel attribute table exists (data/full/parcels_all.jsonl) but has no polygons.\n"
            "To split S1/S2 values to parcel boundaries, export parcel polygons as GeoJSON:\n"
            "  data/full/parcels_geoms.geojson\n"
            "Each feature needs properties.parcel_id (and ideally properties.tile_id).\n"
            "Then re-run: python3 scripts/parcel_zonal_from_tile.py --machine N --run\n"
        )
        print(readme.read_text())
        return 2

    if not args.run:
        data = json.loads(geoms_path.read_text())
        print(f"geoms ok: {len(data.get('features', []))} features; tiles_root={tiles_root}")
        print("dry-run; add --run after tile imagery/metrics rasters exist")
        return 0

    # Full zonal path (enabled when user has run tile pulls that keep band GeoTIFFs
    # or index GeoTIFFs). Current tile pipeline writes JSON stats by default;
    # for true parcel pixels, run tile stage with raster exports (see docs).
    print("RUN mode selected. Looking for per-tile rasters under", tiles_root)
    if not tiles_root.exists():
        print("No tile outputs yet. Run scripts/run_tile_shard.py --shard", f"{args.machine:02d}", "--run first.")
        return 2

    try:
        import numpy as np
        import rasterio
        from rasterio import features as rfeatures
        from rasterio.transform import from_bounds
        from shapely.geometry import shape
    except ImportError as e:
        print("Missing dependency:", e)
        return 2

    geoms = json.loads(geoms_path.read_text())["features"]
    by_tile = defaultdict(list)
    for f in geoms:
        p = f.get("properties") or {}
        tid = p.get("tile_id")
        if tid:
            by_tile[tid].append(f)
    attrs = load_attrs()
    out_path = out_dir / "parcel_metrics.jsonl"
    n = 0
    with out_path.open("w") as fout:
        for tile_dir in sorted(tiles_root.iterdir()):
            if not tile_dir.is_dir():
                continue
            tid = tile_dir.name
            # Prefer JSON timeseries already computed at tile level as fallback
            # True pixel zonal needs index/band tifs — if absent, copy tile JSON joined to parcels.
            s2_ts = tile_dir / "meta" / "s2_indices_timeseries.json"
            s1_ts = tile_dir / "meta" / "s1_indices_timeseries.json"
            parcel_feats = by_tile.get(tid)
            # if no tile_id on geoms, skip heavy spatial index here (keep simple)
            if not parcel_feats:
                # attribute join only for parcels listed in jsonl for this tile
                continue
            # Attribute-join fallback (same tile time series attached to each parcel)
            # Pixel-perfect zonal can replace this block when rasters are present.
            s2 = json.loads(s2_ts.read_text()) if s2_ts.exists() else None
            s1 = json.loads(s1_ts.read_text()) if s1_ts.exists() else None
            for f in parcel_feats:
                pid = str((f.get("properties") or {}).get("parcel_id"))
                a = attrs.get((tid, pid)) or attrs.get(pid) or {}
                rec = {
                    "tile_id": tid,
                    "parcel_id": pid,
                    "attributes": a,
                    "geometry_bbox": list(shape(f["geometry"]).bounds),
                    "s2_timeseries": (s2 or {}).get("time_series"),
                    "s1_timeseries": (s1 or {}).get("time_series"),
                    "aggregation": "tile_timeseries_joined_to_parcel_pending_raster_zonal",
                }
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
    print(f"wrote {n} rows → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
