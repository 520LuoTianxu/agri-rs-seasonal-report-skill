# -*- coding: utf-8 -*-
"""Drought / flood hazard for weak parcels (agri_classify + rain).

HARD GATE: only conclusions with confidence >= CONF_MIN (default 75) are
reportable. Full audit always written to side JSON.

Drought: optical NDVI + NDMI(=LSWI from flood indices) via classify_drought_series.
  Extra canopy gate: NDVI >= CANOPY_NDVI on the flag date (skip bare/post-harvest).
Flood: Sentinel-1 VV/VH via classify_flood_series + rainfall corroboration.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

sys.path.insert(0, '/workspace/agric-satellite-analysis-api/packages/agric_satellite_analysis_common')
from agric_satellite_analysis_common.agri_classify import (  # noqa: E402
    classify_drought_series,
    classify_flood_series,
    is_drought_day_class,
    is_open_water_flood,
)

from catalog import DATA  # noqa: E402

CONF_MIN = 75.0
CANOPY_NDVI = 0.40
FLOOD_CSV_DEFAULT = '/workspace/project2878_20261019/flood/flood_indices_per_parcel.csv'
RAIN_GLOB_DEFAULT = '/workspace/project2878_20261019/flood/rain_*.json'


def _load_rain_mean(rain_glob: str = RAIN_GLOB_DEFAULT) -> dict[str, float]:
    rain: dict[str, list[float]] = {}
    for path in glob.glob(rain_glob):
        if 'points' in os.path.basename(path):
            continue
        r = json.load(open(path))
        daily = r.get('daily') or {}
        for t, p in zip(daily.get('time') or [], daily.get('precipitation_sum') or []):
            rain.setdefault(str(t)[:10], []).append(float(p or 0))
    return {t: sum(v) / len(v) for t, v in rain.items()}


def _rain_sum(rain: dict[str, float], date: str, days: int = 14) -> float:
    d0 = datetime.strptime(date[:10], '%Y-%m-%d')
    s = 0.0
    for i in range(days + 1):
        s += rain.get((d0 - timedelta(days=i)).strftime('%Y-%m-%d'), 0.0)
    return s


def _rain_near_max(rain: dict[str, float], date: str, rad: int = 3) -> float:
    d0 = datetime.strptime(date[:10], '%Y-%m-%d')
    best = 0.0
    for i in range(-rad, rad + 1):
        best = max(best, rain.get((d0 + timedelta(days=i)).strftime('%Y-%m-%d'), 0.0))
    return best


def _weak_stage_dates(parcel_row: dict, group_meta: dict) -> list[str]:
    """Dates where this parcel had ok+weak cells."""
    out = []
    st = group_meta.get('ST') or []
    cells = parcel_row.get('cells') or []
    for i, c in enumerate(cells):
        if i >= len(st):
            break
        if c.get('st') == 'ok' and float(c.get('mu') or 0) > 0.5:
            # ST entry is [d, nm, ix, th]
            d = st[i][0] if isinstance(st[i], (list, tuple)) else st[i].get('d')
            if d:
                out.append(f'2026-{d}' if len(d) == 5 else d)
    return out


def _near_any(date: str, dates: list[str], tol_days: int = 7) -> bool:
    if not dates:
        return False
    d0 = datetime.strptime(date[:10], '%Y-%m-%d')
    for t in dates:
        try:
            dt = datetime.strptime(t[:10], '%Y-%m-%d')
        except ValueError:
            continue
        if abs((d0 - dt).days) <= tol_days:
            return True
    return False


def score_drought(
    flags: list[dict],
    *,
    weak_dates: list[str],
    rain: dict[str, float],
) -> tuple[float, dict]:
    """Return (confidence 0-100, breakdown). flags already canopy-filtered."""
    if not flags:
        return 0.0, {'reason': 'no_canopy_drought_flags'}
    worst = max(flags, key=lambda f: {'mild': 1, 'moderate': 2, 'severe': 3}.get(f['class'], 0))
    conf = 0.0
    br: dict[str, Any] = {'n_flags': len(flags), 'worst': worst['class']}
    base = {'mild': 18, 'moderate': 30, 'severe': 38}.get(worst['class'], 0)
    conf += base
    br['base'] = base
    extra = min(24, 12 * (len(flags) - 1))
    conf += extra
    br['multi_date'] = extra
    # dry antecedent
    dry_bonus = 0
    for f in flags:
        r14 = f.get('rain_14d', 999)
        mon = int(f['date'][5:7])
        if mon in (7, 8, 9) and r14 < 20:
            dry_bonus = max(dry_bonus, 20)
        elif mon in (7, 8, 9) and r14 < 35:
            dry_bonus = max(dry_bonus, 12)
    conf += dry_bonus
    br['dry_antecedent'] = dry_bonus
    # align with weak stages
    align = 0
    if any(_near_any(f['date'], weak_dates, 7) for f in flags):
        align = 15
    conf += align
    br['weak_align'] = align
    # contradict wet
    wet_pen = 0
    if all(f.get('rain_14d', 0) > 80 for f in flags):
        wet_pen = 20
        conf -= wet_pen
    br['wet_penalty'] = wet_pen
    conf = max(0.0, min(100.0, conf))
    return conf, br


def score_flood(
    flags: list[dict],
    *,
    rain: dict[str, float],
) -> tuple[float, dict]:
    if not flags:
        return 0.0, {'reason': 'no_s1_flags'}
    # prefer confirmed flood over watch
    confirmed = [f for f in flags if is_open_water_flood(f['class'])]
    use = confirmed or flags
    worst = max(use, key=lambda f: {'watch': 1, 'flood_moderate': 2, 'flood_severe': 3}.get(f['class'], 0))
    conf = 0.0
    br: dict[str, Any] = {'n_flags': len(flags), 'worst': worst['class'], 'confirmed_n': len(confirmed)}
    base = {'watch': 28, 'flood_moderate': 52, 'flood_severe': 62}.get(worst['class'], 0)
    conf += base
    br['base'] = base
    rain_b = 0
    for f in use:
        rn = f.get('rain_near3', 0)
        if rn >= 50:
            rain_b = max(rain_b, 22)
        elif rn >= 25:
            rain_b = max(rain_b, 15)
        elif rn >= 10:
            rain_b = max(rain_b, 6)
    conf += rain_b
    br['rain_corroboration'] = rain_b
    sw = max((f.get('sarwater_frac') or 0) for f in use)
    sw_b = 10 if sw >= 0.05 else (5 if sw >= 0.02 else 0)
    conf += sw_b
    br['sarwater'] = sw_b
    # spring puddling / irrigation
    spring_pen = 0
    if all(int(f['date'][5:7]) in (3, 4, 5) for f in use):
        spring_pen = 25
        conf -= spring_pen
    br['spring_penalty'] = spring_pen
    # watch without confirmed never reaches report alone easily
    if not confirmed:
        conf = min(conf, 70)  # hard cap below gate
        br['watch_cap'] = 70
    conf = max(0.0, min(100.0, conf))
    return conf, br


def analyze_project(
    key: str,
    *,
    weak_path: str | None = None,
    flood_csv: str = FLOOD_CSV_DEFAULT,
    rain_glob: str = RAIN_GLOB_DEFAULT,
    min_persist_mu: float = 2.0,
    conf_min: float = CONF_MIN,
) -> dict:
    weak_path = weak_path or f'{DATA}/{key}_weak.json'
    W = json.load(open(weak_path))
    rain = _load_rain_mean(rain_glob)
    df = pd.read_csv(flood_csv)

    parcels_out = []
    reportable_drought = []
    reportable_flood = []

    for gname, M in (W.get('groups') or {}).items():
        for x in M.get('per') or []:
            if float(x.get('p2') or 0) < min_persist_mu:
                continue
            lid = int(x['lid'])
            weak_dates = _weak_stage_dates(x, M)

            # --- drought optical ---
            o = df[(df.src == 'S2') & (df.land_id == lid) & (df.clear_frac >= 0.3)].sort_values('date')
            obs = []
            ndvi_by_date = {}
            for _, r in o.iterrows():
                if pd.isna(r.NDVI) or pd.isna(r.LSWI):
                    continue
                d = str(r.date)[:10]
                ndvi = float(r.NDVI)
                ndmi = float(r.LSWI)
                ndvi_by_date[d] = ndvi
                obs.append(dict(
                    date=d, ndvi=ndvi, ndmi=ndmi, official=True, source='s2',
                    parcel_cloud_cover_pct=(1 - float(r.clear_frac)) * 100,
                    parcel_cloud_source='scl',
                ))
            dcls = classify_drought_series(obs) if obs else []
            raw_flags = []
            canopy_flags = []
            for d, c in dcls:
                if not is_drought_day_class(c):
                    continue
                item = {
                    'date': d, 'class': c,
                    'ndvi': ndvi_by_date.get(d),
                    'rain_14d': round(_rain_sum(rain, d, 14), 1),
                }
                raw_flags.append(item)
                # skip wet-antecedent "drought" (rain-heavy 14d contradicts)
                if (ndvi_by_date.get(d) or 0) >= CANOPY_NDVI and item['rain_14d'] <= 50:
                    canopy_flags.append(item)
            d_conf, d_br = score_drought(canopy_flags, weak_dates=weak_dates, rain=rain)

            # --- flood S1 + rain ---
            s = df[(df.src.str.startswith('S1')) & (df.land_id == lid)].sort_values('date')
            sar = []
            sw_by_date = {}
            for _, r in s.iterrows():
                if pd.isna(r.VV_db):
                    continue
                d = str(r.date)[:10]
                sw_by_date[d] = float(r.sarwater_frac) if not pd.isna(r.sarwater_frac) else 0.0
                sar.append(dict(
                    date=d,
                    vv=float(r.VV_db),
                    vh=float(r.VH_db) if not pd.isna(r.VH_db) else None,
                    scene_id=f's1_{d}_{lid}',
                    relative_orbit=1,
                    platform='S1A',
                    calibration_method='rtc',
                    calibration_scale=1.0,
                    processing_version='rtc',
                ))
            fcls = classify_flood_series(sar) if sar else []
            f_flags = []
            for d, c in fcls:
                if not c or c == 'dry':
                    continue
                f_flags.append({
                    'date': d, 'class': c,
                    'rain_near3': round(_rain_near_max(rain, d, 3), 1),
                    'sarwater_frac': sw_by_date.get(d, 0.0),
                })
            f_conf, f_br = score_flood(f_flags, rain=rain)

            row = dict(
                name=x.get('name'), land_id=str(lid), mu=x.get('mu'),
                persist_mu=round(float(x.get('p2') or 0), 2),
                group=gname,
                drought=dict(
                    confidence=round(d_conf, 1),
                    reportable=d_conf >= conf_min,
                    breakdown=d_br,
                    flags_canopy=canopy_flags,
                    flags_raw_n=len(raw_flags),
                    flags_raw_classes=[f['class'] for f in raw_flags],
                ),
                flood=dict(
                    confidence=round(f_conf, 1),
                    reportable=f_conf >= conf_min,
                    breakdown=f_br,
                    flags=f_flags,
                ),
            )
            parcels_out.append(row)
            if row['drought']['reportable']:
                reportable_drought.append(row)
            if row['flood']['reportable']:
                reportable_flood.append(row)

    summary = dict(
        key=key,
        conf_min=conf_min,
        canopy_ndvi_min=CANOPY_NDVI,
        n_weak_ge_min=len(parcels_out),
        n_drought_reportable=len(reportable_drought),
        n_flood_reportable=len(reportable_flood),
        rule=(
            'Drought: agri_classify.classify_drought_series on NDVI+NDMI(LSWI); '
            f'canopy NDVI>={CANOPY_NDVI}; confidence>= {conf_min} to report. '
            'Flood: agri_classify.classify_flood_series on S1 VV/VH + rain±3d; '
            f'watch alone capped <{conf_min}; spring penalty; confidence>={conf_min} to report.'
        ),
    )
    out = dict(
        summary=summary,
        reportable=dict(
            drought=[{
                'name': r['name'], 'land_id': r['land_id'], 'persist_mu': r['persist_mu'],
                'confidence': r['drought']['confidence'],
                'flags': r['drought']['flags_canopy'],
            } for r in reportable_drought],
            flood=[{
                'name': r['name'], 'land_id': r['land_id'], 'persist_mu': r['persist_mu'],
                'confidence': r['flood']['confidence'],
                'flags': r['flood']['flags'],
            } for r in reportable_flood],
        ),
        parcels=parcels_out,
    )
    path = f'{DATA}/{key}_hazard.json'
    json.dump(out, open(path, 'w'), ensure_ascii=False, indent=2)
    print(key, 'hazard weak', summary['n_weak_ge_min'],
          'drought>=', conf_min, summary['n_drought_reportable'],
          'flood>=', conf_min, summary['n_flood_reportable'],
          '→', path, flush=True)
    return out


def report_snippets(hazard: dict, conf_min: float = CONF_MIN) -> dict[str, str]:
    """HTML snippets for agent core (empty if nothing reportable)."""
    rd = hazard.get('reportable', {}).get('drought') or []
    rf = hazard.get('reportable', {}).get('flood') or []
    bits = []
    if rd:
        top = sorted(rd, key=lambda x: -x['confidence'])[:5]
        parts = []
        for t in top:
            labs = '/'.join(sorted({f['class'] for f in t['flags']}))
            parts.append(
                f"{t['name']}（置信度 <span class=\"b\">{t['confidence']:.0f}</span>%；冠层期{labs}）"
            )
        names = '、'.join(parts)
        bits.append(
            f"<p><b>7. 受旱（光学，置信度≥{conf_min:.0f}% 才写入）。</b>"
            f"对持续弱地块用 NDVI+NDMI（NDDI）与同月基线交叉判定，并要求冠层 NDVI≥{CANOPY_NDVI}。"
            f"达到门槛的地块：{names}。"
            f"未达门槛的判定仅留审计 JSON，不写入正文。</p>"
        )
    if rf:
        top = sorted(rf, key=lambda x: -x['confidence'])[:5]
        parts = []
        for t in top:
            labs = '/'.join(sorted({f['class'] for f in t['flags']}))
            parts.append(
                f"{t['name']}（置信度 <span class=\"b\">{t['confidence']:.0f}</span>%；{labs}）"
            )
        names = '、'.join(parts)
        bits.append(
            f"<p><b>8. 受涝（Sentinel-1 + 降水，置信度≥{conf_min:.0f}% 才写入）。</b>"
            f"S1 VV/VH 相对同轨基线 + 前后 3 日降水联合判断。达到门槛的地块：{names}。"
            f"仅 watch 或低于门槛的不写入正文。</p>"
        )
    drought_html = bits[0] if rd else ''
    flood_html = ''
    for b in bits:
        if '受涝' in b:
            flood_html = b
            break
    return dict(
        drought_html=drought_html,
        flood_html=flood_html,
        combined_html=''.join(bits),
    )


if __name__ == '__main__':
    keys = sys.argv[1:] or ['p2878']
    for k in keys:
        h = analyze_project(k)
        sn = report_snippets(h)
        print('snippets', {a: bool(b) for a, b in sn.items()})
