#!/usr/bin/env python3
"""
Sentinel-1 + Sentinel-2 AOI pipeline (Microsoft Planetary Computer)

What it does
------------
1) Sentinel-2 L2A (COG, windowed read):
   - bands B02,B03,B04,B05,B08,B11,SCL
   - indices → JSON: NDVI, NDMI, NDRE, EVI, CIre, MNDWI
   - optional true-color (B04/B03/B02) PNG per scene
2) Sentinel-1 RTC (COG, windowed read):
   - VV / VH linear γ0 → JSON stats (linear + dB)
   - optional skip writing GeoTIFFs (default: stats only)

Default AOI: 5×5 km around a lon/lat (UTM clip @ 10 m for S2 / S1).
Default time: 2021-01-01 → today (UTC).

Examples
--------
  python3 s1_s2_indices_pipeline.py \\
    --lon 116.23486328125 --lat 41.19681661208149 \\
    --start 2021-01-01 --end today --workers 20 --s2-rgb

  python3 s1_s2_indices_pipeline.py --lon ... --lat ... --s2-only
  python3 s1_s2_indices_pipeline.py --lon ... --lat ... --s1-only
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import planetary_computer
import pystac_client
import rasterio
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject

# ---------- GDAL / COG tuning ----------
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.tiff,.TIF,.TIFF,.jp2")
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
os.environ.setdefault("GDAL_HTTP_MULTIPLEX", "YES")
os.environ.setdefault("GDAL_HTTP_VERSION", "2")
os.environ.setdefault("VSI_CACHE", "TRUE")
os.environ.setdefault("VSI_CACHE_SIZE", "268435456")
os.environ.setdefault("GDAL_CACHEMAX", "512")
os.environ.setdefault("GDAL_NUM_THREADS", "1")

SHANGHAI = ZoneInfo("Asia/Shanghai")
SCL_CLEAR = {4, 5, 6, 7}  # vegetation, bare, water, unclassified

S2_BANDS = {
    "B02": 10, "B03": 10, "B04": 10, "B05": 20,
    "B08": 10, "B11": 20, "SCL": 20,
}


# ---------- helpers ----------
def now_sh() -> str:
    return datetime.now(SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")


def parse_end(s: str) -> str:
    if s.lower() in ("today", "now", "nowday"):
        return date.today().isoformat()
    return s


def build_aoi(lon: float, lat: float, half_m: float = 2500.0) -> dict:
    zone = int((lon + 180) / 6) + 1
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    fwd = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    inv = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    cx, cy = fwd.transform(lon, lat)
    bbox_utm = [cx - half_m, cy - half_m, cx + half_m, cy + half_m]
    corners = [
        (bbox_utm[0], bbox_utm[1]), (bbox_utm[0], bbox_utm[3]),
        (bbox_utm[2], bbox_utm[1]), (bbox_utm[2], bbox_utm[3]),
    ]
    lons, lats = zip(*(inv.transform(x, y) for x, y in corners))
    bbox_wgs = [min(lons), min(lats), max(lons), max(lats)]
    return {
        "center": {"lon": lon, "lat": lat},
        "half_extent_m": half_m,
        "utm": {"epsg": epsg, "bbox": bbox_utm, "center_xy": [cx, cy]},
        "wgs84": {"epsg": 4326, "bbox": bbox_wgs},
    }


def catalog():
    return pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )


def to_ref(x: np.ndarray) -> np.ndarray:
    finite = x[np.isfinite(x) & (x > 0)]
    if finite.size and np.median(finite) > 1.5:
        y = x / 10000.0
        y[x <= 0] = np.nan
        return y
    y = x.astype("float32")
    y[x <= 0] = np.nan
    return y


def upsample_nearest(src: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    if src.shape == shape:
        return src
    if src.shape[0] * 2 == shape[0] and src.shape[1] * 2 == shape[1]:
        return np.repeat(np.repeat(src, 2, axis=0), 2, axis=1)[: shape[0], : shape[1]]
    ys = (np.arange(shape[0]) * src.shape[0] / shape[0]).astype(int)
    xs = (np.arange(shape[1]) * src.shape[1] / shape[1]).astype(int)
    return src[ys][:, xs]


def safe_div(a, b):
    out = np.full(a.shape, np.nan, dtype="float32")
    m = np.isfinite(a) & np.isfinite(b) & (np.abs(b) > 1e-6)
    out[m] = (a[m] / b[m]).astype("float32")
    return out


def stats(arr: np.ndarray, mask: np.ndarray | None = None) -> dict:
    if mask is None:
        v = arr[np.isfinite(arr)]
    else:
        v = arr[mask & np.isfinite(arr)]
    if v.size == 0:
        return {
            "count": 0, "mean": None, "median": None, "std": None,
            "p10": None, "p25": None, "p75": None, "p90": None,
            "min": None, "max": None,
        }
    return {
        "count": int(v.size),
        "mean": float(np.mean(v)),
        "median": float(np.median(v)),
        "std": float(np.std(v)),
        "p10": float(np.percentile(v, 10)),
        "p25": float(np.percentile(v, 25)),
        "p75": float(np.percentile(v, 75)),
        "p90": float(np.percentile(v, 90)),
        "min": float(np.min(v)),
        "max": float(np.max(v)),
    }


def read_windowed(href: str, epsg: int, bbox_utm, res: float, resampling) -> tuple[np.ndarray, dict]:
    west, south, east, north = bbox_utm
    width = int(round((east - west) / res))
    height = int(round((north - south) / res))
    dst_transform = from_bounds(west, south, east, north, width, height)
    dst_crs = CRS.from_epsg(epsg)
    with rasterio.open(href) as src:
        dtype = np.float32 if src.dtypes[0] in ("float32", "float64") else src.dtypes[0]
        nodata = src.nodata
        dst = np.zeros((height, width), dtype=dtype)
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=resampling,
            src_nodata=nodata,
            dst_nodata=nodata if nodata is not None else (np.nan if np.issubdtype(dst.dtype, np.floating) else 0),
        )
        profile = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": 1,
            "dtype": str(dst.dtype),
            "crs": dst_crs,
            "transform": dst_transform,
            "nodata": nodata,
        }
    return dst, profile


def save_rgb_png(path: Path, r: np.ndarray, g: np.ndarray, b: np.ndarray, p2=2, p98=98):
    from PIL import Image

    def stretch(x):
        v = x[np.isfinite(x) & (x > 0)]
        if v.size == 0:
            return np.zeros(x.shape, dtype=np.uint8)
        lo, hi = np.percentile(v, [p2, p98])
        if hi <= lo:
            hi = lo + 1e-6
        y = (np.clip(x, lo, hi) - lo) / (hi - lo)
        y = np.nan_to_num(y, nan=0.0)
        return (y * 255).astype(np.uint8)

    rgb = np.dstack([stretch(r), stretch(g), stretch(b)])
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb, mode="RGB").save(path, optimize=True)


# ---------- Sentinel-2 ----------
def process_s2_item(item, aoi: dict, rgb_dir: Path | None, max_cloud: float) -> dict:
    cc = item.properties.get("eo:cloud_cover")
    try:
        if cc is not None and float(cc) >= max_cloud:
            return {"item_id": item.id, "status": "skipped_cloud", "cloud_cover": cc}
    except Exception:
        pass

    t0 = time.perf_counter()
    signed = planetary_computer.sign(item)
    epsg = aoi["utm"]["epsg"]
    bbox = aoi["utm"]["bbox"]
    arrays = {}
    profile10 = None
    try:
        for band, res in S2_BANDS.items():
            asset = signed.assets.get(band)
            if asset is None:
                return {"item_id": item.id, "status": "missing_band", "band": band}
            resampling = Resampling.nearest if band == "SCL" else Resampling.bilinear
            arr, prof = read_windowed(asset.href, epsg, bbox, float(res), resampling)
            arrays[band] = arr
            if band == "B04":
                profile10 = prof
    except Exception as e:
        return {
            "item_id": item.id,
            "status": "fail",
            "error": str(e),
            "seconds": time.perf_counter() - t0,
        }

    blue = to_ref(arrays["B02"].astype("float32"))
    green = to_ref(arrays["B03"].astype("float32"))
    red = to_ref(arrays["B04"].astype("float32"))
    re5 = to_ref(upsample_nearest(arrays["B05"].astype("float32"), red.shape))
    nir = to_ref(arrays["B08"].astype("float32"))
    swir = to_ref(upsample_nearest(arrays["B11"].astype("float32"), red.shape))
    scl = upsample_nearest(arrays["SCL"], red.shape)
    clear = np.isin(scl, list(SCL_CLEAR))

    ndvi = safe_div(nir - red, nir + red)
    ndmi = safe_div(nir - swir, nir + swir)
    ndre = safe_div(nir - re5, nir + re5)
    evi = 2.5 * safe_div(nir - red, nir + 6 * red - 7.5 * blue + 1)
    cire = safe_div(nir, re5) - 1.0
    mndwi = safe_div(green - swir, green + swir)

    dt = item.datetime.astimezone(timezone.utc) if item.datetime else None
    date_s = dt.strftime("%Y-%m-%d") if dt else None
    sensing = dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None

    rgb_path = None
    if rgb_dir is not None:
        rgb_path = str(rgb_dir / f"{item.id}_rgb.png")
        try:
            save_rgb_png(Path(rgb_path), red, green, blue)
        except Exception as e:
            rgb_path = None
            rgb_err = str(e)
        else:
            rgb_err = None
    else:
        rgb_err = None

    return {
        "item_id": item.id,
        "platform": item.properties.get("platform") or item.id[:3],
        "date": date_s,
        "sensing_time_utc": sensing,
        "cloud_cover": cc,
        "clear_fraction": float(clear.mean()),
        "status": "ok",
        "seconds": time.perf_counter() - t0,
        "rgb_png": rgb_path,
        "rgb_error": rgb_err,
        "NDVI": stats(ndvi, clear),
        "NDMI": stats(ndmi, clear),
        "NDRE": stats(ndre, clear),
        "EVI": stats(evi, clear),
        "CIre": stats(cire, clear),
        "MNDWI": stats(mndwi, clear),
    }


def run_s2(aoi, start, end, out_root: Path, workers: int, max_cloud: float, save_rgb: bool) -> dict:
    meta = out_root / "meta"
    rgb_dir = out_root / "s2_rgb" if save_rgb else None
    meta.mkdir(parents=True, exist_ok=True)
    if rgb_dir:
        rgb_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    cat = catalog()
    search = cat.search(
        collections=["sentinel-2-l2a"],
        bbox=aoi["wgs84"]["bbox"],
        datetime=f"{start}/{end}",
        query={"eo:cloud_cover": {"lt": max_cloud}},
    )
    items = list({it.id: it for it in search.items()}.values())
    items.sort(key=lambda x: x.datetime or datetime.min.replace(tzinfo=timezone.utc))
    print(f"[S2] found {len(items)} items cloud<{max_cloud} {start}→{end}", flush=True)

    rows = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process_s2_item, it, aoi, rgb_dir, max_cloud): it.id for it in items}
        done = 0
        for fut in as_completed(futs):
            rows.append(fut.result())
            done += 1
            if done % 10 == 0 or done == len(items):
                ok = sum(1 for r in rows if r.get("status") == "ok")
                print(f"[S2] progress {done}/{len(items)} ok={ok}", flush=True)

    rows.sort(key=lambda r: (r.get("date") or "", r.get("item_id") or ""))
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    ts = []
    for r in ok_rows:
        e = {
            "date": r["date"],
            "item_id": r["item_id"],
            "clear_fraction": r["clear_fraction"],
            "cloud_cover": r.get("cloud_cover"),
            "rgb_png": r.get("rgb_png"),
        }
        for k in ("NDVI", "NDMI", "NDRE", "EVI", "CIre", "MNDWI"):
            e[f"{k}_mean"] = r[k]["mean"]
            e[f"{k}_median"] = r[k]["median"]
        ts.append(e)

    payload = {
        "generated_at_shanghai": now_sh(),
        "sensor": "sentinel-2-l2a",
        "source": "microsoft-planetary-computer",
        "aoi": aoi,
        "time_range": {"start": start, "end": end},
        "max_cloud_cover": max_cloud,
        "formulas": {
            "NDVI": "(B08-B04)/(B08+B04)",
            "NDMI": "(B08-B11)/(B08+B11)",
            "NDRE": "(B08-B05)/(B08+B05)",
            "EVI": "2.5*(B08-B04)/(B08+6*B04-7.5*B02+1)",
            "CIre": "(B08/B05)-1",
            "MNDWI": "(B03-B11)/(B03+B11)",
            "cloud_mask": "SCL in {4,5,6,7}",
        },
        "n_items_found": len(items),
        "n_ok": len(ok_rows),
        "elapsed_s": time.perf_counter() - t0,
        "workers": workers,
        "time_series": ts,
        "scenes": rows,
    }
    (meta / "s2_indices.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    (meta / "s2_indices_timeseries.json").write_text(
        json.dumps(
            {
                "generated_at_shanghai": payload["generated_at_shanghai"],
                "formulas": payload["formulas"],
                "n_ok": payload["n_ok"],
                "time_series": ts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"[S2] done ok={len(ok_rows)} elapsed={payload['elapsed_s']:.1f}s", flush=True)
    return payload


# ---------- Sentinel-1 ----------
def process_s1_item(item, aoi: dict) -> dict:
    t0 = time.perf_counter()
    signed = planetary_computer.sign(item)
    epsg = aoi["utm"]["epsg"]
    bbox = aoi["utm"]["bbox"]
    out = {
        "item_id": item.id,
        "orbit_state": item.properties.get("sat:orbit_state"),
        "platform": item.properties.get("platform"),
        "status": "ok",
    }
    dt = item.datetime.astimezone(timezone.utc) if item.datetime else None
    out["date"] = dt.strftime("%Y-%m-%d") if dt else None
    out["sensing_time_utc"] = dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None

    try:
        for pol in ("vv", "vh"):
            asset = signed.assets.get(pol)
            if asset is None:
                out["status"] = "missing_asset"
                out["missing"] = pol
                return out
            arr, _ = read_windowed(asset.href, epsg, bbox, 10.0, Resampling.bilinear)
            arr = arr.astype("float32")
            arr[~np.isfinite(arr) | (arr <= 0)] = np.nan
            db = 10.0 * np.log10(arr)
            out[pol.upper()] = {
                "linear": stats(arr),
                "db": stats(db),
            }
    except Exception as e:
        out["status"] = "fail"
        out["error"] = str(e)
        out["traceback"] = traceback.format_exc()[-800:]
    out["seconds"] = time.perf_counter() - t0
    return out


def run_s1(aoi, start, end, out_root: Path, workers: int) -> dict:
    meta = out_root / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    cat = catalog()
    search = cat.search(
        collections=["sentinel-1-rtc"],
        bbox=aoi["wgs84"]["bbox"],
        datetime=f"{start}/{end}",
    )
    items = list({it.id: it for it in search.items()}.values())
    items.sort(key=lambda x: x.datetime or datetime.min.replace(tzinfo=timezone.utc))
    print(f"[S1] found {len(items)} RTC items {start}→{end}", flush=True)

    rows = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process_s1_item, it, aoi): it.id for it in items}
        done = 0
        for fut in as_completed(futs):
            rows.append(fut.result())
            done += 1
            if done % 10 == 0 or done == len(items):
                ok = sum(1 for r in rows if r.get("status") == "ok")
                print(f"[S1] progress {done}/{len(items)} ok={ok}", flush=True)

    rows.sort(key=lambda r: (r.get("date") or "", r.get("item_id") or ""))
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    ts = []
    for r in ok_rows:
        ts.append(
            {
                "date": r["date"],
                "item_id": r["item_id"],
                "orbit_state": r.get("orbit_state"),
                "VV_db_mean": r["VV"]["db"]["mean"],
                "VV_db_median": r["VV"]["db"]["median"],
                "VH_db_mean": r["VH"]["db"]["mean"],
                "VH_db_median": r["VH"]["db"]["median"],
                "VV_linear_mean": r["VV"]["linear"]["mean"],
                "VH_linear_mean": r["VH"]["linear"]["mean"],
            }
        )

    payload = {
        "generated_at_shanghai": now_sh(),
        "sensor": "sentinel-1-rtc",
        "source": "microsoft-planetary-computer",
        "aoi": aoi,
        "time_range": {"start": start, "end": end},
        "note": "Radiometric Terrain Corrected VV/VH; stats over 5km AOI; no full SLC.",
        "n_items_found": len(items),
        "n_ok": len(ok_rows),
        "elapsed_s": time.perf_counter() - t0,
        "workers": workers,
        "time_series": ts,
        "scenes": rows,
    }
    (meta / "s1_indices.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    (meta / "s1_indices_timeseries.json").write_text(
        json.dumps(
            {
                "generated_at_shanghai": payload["generated_at_shanghai"],
                "n_ok": payload["n_ok"],
                "time_series": ts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"[S1] done ok={len(ok_rows)} elapsed={payload['elapsed_s']:.1f}s", flush=True)
    return payload


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="S1+S2 AOI indices → JSON (+ optional S2 RGB)")
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--half-km", type=float, default=2.5, help="half extent in km (default 2.5 → 5×5 km)")
    ap.add_argument("--start", type=str, default="2021-01-01")
    ap.add_argument("--end", type=str, default="today")
    ap.add_argument("--outdir", type=str, default="/workspace/s1_s2_pipeline_out")
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--max-cloud", type=float, default=80.0)
    ap.add_argument("--s2-rgb", action="store_true", help="save Sentinel-2 true-color PNGs")
    ap.add_argument("--s2-only", action="store_true")
    ap.add_argument("--s1-only", action="store_true")
    args = ap.parse_args(argv)

    start = args.start
    end = parse_end(args.end)
    out_root = Path(args.outdir)
    out_root.mkdir(parents=True, exist_ok=True)
    aoi = build_aoi(args.lon, args.lat, half_m=args.half_km * 1000.0)
    (out_root / "meta").mkdir(parents=True, exist_ok=True)
    (out_root / "meta" / "aoi.json").write_text(json.dumps(aoi, indent=2))

    run_start = now_sh()
    print(f"START_SHANGHAI={run_start}", flush=True)
    print(f"AOI epsg={aoi['utm']['epsg']} bbox_wgs={aoi['wgs84']['bbox']}", flush=True)
    print(f"RANGE {start} → {end} workers={args.workers}", flush=True)

    summary = {
        "start_shanghai": run_start,
        "aoi": aoi,
        "time_range": {"start": start, "end": end},
        "workers": args.workers,
    }
    t0 = time.perf_counter()

    do_s2 = not args.s1_only
    do_s1 = not args.s2_only
    if do_s2:
        summary["s2"] = run_s2(
            aoi, start, end, out_root, args.workers, args.max_cloud, args.s2_rgb
        )
    if do_s1:
        summary["s1"] = run_s1(aoi, start, end, out_root, args.workers)

    # combined slim JSON for apps
    combined = {
        "generated_at_shanghai": now_sh(),
        "aoi": aoi,
        "time_range": {"start": start, "end": end},
        "s2_timeseries": (summary.get("s2") or {}).get("time_series", []),
        "s1_timeseries": (summary.get("s1") or {}).get("time_series", []),
        "s2_formulas": (summary.get("s2") or {}).get("formulas"),
        "outputs": {
            "s2_indices": str(out_root / "meta" / "s2_indices.json"),
            "s2_timeseries": str(out_root / "meta" / "s2_indices_timeseries.json"),
            "s1_indices": str(out_root / "meta" / "s1_indices.json"),
            "s1_timeseries": str(out_root / "meta" / "s1_indices_timeseries.json"),
            "s2_rgb_dir": str(out_root / "s2_rgb") if args.s2_rgb else None,
        },
    }
    (out_root / "meta" / "combined_timeseries.json").write_text(
        json.dumps(combined, ensure_ascii=False, indent=2)
    )

    end_sh = now_sh()
    summary["end_shanghai"] = end_sh
    summary["total_s"] = time.perf_counter() - t0
    (out_root / "meta" / "run_summary.json").write_text(json.dumps({
        "start_shanghai": run_start,
        "end_shanghai": end_sh,
        "total_s": summary["total_s"],
        "s2_ok": (summary.get("s2") or {}).get("n_ok"),
        "s1_ok": (summary.get("s1") or {}).get("n_ok"),
        "s2_elapsed_s": (summary.get("s2") or {}).get("elapsed_s"),
        "s1_elapsed_s": (summary.get("s1") or {}).get("elapsed_s"),
    }, indent=2))
    print(f"END_SHANGHAI={end_sh} total_s={summary['total_s']:.1f}", flush=True)
    print(f"Wrote {out_root/'meta'/'combined_timeseries.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
