#!/usr/bin/env python3
"""
Process one machine shard of 5km tiles:
  1) For each tile polygon → pull S2/S1 AOI metrics (JSON)
  2) Optionally zonal-stats into each parcel polygon (requires parcels_geoms.geojson)

Default is DRY-RUN (list work only). Pass --run to actually download.

Examples:
  python3 scripts/run_tile_shard.py --shard 01                 # dry-run
  python3 scripts/run_tile_shard.py --shard 01 --run --limit 2 # real, 2 tiles
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load_shard(shard_id: str):
    path = ROOT / "data" / "shards" / f"shard_{shard_id}.geojson"
    data = json.loads(path.read_text())
    return path, data["features"]


def tile_center(feat):
    ring = feat["geometry"]["coordinates"][0]
    xs = [c[0] for c in ring]
    ys = [c[1] for c in ring]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", required=True, help="01|02|03")
    ap.add_argument("--run", action="store_true", help="actually pull S1/S2 (default dry-run)")
    ap.add_argument("--limit", type=int, default=0, help="only first N tiles")
    ap.add_argument("--start", default="2021-01-01")
    ap.add_argument("--end", default="today")
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--s2-rgb", action="store_true")
    ap.add_argument("--s2-only", action="store_true")
    ap.add_argument("--s1-only", action="store_true")
    args = ap.parse_args()

    shard_id = f"{int(args.shard):02d}"
    path, feats = load_shard(shard_id)
    if args.limit > 0:
        feats = feats[: args.limit]
    outdir = ROOT / "output" / f"machine-{int(shard_id)}" / "tiles"
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"shard={shard_id} file={path} n_tiles={len(feats)} run={args.run}")
    print("NOTE: parcel pixel split needs data/full/parcels_geoms.geojson (not bundled attributes-only jsonl)")

    if not args.run:
        for i, f in enumerate(feats[:5], 1):
            p = f["properties"]
            lon, lat = tile_center(f)
            print(f"  sample[{i}] tile_id={p.get('tile_id')} lon={lon:.5f} lat={lat:.5f} county={p.get('county_name')}")
        print(f"dry-run only. To execute: add --run (writes under {outdir})")
        return 0

    # Lazy import heavy pipeline only when running
    import s1_s2_indices_pipeline as pipe

    for i, f in enumerate(feats, 1):
        props = f["properties"]
        tile_id = props["tile_id"]
        lon, lat = tile_center(f)
        tile_out = outdir / tile_id
        tile_out.mkdir(parents=True, exist_ok=True)
        (tile_out / "tile_properties.json").write_text(json.dumps(props, ensure_ascii=False, indent=2))
        print(f"[{i}/{len(feats)}] RUN {tile_id} ({lon:.5f},{lat:.5f})", flush=True)
        argv = [
            "--lon", str(lon), "--lat", str(lat),
            "--half-km", "2.5",
            "--start", args.start, "--end", args.end,
            "--workers", str(args.workers),
            "--outdir", str(tile_out),
        ]
        if args.s2_rgb:
            argv.append("--s2-rgb")
        if args.s2_only:
            argv.append("--s2-only")
        if args.s1_only:
            argv.append("--s1-only")
        pipe.main(argv)
    print("DONE shard", shard_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
