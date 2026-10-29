# -*- coding: utf-8 -*-
"""省级遥感长势综合报告：综合分排行（同地块近三年+田内+相对周边变化）+ 解读 + 卫星对比。"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections import defaultdict

from catalog import PROJECTS, DATA, ROOT, by_key
from cover import COVER_CSS, make_cover_html, province_of
from harden_helpers import pct_verdict
from season_ring import season_rank_pct, season_y3_ranks

OUT_DIR = os.path.join(ROOT, 'out', 'province_summary_20261028')
FIG_CACHE = os.path.join(OUT_DIR, '_figs')
AGENT_DIR = os.path.join(DATA, 'agent_analysis')
REPORT_DATE = '2026年10月28日'
PROVINCES = ('河南', '山东', '山西', '河北')

CSS = f'''
@page{{size:A4;margin:12mm 12mm 12mm 12mm}}
body{{font-family:'Noto Sans CJK SC','Noto Sans CJK JP',sans-serif;font-size:9.6pt;line-height:1.52;color:#222}}
h1{{font-size:14pt;color:#0d3b66;border-bottom:2px solid #0d3b66;padding-bottom:3px;margin:0 0 6px}}
h2{{font-size:11.2pt;color:#0d3b66;margin:8px 0 4px;border-left:4px solid #0d3b66;padding-left:6px;page-break-after:avoid}}
h3{{font-size:10pt;color:#333;margin:7px 0 3px;page-break-after:avoid}}
p{{margin:3px 0 5px;text-align:justify}}
.b{{color:#1565c0;font-weight:600}}.g{{color:#2e7d32;font-weight:600}}.r{{color:#c62828;font-weight:600}}
table.t{{border-collapse:collapse;width:100%;margin:4px 0 7px;font-size:8.1pt}}
table.t th{{background:#0d3b66;color:#fff;padding:4px 3px;border:1px solid #0d3b66;font-weight:600;text-align:center}}
table.t td{{padding:3px 3px;border:1px solid #cfd8dc;vertical-align:middle}}
table.t tr:nth-child(even){{background:#f7fafc}}
table.t td.n{{text-align:center;width:7%}}
table.t td.num{{text-align:right;white-space:nowrap}}
table.t td.name{{text-align:left}}
.note{{font-size:7.6pt;color:#666;margin:2px 0 6px}}
.foot{{margin-top:6mm;font-size:7.1pt;color:#b0b0b0;line-height:1.4;border-top:1px solid #e0e0e0;padding-top:4px}}
.sum{{background:#f3f7fb;border-left:3px solid #2F6FED;padding:5px 7px;margin:4px 0 7px;font-size:9pt}}
.warn{{background:#fff8e7;border-left:3px solid #D4A017;padding:5px 7px;margin:4px 0 7px;font-size:9pt}}
ul.reason{{margin:2px 0 6px 1.05em;padding:0}}
ul.reason li{{margin:2px 0;text-align:justify}}
table.grid{{width:100%;border-collapse:collapse;margin:4px 0 8px;page-break-inside:avoid}}
table.grid td{{width:50%;vertical-align:top;padding:3px 4px;border:none;text-align:center}}
table.grid img{{max-width:100%;max-height:78mm;object-fit:contain;border:1px solid #ddd}}
.cap{{font-size:8pt;color:#0d3b66;font-weight:600;margin-top:3px;line-height:1.35;text-align:center}}
.cap .sub{{font-weight:400;color:#555;font-size:7.5pt}}
.legend{{font-size:7.8pt;color:#555;margin:2px 0 6px}}
{COVER_CSS}
.rs-cover{{page-break-after:always}}
.pagebreak{{page-break-before:always}}
'''


def _b(s):
    return f'<span class="b">{s}</span>'


def _g(s):
    return f'<span class="g">{s}</span>'


def _r(s):
    return f'<span class="r">{s}</span>'


def _color_verdict(v):
    if v in ('偏好', '略好'):
        return _g(v)
    if v == '差不多':
        return _b(v)
    return _r(v)


def strip_html(html):
    s = re.sub(r'<[^>]+>', '', html or '')
    s = re.sub(r'\{\{[^}]+\}\}', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def parse_basis(basis):
    out = dict(mu=None, n=None, pct=None, weak=None, drought_mu=None, drought_note=None,
               flood_mu=None, peanut_n=None, peanut_mu=None, peanut_harvest_pct=None,
               verdict_tag=None)
    for t in basis or []:
        m = re.fullmatch(r'n(\d+)', t)
        if m:
            out['n'] = int(m.group(1)); continue
        m = re.fullmatch(r'dedup(\d+)', t)
        if m:
            out['n'] = int(m.group(1)); continue
        m = re.fullmatch(r'mu([0-9.]+)', t)
        if m:
            out['mu'] = float(m.group(1)); continue
        m = re.fullmatch(r'([0-9.]+)亩夏玉米', t)
        if m:
            out['mu'] = float(m.group(1)); continue
        m = re.fullmatch(r'超过周边(\d+)%(.+)', t)
        if m:
            out['pct'] = int(m.group(1)); out['verdict_tag'] = m.group(2); continue
        m = re.fullmatch(r'weak([0-9.]+)%', t)
        if m:
            out['weak'] = float(m.group(1)); continue
        m = re.fullmatch(r'受旱(.+?)约([0-9.]+)亩', t)
        if m:
            out['drought_note'] = m.group(1).strip(); out['drought_mu'] = float(m.group(2)); continue
        m = re.fullmatch(r'受涝([0-9.]+)亩', t)
        if m:
            out['flood_mu'] = float(m.group(1)); continue
        m = re.fullmatch(r'花生启用(\d+)块([0-9.]+)亩', t)
        if m:
            out['peanut_n'] = int(m.group(1)); out['peanut_mu'] = float(m.group(2)); continue
        m = re.search(r'花生.+已收约([0-9.]+)%', t)
        if m:
            out['peanut_harvest_pct'] = float(m.group(1)); continue
    return out


def extract_evidence(html, info):
    plain = strip_html(html)
    ev = {}
    if info.get('weak') is not None and info.get('mu'):
        ev['weak_mu'] = round(info['mu'] * info['weak'] / 100.0, 1)
    m = re.search(r'时序上[：:]([^。]{8,120})', plain)
    if m:
        ev['timeline'] = m.group(1).strip()
    if 'timeline' not in ev:
        m = re.search(r'((?:[6-9]|10)\s*月[^。]{0,40}(?:低于|追平|不低于|晚于)[^。]{0,60})', plain)
        if m:
            ev['timeline'] = m.group(1).strip()
    m = re.search(r'周边中位峰值约\s*([0-9.]+)', plain)
    if m:
        ev['ring_med'] = m.group(1)
    if re.search(r'春夏混种玉米', plain):
        ev['mixed'] = True
        m2 = re.search(
            r'其中春播约\s*(\d+)\s*块[、，]\s*([0-9.]+)\s*亩'
            r'(?:[，,]?\s*持续弱约\s*([0-9.]+)\s*亩)?',
            plain,
        )
        m3 = re.search(
            r'夏播约\s*(\d+)\s*块[、，]\s*([0-9.]+)\s*亩'
            r'(?:[，,]?\s*持续弱约\s*([0-9.]+)\s*亩)?',
            plain,
        )
        if m2:
            ev['spring_n'], ev['spring_mu'] = int(m2.group(1)), float(m2.group(2))
            if m2.group(3) is not None:
                ev['spring_weak_mu'] = float(m2.group(3))
        if m3:
            ev['summer_n'], ev['summer_mu'] = int(m3.group(1)), float(m3.group(2))
            if m3.group(3) is not None:
                ev['summer_weak_mu'] = float(m3.group(3))
    m = re.search(r'(\d{2}-\d{2})[^。]{0,24}约\s*([0-9.]+)\s*亩（单期最高）', plain)
    if m:
        ev['peak_weak_date'], ev['peak_weak_mu'] = m.group(1), float(m.group(2))
    return ev


def resolve_fig(P, kind='pmap'):
    """Return absolute path: prefer pmap, then pmap_px, then map; ring separate."""
    fd = P['fig_dir']
    pref = P['fig_prefix']
    if kind == 'ring':
        cands = [f'{pref}ring.png', f'{P["key"]}_ring.png']
    else:
        cands = [f'{pref}pmap.png', f'{pref}pmap_px.png', f'{pref}map.png',
                 f'{P["key"]}_pmap.png', f'{P["key"]}_pmap_px.png', f'{P["key"]}_map.png']
    for c in cands:
        p = os.path.join(fd, c)
        if os.path.exists(p) and os.path.getsize(p) > 1000:
            return p, os.path.basename(p)
    return None, None


def cache_fig(src, key, kind):
    if not src:
        return None
    os.makedirs(FIG_CACHE, exist_ok=True)
    ext = os.path.splitext(src)[1] or '.png'
    dst = os.path.join(FIG_CACHE, f'{key}_{kind}{ext}')
    if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
        shutil.copy2(src, dst)
    return dst


def primary_crop(P, html):
    plain = re.sub(r'<[^>]+>', '', html or '')
    if re.search(r'本项目春玉米', plain):
        return '春玉米'
    if P.get('spring'):
        return '春玉米'
    return '夏玉米'


def load_y3(P):
    """Read 2024/2025/2026 proj_peak + rank_pct from catalog rs JSON.
    proj_peak = same-parcel peak greenness (近三年主列);
    rank_pct = relative-to-surroundings share (超过周边约 N% 的地块) for 区位对照.
    """
    out = {
        'peak24': None, 'peak25': None, 'peak26': None,
        'rank24': None, 'rank25': None, 'rank26': None,
    }
    rs = P.get('rs')
    if not rs or not os.path.exists(rs):
        return out
    try:
        d = json.load(open(rs, encoding='utf-8'))
    except Exception:
        return out
    for y, pk, rk in (
        ('2024', 'peak24', 'rank24'),
        ('2025', 'peak25', 'rank25'),
        ('2026', 'peak26', 'rank26'),
    ):
        yy = d.get(y) or {}
        v = yy.get('proj_peak')
        if v is not None:
            try:
                out[pk] = float(v)
            except (TypeError, ValueError):
                pass
        rv = yy.get('rank_pct')
        if rv is not None:
            try:
                out[rk] = float(rv)
            except (TypeError, ValueError):
                pass
    return out


RING_YOY_EPS = 10.0  # 个百分点：|Δ|≤此值视为区位常态


def classify_ring_yoy(rank24, rank25, rank26):
    """对照近三年相对周边位置（rank_pct → 超过周边约 N% 的地块）。
    返回 dict: rank24/25/26(int|None), prior_mean, delta_pp, tag, phrase, short.
    tag: '区位常态' | '走弱' | '好转' | None
    """
    def _ri(v):
        if v is None:
            return None
        try:
            return int(round(float(v)))
        except (TypeError, ValueError):
            return None

    r24, r25, r26 = _ri(rank24), _ri(rank25), _ri(rank26)
    out = dict(
        rank24=r24, rank25=r25, rank26=r26,
        prior_mean=None, delta_pp=None, tag=None, phrase='', short='',
    )
    priors = [x for x in (r24, r25) if x is not None]
    if r26 is None or not priors:
        return out
    prior = sum(priors) / len(priors)
    delta = r26 - prior
    out['prior_mean'] = round(prior, 1)
    out['delta_pp'] = round(delta, 1)
    if abs(delta) <= RING_YOY_EPS:
        tag = '区位常态'
        if r26 < 40:
            phrase = (
                f'相对周边一直偏低（近三年超过周边约 '
                f'{_fmt_rank_chain(r24, r25, r26)} 的地块），'
                f'更像区位/立地常态，不能单凭今年断定变差'
            )
            short = '区位常态偏低'
        elif r26 >= 60:
            phrase = (
                f'相对周边位置与近三年大体接近（约 '
                f'{_fmt_rank_chain(r24, r25, r26)}），属区位常态偏高/偏好一侧'
            )
            short = '区位常态偏好'
        else:
            phrase = (
                f'相对周边位置与近三年大体接近（约 '
                f'{_fmt_rank_chain(r24, r25, r26)}），属区位常态'
            )
            short = '区位常态'
    elif delta < -RING_YOY_EPS:
        tag = '走弱'
        phrase = (
            f'相对周边比往年更弱（近三年超过周边约 '
            f'{_fmt_rank_chain(r24, r25, r26)} 的地块，'
            f'今年较往年均值约低 {abs(delta):.0f} 个百分点）'
        )
        short = '相对周边走弱'
    else:
        tag = '好转'
        phrase = (
            f'相对周边好于往年（近三年超过周边约 '
            f'{_fmt_rank_chain(r24, r25, r26)} 的地块，'
            f'今年较往年均值约高 {delta:.0f} 个百分点）'
        )
        short = '相对周边好转'
    out['tag'] = tag
    out['phrase'] = phrase
    out['short'] = short
    return out


def _fmt_rank_chain(r24, r25, r26):
    def _p(v):
        return '—' if v is None else f'{v}%'
    return f'{_p(r24)} / {_p(r25)} / {_p(r26)}'


def compute_scores(pct, weak_raw, y3):
    """综合分 = 0.50×同地块近三年分 + 0.30×田内分 + 0.20×相对周边变化分。

    - S_peak（同地块近三年分）= S_level（以峰值水平为主，不用同比微涨/趋势主导）
      · S_level = clip((peak26−0.55)/(0.95−0.55)×100, 0, 100)
      · 高位就高分、低位就低分；三年峰值数字仍作描述列，但不靠趋势抬/压综合分
      · S_change 仅保留审计字段（clip(50+相对升降%,0,100)），不入 S_peak
    - S_weak（田内分）= max(0, 100 − 持续弱占比)
    - S_ringΔ（相对周边变化分）= clip(50 + (rp26 − mean(rp24,rp25)), 0, 100)
      ——只用三年 rank_pct 的**变化**，不用绝对「超过周边约 N%」水平
    - S_ring 仅保留绝对超过周边约 N% 作描述列，**不入综合分**
    - 缺某项权重归一；无超过周边% 或 无峰值（如花生）→ score=None
    """
    # 描述用绝对周边位置（不入分）
    S_ring = float(pct) if pct is not None and pct >= 0 else None
    S_weak = max(0.0, 100.0 - float(weak_raw)) if weak_raw is not None else None

    peak24, peak25, peak26 = y3.get('peak24'), y3.get('peak25'), y3.get('peak26')
    priors = [x for x in (peak24, peak25) if x is not None]
    S_peak = None
    S_level = None
    S_change = None
    y3_delta = None
    y3_delta_rel = None
    if peak26 is not None:
        # 峰值水平：0.55→0、0.95→100（本来就高→高分；本来就低→低分）
        S_level = max(0.0, min(100.0, (float(peak26) - 0.55) / (0.95 - 0.55) * 100.0))
        S_peak = S_level  # 近三年分 = 水平分，不以趋势主导
        if priors:
            prior = sum(priors) / len(priors)
            y3_delta = peak26 - prior
            if prior and prior != 0:
                y3_delta_rel = (peak26 - prior) / prior * 100.0
                S_change = max(0.0, min(100.0, 50.0 + y3_delta_rel))
            else:
                S_change = 50.0

    # 相对周边变化分（rank_pct 升降，非绝对水平）
    r24, r25, r26 = y3.get('rank24'), y3.get('rank25'), y3.get('rank26')
    r_priors = [x for x in (r24, r25) if x is not None]
    S_ring_delta = None
    ring_delta_pp = None
    if r26 is not None and r_priors:
        prior_r = sum(r_priors) / len(r_priors)
        ring_delta_pp = float(r26) - prior_r
        S_ring_delta = max(0.0, min(100.0, 50.0 + ring_delta_pp))

    # 权重：同地块近三年 0.50 / 田内 0.30 / 相对周边变化 0.20
    w_peak, w_weak, w_rd = 0.50, 0.30, 0.20
    parts = []
    if S_peak is not None:
        parts.append(('peak', w_peak, S_peak))
    if S_weak is not None:
        parts.append(('weak', w_weak, S_weak))
    if S_ring_delta is not None:
        parts.append(('ring_delta', w_rd, S_ring_delta))

    score = None
    # 无超过周边% 或 无峰值 → 不参与综合分（如花生）
    if S_ring is None or S_peak is None:
        score = None
    elif not parts:
        score = None
    else:
        wsum = sum(w for _, w, _ in parts)
        score = round(sum(w * s for _, w, s in parts) / wsum, 1)

    def _pk(v):
        return None if v is None else round(float(v), 4)

    return dict(
        S_ring=S_ring,  # 描述列绝对水平，不入分
        S_weak=S_weak,
        S_peak=None if S_peak is None else round(S_peak, 1),
        S_level=None if S_level is None else round(S_level, 1),
        S_change=None if S_change is None else round(S_change, 1),  # 审计用，不入 S_peak
        S_y3=None if S_peak is None else round(S_peak, 1),  # 兼容旧字段名
        S_ring_delta=None if S_ring_delta is None else round(S_ring_delta, 1),
        ring_delta_pp=None if ring_delta_pp is None else round(ring_delta_pp, 1),
        score=score,
        y3_delta=None if y3_delta is None else round(y3_delta, 4),
        y3_delta_rel=None if y3_delta_rel is None else round(y3_delta_rel, 2),
        peak24=_pk(peak24), peak25=_pk(peak25), peak26=_pk(peak26),
    )


def load_project_row(P):
    """Return list of ranking rows. Mixed spring/summer → two rows (same-season ring)."""
    k = P['key']
    path = os.path.join(AGENT_DIR, f'{k}.json')
    agent = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    basis = agent.get('basis') or []
    html = agent.get('core_growth_html') or ''
    info = parse_basis(basis)
    if info['mu'] is None or info['n'] is None:
        pp = P['parcels']
        dedup = pp.replace('_parcels.json', '_parcels_dedup.json')
        plp = dedup if (P.get('dedup') and os.path.exists(dedup)) else pp
        if os.path.exists(plp):
            pl = json.load(open(plp, encoding='utf-8'))
            if info['n'] is None:
                info['n'] = len(pl)
            if info['mu'] is None:
                info['mu'] = round(sum(float(x.get('mu') or 0) for x in pl), 1)
    pct_all = info.get('pct')
    verdict_all = info.get('verdict_tag') or (pct_verdict(pct_all) if pct_all is not None else '—')
    if pct_all is not None and verdict_all not in ('偏低', '偏弱', '差不多', '略好', '偏好'):
        verdict_all = pct_verdict(pct_all)
    pmap, pmap_name = resolve_fig(P, 'pmap')
    ring, ring_name = resolve_fig(P, 'ring')
    y3 = load_y3(P)
    ev = extract_evidence(html, info)

    def _make_row(*, key, name, crop, mu, n, pct, verdict, weak, ev_row,
                  season_split=False, season=None, y3_ranks=None,
                  ring_missing_note=None):
        pmap_cached = cache_fig(pmap, key, 'pmap') if pmap else None
        ring_cached = cache_fig(ring, key, 'ring') if ring else None
        sc = compute_scores(pct if pct is not None else -1, weak, y3)
        if y3_ranks is None:
            ry = classify_ring_yoy(y3.get('rank24'), y3.get('rank25'), y3.get('rank26'))
            r24, r25, r26 = ry['rank24'], ry['rank25'], ry['rank26']
        else:
            r24 = y3_ranks.get('rank24')
            r25 = y3_ranks.get('rank25')
            r26 = y3_ranks.get('rank26')
            ry = classify_ring_yoy(r24, r25, r26)
            # Recompute ring-delta score with seasonal ranks when split
            if season_split:
                y3s = dict(y3)
                y3s['rank24'], y3s['rank25'], y3s['rank26'] = r24, r25, r26
                sc = compute_scores(pct if pct is not None else -1, weak, y3s)
        return dict(
            key=key, base_key=k, name=name, province=province_of(P),
            crop=crop,
            mu=float(mu or 0), n=int(n or 0),
            pct=pct if pct is not None else -1,
            verdict=verdict,
            weak=float(weak) if weak is not None else 999.0,
            weak_raw=weak,
            drought_mu=info['drought_mu'], drought_note=info['drought_note'],
            flood_mu=info['flood_mu'],
            peanut_n=info['peanut_n'], peanut_mu=info['peanut_mu'],
            peanut_harvest_pct=info['peanut_harvest_pct'],
            html=html, agent=agent, ev=ev_row,
            small=(n or 0) <= 2 or (mu or 0) < 200,
            pmap=pmap_cached, pmap_src=pmap_name,
            ring=ring_cached, ring_src=ring_name,
            score=sc['score'], S_ring=sc['S_ring'], S_weak=sc['S_weak'],
            S_peak=sc['S_peak'], S_level=sc.get('S_level'), S_change=sc.get('S_change'),
            S_y3=sc['S_peak'], S_ring_delta=sc['S_ring_delta'],
            ring_delta_pp=sc['ring_delta_pp'],
            y3_delta=sc['y3_delta'], y3_delta_rel=sc['y3_delta_rel'],
            peak24=sc['peak24'], peak25=sc['peak25'], peak26=sc['peak26'],
            rank24=r24, rank25=r25, rank26=r26,
            ring_yoy_tag=ry['tag'], ring_yoy_phrase=ry['phrase'], ring_yoy_short=ry['short'],
            ring_yoy_delta=ry['delta_pp'],
            season_split=season_split, season=season,
            ring_missing_note=ring_missing_note,
        )

    # Mixed → two season rows; never share mixed-season pct across spring/summer
    if ev.get('mixed') and ev.get('spring_mu') and ev.get('summer_mu'):
        rows = []
        for season, crop, label in (
            ('spring', '春玉米', '春播'),
            ('summer', '夏玉米', '夏播'),
        ):
            mu = ev[f'{season}_mu']
            n = ev.get(f'{season}_n') or 0
            weak_mu = ev.get(f'{season}_weak_mu')
            weak_fallback = False
            if weak_mu is not None and mu:
                weak = round(weak_mu / mu * 100.0, 1)
            else:
                weak = info['weak']
                weak_fallback = True
            pct = season_rank_pct(k, season, '2026')
            ring_missing = None
            if pct is None:
                # Do NOT fall back to mixed-season / other-season pct
                verdict = '—'
                ring_missing = '缺同季周边对比（未拿混季或其他季顶替）'
            else:
                verdict = pct_verdict(pct)
            y3r = season_y3_ranks(k, season)
            ev_row = dict(ev)
            if weak_mu is not None:
                ev_row['weak_mu'] = weak_mu
            if weak_fallback:
                ev_row['weak_fallback_project'] = True
            rows.append(_make_row(
                key=f'{k}_{season}',
                name=f"{P['name']}（{label}）",
                crop=crop, mu=mu, n=n, pct=pct, verdict=verdict, weak=weak,
                ev_row=ev_row, season_split=True, season=season, y3_ranks=y3r,
                ring_missing_note=ring_missing,
            ))
        return rows

    # Non-mixed: single row (peanut still handled later via peanut_row_from)
    sc_pct = pct_all
    return [_make_row(
        key=k, name=P['name'], crop=primary_crop(P, html),
        mu=info['mu'], n=info['n'], pct=sc_pct, verdict=verdict_all,
        weak=info['weak'], ev_row=ev, season_split=False, season=None,
    )]



def rank_rows(rows):
    """Sort by 综合分 desc; tie-break S_peak, S_weak, mu. Rows without score go last."""
    def key(r):
        sc = r.get('score')
        if sc is None:
            return (1, 0, 0, 0, 0)  # after scored
        s_peak = r.get('S_peak') if r.get('S_peak') is not None else -1
        s_weak = r.get('S_weak') if r.get('S_weak') is not None else -1
        return (0, -sc, -s_peak, -s_weak, -r['mu'])
    return sorted(rows, key=key)


def peanut_row_from(r):
    if not r.get('peanut_mu'):
        return None
    peak = still_green = None
    pref = r['agent'].get('peanut_ref')
    if pref and os.path.exists(pref):
        try:
            h = (json.load(open(pref, encoding='utf-8')).get('harvest') or {})
            peak = h.get('peak_ndvi_median')
            still_green = h.get('still_green_mu')
        except Exception:
            pass
    # peanut uses same project pmap as visual reference of project footprint
    return dict(
        key=(r.get('base_key') or r['key']) + '_peanut', name=(r['name'].split('（')[0] if '（' in r['name'] else r['name']) + '（夏花生）',
        province=r['province'], crop='花生',
        mu=float(r['peanut_mu']), n=int(r['peanut_n'] or 0),
        pct=-1, verdict='—', weak=999.0, weak_raw=None,
        harvest_pct=r.get('peanut_harvest_pct'), peak_ndvi=peak,
        still_green=still_green, note='省内仅此，无法横向排名',
        small=False, ev={}, pmap=r.get('pmap'), pmap_src=r.get('pmap_src'),
        ring=None, ring_src=None,
        score=None, S_ring=None, S_weak=None, S_peak=None, S_level=None, S_change=None,
        S_y3=None, S_ring_delta=None,
        ring_delta_pp=None,
        y3_delta=None, y3_delta_rel=None, peak24=None, peak25=None, peak26=None,
        rank24=None, rank25=None, rank26=None,
        ring_yoy_tag=None, ring_yoy_phrase='', ring_yoy_short='', ring_yoy_delta=None,
    )


def season_label(crops):
    parts = []
    for c, lab in (('春玉米', '春玉米'), ('夏玉米', '夏玉米'), ('花生', '夏花生')):
        if c in crops:
            parts.append(lab)
    return '2026 年' + ' / '.join(parts or ['玉米']) + '季'


def fmt_pct_cell(r):
    if r['pct'] < 0:
        return '—'
    return f"超过周边约 {r['pct']}% 的地块（{_color_verdict(r['verdict'])}）"


def fmt_weak_cell(r):
    return '—' if r.get('weak_raw') is None else f"{r['weak_raw']:.1f}%"


def fmt_score_cell(r):
    if r.get('score') is None:
        return '—'
    return f"{r['score']:.1f}"


def fmt_y3_cell(r):
    """同地块峰值绿度主列 + 相对周边三年对照一句。"""
    if r.get('crop') == '花生':
        return '—'
    a, b, c = r.get('peak24'), r.get('peak25'), r.get('peak26')
    ra, rb, rc = r.get('rank24'), r.get('rank25'), r.get('rank26')
    if a is None and b is None and c is None and ra is None and rb is None and rc is None:
        return '—'
    def _p(v):
        return '—' if v is None else f'{v:.2f}'
    def _rp(v):
        return '—' if v is None else f'{v}%'
    bits = []
    if not (a is None and b is None and c is None):
        core = f'峰值 {_p(a)} / {_p(b)} / {_p(c)}'
        d = r.get('y3_delta')
        if d is not None:
            arrow = '↑' if d >= 0 else '↓'
            core += f'（较往年均值{arrow}{abs(d):.2f}）'
        bits.append(core)
    if not (ra is None and rb is None and rc is None):
        ring = f'相对周边：{_rp(ra)} / {_rp(rb)} / {_rp(rc)}'
        if r.get('ring_yoy_short'):
            ring += f'（{r["ring_yoy_short"]}）'
        bits.append(ring)
    return '<br>'.join(bits) if bits else '—'


def short_name(name):
    return name.replace('新农人', '').replace('分支', '').strip()


def reason_one(r, rank=None, role='mid'):
    if r['crop'] == '花生':
        return (
            f'{r["name"]}启用约 {_b(r["n"])} 块、{_b(f"{r["mu"]:.1f}")} 亩'
            + (f'，峰值绿度中位约 {_b(f"{r["peak_ndvi"]:.2f}")}' if r.get('peak_ndvi') else '')
            + (f'；截至 10-13 已收获约 {_b(f"{r["harvest_pct"]:.1f}")}%' if r.get('harvest_pct') is not None else '')
            + (f'，仍青绿约 {_b(f"{r["still_green"]:.0f}")} 亩' if r.get('still_green') else '')
            + '。省内仅此花生产目，无「超过周边约 N% 的地块」可比，不参与综合分排序。'
        )
    head = (f'第 {_b(rank)} 名 {r["name"]}' if rank else r['name'])
    parts = []
    if r.get('score') is not None:
        parts.append(f'{head}：综合分 {_b(f"{r["score"]:.1f}")}')
    elif rank:
        parts.append(f'{head}')
    else:
        parts.append(r['name'])
    if r['pct'] >= 0:
        # 克制表述：不把「超过周边低」直接写成「差」；靠后档位结合三年区位对照
        pos = {
            '偏好': '相对多数周边同季耕地处较高一侧',
            '略好': '相对多数周边同季耕地略高',
            '差不多': '与周边同季耕地大体相当',
            '偏低': '相对多数周边同季耕地处较低一侧',
            '偏弱': '相对多数周边同季耕地处较低一侧',
        }.get(r['verdict'], '相对周边有差距')
        parts.append(
            f'峰值超过周边约 {_b(r["pct"])}% 的地块（{_color_verdict(r["verdict"])}），'
            f'{pos}'
        )
        if r.get('ring_yoy_phrase'):
            parts.append(r['ring_yoy_phrase'])
        elif role == 'bot' and r['pct'] < 40:
            parts.append(
                '仅凭「超过周边偏低」不能断定今年变差，还需对照近三年相对周边位置与同地块峰值'
            )
    if r.get('weak_raw') is not None:
        wm = r['ev'].get('weak_mu')
        weak_bit = f'持续弱面积约占 {_b(f"{r["weak_raw"]:.1f}")}%'
        if wm is not None:
            weak_bit += f'（约 {_b(f"{wm:.1f}")} 亩）'
        if role == 'top' and r['weak_raw'] <= 10:
            weak_bit += '，田内持续弱斑相对可控'
        elif role == 'bot' and r['weak_raw'] >= 15:
            weak_bit += '，田内持续弱斑占比偏高（须与周边区位、同地块峰值一并看，不宜单凭弱占比下结论）'
        if r['ev'].get('peak_weak_date') and role in ('bot', 'solo'):
            weak_bit += f'；单期弱面积最高约在 {r["ev"]["peak_weak_date"]}（约 {r["ev"]["peak_weak_mu"]:.0f} 亩）'
        parts.append(weak_bit)
    if role in ('top', 'bot', 'solo') and (
        r.get('peak24') is not None or r.get('peak25') is not None or r.get('peak26') is not None
    ):
        ybits = []
        if r.get('peak24') is not None:
            ybits.append(f'24年峰值 {r["peak24"]:.2f}')
        if r.get('peak25') is not None:
            ybits.append(f'25年峰值 {r["peak25"]:.2f}')
        if r.get('peak26') is not None:
            ybits.append(f'今年峰值 {r["peak26"]:.2f}')
        y3s = ' → '.join(ybits)
        d = r.get('y3_delta')
        if d is not None:
            if d >= 0.02:
                y3s += f'（同地块峰值绿度较往年均值{_g("↑约 " + f"{abs(d):.2f}")}）'
            elif d <= -0.02:
                y3s += f'（同地块峰值绿度较往年均值{_r("↓约 " + f"{abs(d):.2f}")}）'
            else:
                y3s += f'（同地块峰值绿度较往年均值大致持平，差约 {d:+.2f}）'
        parts.append('近三年（同地块峰值绿度）：' + y3s)
    scale = f'规模约 {_b(f"{r["mu"]:.1f}")} 亩 / {_b(r["n"])} 块'
    if r.get('small'):
        scale += '（地块或亩数偏少，排行宜作参考、勿过度外推）'
    parts.append(scale)
    if r['ev'].get('timeline') and role in ('top', 'bot', 'solo'):
        tl = r['ev']['timeline']
        if len(tl) > 68:
            tl = tl[:68] + '…'
        parts.append(f'时序所见：{tl}')
    if r.get('season_split') and role in ('top', 'bot', 'solo'):
        parts.append(
            '春夏混种已按季分列入榜；本行亩数与田内弱占比按本季，'
            '周边对比为同季（春对春、夏对夏）；近三年同地块峰值暂按全项目口径'
        )
        if r.get('ring_missing_note'):
            parts.append(r['ring_missing_note'])
        if r['ev'].get('weak_fallback_project'):
            parts.append('田内弱占比回退全项目口径（分季持续弱亩未解析）')
    elif r['ev'].get('mixed') and role in ('top', 'bot', 'solo'):
        bits = []
        if r['ev'].get('spring_mu') is not None:
            bits.append(f'春播约 {r["ev"]["spring_mu"]:.0f} 亩')
        if r['ev'].get('summer_mu') is not None:
            bits.append(f'夏播约 {r["ev"]["summer_mu"]:.0f} 亩')
        if bits:
            parts.append('项目为春夏混种（' + '、'.join(bits) + '）')
    return '；'.join(parts) + '。'


def verdict_distribution(ranked):
    bands = defaultdict(list)
    for r in ranked:
        if r['pct'] >= 0:
            bands[r['verdict']].append(r)
    order = ('偏好', '略好', '差不多', '偏低', '偏弱')
    parts = []
    for v in order:
        rs = bands.get(v) or []
        if rs:
            parts.append(f'{_color_verdict(v)} {_b(len(rs))} 项')
    return '、'.join(parts) if parts else '—'


def common_evidence(rows, role='top'):
    """头部/尾部共同证据摘要。"""
    if not rows:
        return ''
    scores = [r['score'] for r in rows if r.get('score') is not None]
    pcts = [r['pct'] for r in rows if r['pct'] >= 0]
    weaks = [r['weak_raw'] for r in rows if r.get('weak_raw') is not None]
    deltas = [r['y3_delta'] for r in rows if r.get('y3_delta') is not None]
    bits = []
    if scores:
        bits.append(f'综合分约 {min(scores):.1f}～{max(scores):.1f}')
    if pcts:
        bits.append(f'超过周边约 {min(pcts)}%～{max(pcts)}% 的地块')
    if weaks:
        bits.append(f'持续弱占比约 {min(weaks):.1f}%～{max(weaks):.1f}%')
    if deltas:
        up = sum(1 for d in deltas if d >= 0.02)
        dn = sum(1 for d in deltas if d <= -0.02)
        if role == 'top' and up:
            bits.append(f'近三年同地块峰值较往年均值上升 {_b(up)} 项')
        elif role == 'bot' and dn:
            bits.append(f'近三年同地块峰值较往年均值下降 {_b(dn)} 项')
        else:
            bits.append(f'近三年同地块峰值较往年均值差约 {min(deltas):+.2f}～{max(deltas):+.2f}')
    small_n = sum(1 for r in rows if r.get('small'))
    if small_n:
        bits.append(f'其中 {_b(small_n)} 项地块/亩数偏少')
    if role == 'top':
        return '共同特征：' + '；'.join(bits) + '——综合分靠前' + (
            '，周边与田内多数较稳。' if weaks and max(weaks) <= 16 else '。'
        )
    # 尾部：提示一篇盖不全——周边偏低须对照三年区位与同地块峰值
    tags = [r.get('ring_yoy_tag') for r in rows if r.get('ring_yoy_tag')]
    n_loc = sum(1 for t in tags if t == '区位常态')
    n_dn = sum(1 for t in tags if t == '走弱')
    tail = '——综合分靠后'
    if n_loc and n_loc >= max(1, len(tags) // 2):
        tail += '；其中多项相对周边偏低更像区位/立地常态，不能单凭今年「超过周边低」断定变差'
    elif n_dn:
        tail += '；部分相对周边比往年更弱，须与同地块峰值、弱占比一并看'
    elif (weaks and max(weaks) >= 15) or (deltas and any(d is not None and d < 0 for d in deltas)):
        tail += '；周边对比、田内弱占比或同地块峰值升降需综合看，不宜一篇盖全'
    else:
        tail += '。'
    if not tail.endswith('。'):
        tail += '。'
    return '共同特征：' + '；'.join(bits) + tail


def table_html(crop, ranked):
    if not ranked:
        return ''
    rows_html = []
    for i, r in enumerate(ranked, 1):
        rows_html.append(
            '<tr>'
            f'<td class="n">{i}</td>'
            f'<td class="name">{r["name"]}</td>'
            f'<td class="num"><b>{fmt_score_cell(r)}</b></td>'
            f'<td>{fmt_pct_cell(r)}</td>'
            f'<td class="num">{fmt_weak_cell(r)}</td>'
            f'<td style="font-size:7.4pt">{fmt_y3_cell(r)}</td>'
            f'<td class="num">{r["mu"]:.1f} / {r["n"]}</td>'
            '</tr>'
        )
    note = ''
    if crop == '花生':
        note = (
            '<p class="note">说明：花生按启用去重亩数单列，不与玉米并亩；'
            '无「超过周边约 N% 的地块」时不参与综合分排序。</p>'
        )
    rule = (
        '<p class="note">排行规则：按<strong>综合分</strong>从高到低。'
        '综合分 = 0.50×同地块近三年分 + 0.30×田内分 + 0.20×相对周边变化分'
        '（缺某项时权重归一到其余项）。'
        '<b>不含</b>「超过周边约 N% 的地块」绝对高低——该列仅作描述。'
        '同地块近三年分＝峰值水平分（clip((今年峰值−0.55)/(0.95−0.55)×100,0～100)；高位高分、低位低分，不以同比微涨/趋势主导）；田内分＝100−持续弱占比；'
        '相对周边变化分＝clip(50+（今年相对周边%−往年均值），0～100）'
        '（走强加分、走弱减分；常年偏低但今年差不多→约 50，不因绝对低被压分）。'
        '综合分相同再比同地块近三年分、田内分、亩数。近三年列：峰值 24/25/今年 + 相对周边三年对照'
        '（超过周边约 x% 的地块；区位常态/走弱/好转）。'
        '「超过周边偏低」须结合三年区位对照解读，不能单凭今年断定变差。'
        '春夏混种项目按季拆成两行分列入榜：亩数与田内弱占比按本季；'
        '<b>周边对比均为同季</b>（春玉米只与周边春播比、夏玉米只与周边夏播比），'
        '不用混季或其他季顶替；近三年同地块峰值暂按全项目口径。'
        '花生无超过周边约 N%/无峰值时综合分记为 —。</p>'
    )
    return (
        f'<h2>{crop}正式排行</h2>{note}'
        '<table class="t"><thead><tr>'
        '<th>名次</th><th>项目名</th><th>综合分</th>'
        '<th>超过周边约 N% 的地块（判定）</th><th>持续弱占比</th>'
        '<th>近三年</th><th>亩数/块数</th>'
        '</tr></thead><tbody>'
        + ''.join(rows_html) +
        '</tbody></table>'
        + rule
    )


def interpret_html(crop, ranked):
    if not ranked:
        return ''
    if crop == '花生':
        return ('<h2>花生排行解读</h2><ul class="reason"><li>'
                + reason_one(ranked[0], rank=1, role='solo') + '</li></ul>')
    n = len(ranked)
    bits = [f'<h2>{crop}排行解读</h2>']
    bits.append(
        '<div class="sum"><b>读排行：</b>名次按<strong>综合分</strong>从高到低——'
        '综合分 = 0.50×同地块近三年分 + 0.30×田内分 + 0.20×相对周边变化分；'
        '<b>不含</b>周边绝对高低。近三年分＝峰值水平（高位高分、低位低分，不以微涨/趋势主导）。'
        '田内弱占比、相对周边较往年升降加权；常年偏低但今年差不多时变化分约中性，不因绝对低被压分。'
        '<b>一篇盖不全：</b>「超过周边偏低」不等于今年变差——须对照近三年相对周边位置'
        '（区位常态 / 走弱 / 好转）与同地块峰值、弱占比一起看。'
        '混种分列行的周边对比均为同季（春对春、夏对夏）。'
        '下图用峰值绿度卫星叠图（红偏弱、绿偏好）对照头尾差异。</div>'
    )
    top_n = min(3, n)
    bits.append(f'<p><b>靠前（第 1～{top_n} 名）。</b>{common_evidence(ranked[:top_n], "top")}</p>')
    bits.append('<ul class="reason">')
    for i, r in enumerate(ranked[:top_n], 1):
        bits.append('<li>' + reason_one(r, rank=i, role='top') + '</li>')
    bits.append('</ul>')

    if n >= 4:
        bot = ranked[-min(3, n - top_n):]
        bot = [r for r in bot if r not in ranked[:top_n]]
        if bot:
            start = n - len(bot) + 1
            bits.append(
                f'<p><b>靠后（第 {start}～{n} 名）。</b>{common_evidence(bot, "bot")}</p>'
            )
            bits.append('<ul class="reason">')
            for j, r in enumerate(bot):
                bits.append('<li>' + reason_one(r, rank=start + j, role='bot') + '</li>')
            bits.append('</ul>')
    elif n == 2:
        bits.append('<p><b>对照。</b></p><ul class="reason">')
        bits.append('<li>' + reason_one(ranked[1], rank=2, role='bot') + '</li>')
        bits.append('</ul>')
    elif n == 1:
        bits.append('<p class="note">本省该作物仅 1 个项目，排行即其自身指标，无省内横向对手。</p>')

    mid_end = n - (3 if n >= 6 else (1 if n >= 4 else 0))
    mid = ranked[top_n:mid_end]
    if n >= 6 and mid:
        bands = defaultdict(list)
        for r in mid:
            bands[r['verdict']].append(r)
        bits.append('<p><b>中间档位概括。</b></p><ul class="reason">')
        for v in ('偏好', '略好', '差不多', '偏低', '偏弱'):
            rs = bands.get(v) or []
            if not rs:
                continue
            names = '、'.join(short_name(x['name']) + (f'（综合{x["score"]:.1f}/{x["pct"]}%）' if x.get('score') is not None else f'（{x["pct"]}%）') for x in rs)
            wmin = min(x['weak_raw'] for x in rs if x.get('weak_raw') is not None)
            wmax = max(x['weak_raw'] for x in rs if x.get('weak_raw') is not None)
            bits.append(
                f'<li>{_color_verdict(v)}档：{names}。相对周边处「{v}」；'
                f'持续弱占比约 {wmin:.1f}%～{wmax:.1f}%。</li>'
            )
        bits.append('</ul>')
    return '\n'.join(bits)


def fig_cell(r, rank, role_label=''):
    """One satellite cell."""
    if not r.get('pmap'):
        return (f'<td><div class="cap">{rank}. {r["name"]}<br>'
                f'<span class="sub">（缺峰值绿度卫星图）</span></div></td>')
    url = 'file://' + r['pmap']
    pct_txt = (f'超过周边约 {r["pct"]}% 的地块（{r["verdict"]}）' if r['pct'] >= 0
               else (r.get('note') or '花生单列'))
    score_txt = f'综合分 {r["score"]:.1f}' if r.get('score') is not None else ''
    weak_txt = f'弱占比 {r["weak_raw"]:.1f}%' if r.get('weak_raw') is not None else ''
    y3_txt = ''
    if r.get('y3_delta') is not None:
        arrow = '↑' if r['y3_delta'] >= 0 else '↓'
        y3_txt = f'近三年峰值{arrow}{abs(r["y3_delta"]):.2f}'
    label = role_label + (f'第{rank}名' if rank else '')
    return (
        f'<td><img src="{url}" alt="{r["name"]}">'
        f'<div class="cap">{label} {r["name"]}<br>'
        f'<span class="sub">'
        + (f'{score_txt} · ' if score_txt else '')
        + pct_txt
        + (f' · {weak_txt}' if weak_txt else '')
        + (f' · {y3_txt}' if y3_txt else '')
        + f' · {r["mu"]:.0f}亩/{r["n"]}块'
        + (f' · 图源 {r.get("pmap_src")}' if r.get('pmap_src') else '')
        + '</span></div></td>'
    )


def select_fig_rows(crop, ranked, prov):
    """Which projects to show on satellite page."""
    if crop == '花生':
        return [(1, ranked[0])] if ranked else []
    n = len(ranked)
    # small provinces: show all
    if prov in ('河南', '山东', '山西') or n <= 6:
        return [(i + 1, r) for i, r in enumerate(ranked)]
    # Hebei large: top2 + bottom2
    picks = []
    for i, r in enumerate(ranked[:2], 1):
        picks.append((i, r))
    bot = ranked[-2:]
    for j, r in enumerate(bot):
        rk = n - len(bot) + 1 + j
        if r not in [x[1] for x in picks]:
            picks.append((rk, r))
    return picks


def satellite_html(crop, ranked, prov):
    if not ranked or crop == '花生' and not ranked[0].get('pmap'):
        # peanut: still try show project pmap as footprint
        if crop == '花生' and ranked and ranked[0].get('pmap'):
            pass
        elif not any(r.get('pmap') for r in ranked):
            return (f'<h2>{crop}卫星图对比</h2>'
                    f'<p class="note">本作物所选项目暂无可用峰值绿度卫星图，已跳过。</p>')

    picks = select_fig_rows(crop, ranked, prov)
    shown = [r for _, r in picks if r.get('pmap')]
    missing = [r['name'] for _, r in picks if not r.get('pmap')]

    bits = [f'<h2>{crop}卫星图对比</h2>']
    bits.append(
        '<p class="legend">峰值绿度叠卫星底图：<span class="r">红/暖色偏弱</span>，'
        '<span class="g">绿/冷色偏好</span>。并排对照可直接看项目间田块差异；'
        '名次按综合分（含近三年）排序。</p>'
    )
    if prov in ('河北',) and len(ranked) > 6:
        bits.append(
            f'<p class="note">河北{crop}共 {len(ranked)} 项，本页展示前 2 与后 2；'
            f'完整名次见表。</p>'
        )
    # pair into rows of 2
    cells = [fig_cell(r, rk) for rk, r in picks]
    rows = []
    for i in range(0, len(cells), 2):
        pair = cells[i:i + 2]
        if len(pair) == 1:
            pair.append('<td></td>')
        rows.append('<tr>' + ''.join(pair) + '</tr>')
    bits.append('<table class="grid">' + ''.join(rows) + '</table>')
    if missing:
        bits.append(f'<p class="note">缺图已跳过：{"、".join(missing)}。</p>')

    # optional ring for head vs tail when both have ring and n>=2
    if crop != '花生' and len(ranked) >= 2:
        a, b = ranked[0], ranked[-1]
        if a.get('ring') and b.get('ring') and a is not b:
            bits.append('<h3>头尾与周边对比曲线（辅助）</h3>')
            bits.append(
                '<p class="legend">曲线对照项目相对周边同季耕地的季节走势；'
                '作区位描述对照；综合分已改用相对周边变化，不再用绝对高低入分。</p>'
            )
            def _ring_sub(x):
                bits = []
                if x.get('score') is not None:
                    bits.append(f'综合分 {x["score"]:.1f}')
                bits.append(f'超过周边约 {x["pct"]}% 的地块（{x["verdict"]}）')
                if x.get('y3_delta') is not None:
                    ar = '↑' if x['y3_delta'] >= 0 else '↓'
                    bits.append(f'近三年峰值{ar}{abs(x["y3_delta"]):.2f}')
                return ' · '.join(bits)
            bits.append(
                '<table class="grid"><tr>'
                f'<td><img src="file://{a["ring"]}" alt="ring">'
                f'<div class="cap">第1名 {a["name"]}<br><span class="sub">{_ring_sub(a)}</span></div></td>'
                f'<td><img src="file://{b["ring"]}" alt="ring">'
                f'<div class="cap">第{len(ranked)}名 {b["name"]}<br><span class="sub">{_ring_sub(b)}</span></div></td>'
                '</tr></table>'
            )
    return '\n'.join(bits)


def conclusion_html(prov, by_crop, all_rows):
    n_proj = len({r.get('base_key') or r['key'] for r in all_rows})
    total_mu = sum(r['mu'] for r in all_rows)
    peanut_rows = by_crop.get('花生') or []
    peanut_mu = sum(r['mu'] for r in peanut_rows)
    smalls = [r for r in all_rows if r.get('small')]
    n_split = sum(1 for r in all_rows if r.get('season_split'))

    bits = []
    crop_bits = []
    for c in ('春玉米', '夏玉米', '花生'):
        if not by_crop.get(c):
            continue
        lab = f'{c} {_b(len(by_crop[c]))} 项'
        if c in ('春玉米', '夏玉米') and n_split:
            lab += '（含混种分列）' if any(x.get('season_split') for x in by_crop[c]) else ''
        crop_bits.append(lab)
    bits.append(
        f'<p><b>1. 规模与作物结构。</b>本省纳入 {_b(n_proj)} 个项目、玉米合计约 '
        f'{_b(f"{total_mu:.1f}")} 亩 / {_b(sum(r["n"] for r in all_rows))} 块'
        + (f'；另夏花生约 {_b(f"{peanut_mu:.1f}")} 亩（不并入玉米）' if peanut_mu else '')
        + '。作物分列：'
        + '、'.join(crop_bits)
        + '。春夏混种按季拆行入榜（亩数分列、不双计）；'
        '<b>周边对比均为同季</b>（春对春、夏对夏）。'
        '省级排行按<strong>综合分</strong>从高到低：'
        '综合分 = 0.50×同地块近三年分 + 0.30×田内分 + 0.20×相对周边变化分；'
        '近三年分＝峰值水平（高位高分、低位低分，不以微涨/趋势主导）。'
        '<b>不含</b>「超过周边约 N% 的地块」绝对高低（该列仅描述）。'
        '相对周边走强加分、走弱减分；常年偏低但今年差不多→变化分约中性。缺某项权重归一。'
        '解读上「超过周边偏低」不能一篇盖全：须对照近三年相对周边位置（区位常态/走弱/好转）'
        '与同地块峰值、弱占比一起看。后文卫星图用峰值绿度（红偏弱、绿偏好）对照差异。</p>'
    )

    # overall distribution across corn projects
    corn = [r for r in all_rows]
    point = 2
    if corn:
        bits.append(
            f'<p><b>{point}. 整体水平（综合分与分项）。</b>'
            f'{verdict_distribution(corn)}。'
        )
        pcts = [r['pct'] for r in corn if r['pct'] >= 0]
        weaks = [r['weak_raw'] for r in corn if r.get('weak_raw') is not None]
        scores = [r['score'] for r in corn if r.get('score') is not None]
        if scores:
            bits.append(
                f'综合分约 {_b(f"{min(scores):.1f}")}～{_b(f"{max(scores):.1f}")}'
                f'，均值约 {_b(f"{sum(scores)/len(scores):.1f}")}。'
            )
        if pcts:
            bits.append(
                f'超过周边约 {_b(min(pcts))}%～{_b(max(pcts))}% 的地块'
                f'，均值约 {_b(f"{sum(pcts)/len(pcts):.0f}")}%'
                f'（{_color_verdict(pct_verdict(int(round(sum(pcts)/len(pcts)))))}）。'
            )
        if weaks:
            bits.append(
                f'持续弱占比约 {_b(f"{min(weaks):.1f}")}%～{_b(f"{max(weaks):.1f}")}%'
                f'，均值约 {_b(f"{sum(weaks)/len(weaks):.1f}")}%。'
            )
        deltas = [r['y3_delta'] for r in corn if r.get('y3_delta') is not None]
        if deltas:
            up = sum(1 for d in deltas if d >= 0.02)
            dn = sum(1 for d in deltas if d <= -0.02)
            bits.append(
                f'近三年同地块峰值绿度相对往年均值：上升 {_b(up)} 项、下降 {_b(dn)} 项'
                f'（差约 {_b(f"{min(deltas):+.2f}")}～{_b(f"{max(deltas):+.2f}")}）。'
            )
        bits.append('</p>')
        point += 1

    for crop in ('春玉米', '夏玉米', '花生'):
        ranked = by_crop.get(crop) or []
        if not ranked:
            continue
        if crop == '花生':
            bits.append(f'<p><b>{point}. 夏花生（单列）。</b>{reason_one(ranked[0], role="solo")}</p>')
            point += 1
            continue

        bits.append(
            f'<p><b>{point}. {crop}综述。</b>共 {_b(len(ranked))} 项、约 '
            f'{_b(f"{sum(r["mu"] for r in ranked):.1f}")} 亩。判定分布：'
            f'{verdict_distribution(ranked)}。</p>'
        )
        point += 1

        top = ranked[:min(2, len(ranked))]
        bot = []
        if len(ranked) >= 3:
            bot = [x for x in ranked[-min(2, len(ranked) - 2):] if x not in top]

        bits.append(f'<p><b>{point}. {crop}头部靠前的证据。</b>{common_evidence(top, "top")}</p>')
        bits.append('<ul class="reason">')
        for i, r in enumerate(top, 1):
            bits.append('<li>' + reason_one(r, rank=i, role='top') + '</li>')
        bits.append('</ul>')
        point += 1

        if bot:
            bits.append(f'<p><b>{point}. {crop}尾部靠后的证据。</b>{common_evidence(bot, "bot")}</p>')
            bits.append('<ul class="reason">')
            for r in bot:
                bits.append('<li>' + reason_one(r, rank=ranked.index(r) + 1, role='bot') + '</li>')
            bits.append('</ul>')
            point += 1

    if smalls:
        names = '、'.join(short_name(r['name']) + f'（{r["n"]}块/{r["mu"]:.0f}亩）' for r in smalls[:8])
        more = f'等 {_b(len(smalls))} 项' if len(smalls) > 8 else f'共 {_b(len(smalls))} 项'
        bits.append(
            f'<div class="warn"><b>{point}. 小样本提示。</b>{more}：{names}。'
            f'地块数很少或亩数偏小时，单块波动会明显影响「超过周边」与弱占比，'
            f'名次宜作对照参考，不宜单独外推到更大范围。</div>'
        )
        point += 1

    seen_drought = set()
    for r in all_rows:
        bk = r.get('base_key') or r['key']
        if r.get('drought_mu') and bk not in seen_drought:
            seen_drought.add(bk)
            bits.append(
                f'<p><b>{point}. 已写入报告的受旱。</b>{(r["name"].split("（")[0] if r.get("season_split") else r["name"])}：'
                f'{r.get("drought_note") or ""}约 {_r(f"{r["drought_mu"]:.1f}")} 亩'
                + ('；本季未写出可确认受涝。' if r.get('flood_mu') in (0, 0.0, None) else '')
                + '</p>'
            )
            point += 1

    bits.append(
        f'<p><b>{point}. 使用提示。</b>正式排行、逐条解读与卫星图对比见后文；'
        f'指标口径与各项目报告一致。遥感数据不一定准确，结论仅供参考。</p>'
    )
    return '<h1>一、省级核心结论</h1>\n' + '\n'.join(bits)


def build_province_html(prov, rows):
    by_crop = defaultdict(list)
    for r in rows:
        by_crop[r['crop']].append(r)
    peanut = None
    for r in rows:
        pr = peanut_row_from(r)
        if pr:
            peanut = pr
            break
    if peanut:
        by_crop['花生'] = [peanut]

    for crop in list(by_crop):
        if crop != '花生':
            by_crop[crop] = rank_rows(by_crop[crop])

    crops_present = [c for c in ('春玉米', '夏玉米', '花生') if by_crop.get(c)]
    total_mu = sum(r['mu'] for r in rows)
    total_n = sum(r['n'] for r in rows)
    n_proj = len({r.get('base_key') or r['key'] for r in rows})
    scale = f'{total_mu:.1f} 亩 · {total_n} 个地块 · {n_proj} 个项目'
    if peanut:
        scale += f'（另花生 {peanut["mu"]:.1f} 亩）'

    n_figs = 0
    cover = make_cover_html(dict(
        name=f'{prov}综合', province=prov, season=season_label(crops_present),
        mu=f'{total_mu:.1f}', n_parcels=total_n, report_date=REPORT_DATE,
        title=f'{prov}省遥感长势综合分析报告',
        report_type='省级综合长势分析（含卫星对比）',
        scale=scale, show_proj=False,
    ))

    body = [conclusion_html(prov, by_crop, rows)]
    body.append('<h1 class="pagebreak">二、分作物正式排行与解读</h1>')
    for crop in ('春玉米', '夏玉米', '花生'):
        ranked = by_crop.get(crop) or []
        if not ranked:
            continue
        body.append(table_html(crop, ranked))
        body.append(interpret_html(crop, ranked))

    body.append('<h1 class="pagebreak">三、项目级卫星图对比</h1>')
    body.append(
        '<p>以下为项目峰值绿度卫星叠图，便于直接对照头尾/各项目田块差异。'
        '图例：<span class="r">红偏弱</span>、<span class="g">绿偏好</span>。</p>'
    )
    for crop in ('春玉米', '夏玉米', '花生'):
        ranked = by_crop.get(crop) or []
        if not ranked:
            continue
        html = satellite_html(crop, ranked, prov)
        body.append(html)
        picks = select_fig_rows(crop, ranked, prov)
        n_figs += sum(1 for _, r in picks if r.get('pmap'))
        # count ring pair as +2 if added
        if crop != '花生' and len(ranked) >= 2 and ranked[0].get('ring') and ranked[-1].get('ring'):
            if prov in ('河南', '山东', '山西') or len(ranked) > 1:
                n_figs += 2  # head+tail ring

    body.append(
        '<div class="foot">提示：遥感数据不一定准确，分析结论仅供参考，不作为最终准入或交易依据。<br>'
        '乡合农服 · 用遥感数据，服务现代农业</div>'
    )

    html = (
        f'<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<title>{prov}省遥感长势综合分析报告</title>'
        f'<style>{CSS}</style></head><body>'
        f'{cover}{"".join(body)}</body></html>'
    )
    meta = dict(
        province=prov, n_proj=n_proj, total_mu=total_mu, total_n=total_n,
        crops={c: len(by_crop[c]) for c in crops_present},
        n_figs=n_figs,
        ranks={c: [
            dict(rank=i + 1, name=x['name'], score=x.get('score'),
                 pct=x['pct'], verdict=x['verdict'],
                 weak=x.get('weak_raw'), mu=x['mu'], n=x['n'],
                 base_key=x.get('base_key'), season=x.get('season'),
                 season_split=bool(x.get('season_split')),
                 S_ring=x.get('S_ring'), S_weak=x.get('S_weak'), S_peak=x.get('S_peak'),
                 S_level=x.get('S_level'), S_change=x.get('S_change'),
                 S_y3=x.get('S_peak'), S_ring_delta=x.get('S_ring_delta'),
                 ring_delta_pp=x.get('ring_delta_pp'),
                 y3_delta=x.get('y3_delta'), y3_delta_rel=x.get('y3_delta_rel'),
                 peak24=x.get('peak24'), peak25=x.get('peak25'), peak26=x.get('peak26'),
                 rank24=x.get('rank24'), rank25=x.get('rank25'), rank26=x.get('rank26'),
                 ring_yoy_tag=x.get('ring_yoy_tag'), ring_yoy_short=x.get('ring_yoy_short'),
                 has_pmap=bool(x.get('pmap')))
            for i, x in enumerate(by_crop[c])
        ] for c in crops_present},
        fig_picks={c: [
            dict(rank=rk, name=r['name'], has_pmap=bool(r.get('pmap')), src=r.get('pmap_src'))
            for rk, r in select_fig_rows(c, by_crop[c], prov)
        ] for c in crops_present},
    )
    return html, meta


def render_pdf(html_path, pdf_path):
    subprocess.run(
        ['google-chrome', '--headless=new', '--no-sandbox', '--disable-gpu',
         '--no-pdf-header-footer', f'--print-to-pdf={pdf_path}', 'file://' + html_path],
        capture_output=True, timeout=300, check=False,
    )
    if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) < 1000:
        raise RuntimeError(f'PDF failed: {pdf_path}')


def pdf_pages(pdf_path):
    info = subprocess.run(['pdfinfo', pdf_path], capture_output=True, text=True).stdout
    m = re.search(r'Pages:\s+(\d+)', info)
    return int(m.group(1)) if m else None


def build_all():
    os.makedirs(OUT_DIR, exist_ok=True)
    rows_all = []
    for P in PROJECTS:
        rows_all.extend(load_project_row(P))
    by_prov = defaultdict(list)
    for r in rows_all:
        by_prov[r['province']].append(r)

    results = []
    for prov in PROVINCES:
        rows = by_prov.get(prov) or []
        if not rows:
            continue
        html, meta = build_province_html(prov, rows)
        tag = f'{prov}遥感长势综合分析报告'
        html_path = os.path.join(OUT_DIR, tag + '.html')
        pdf_path = os.path.join(OUT_DIR, tag + '.pdf')
        open(html_path, 'w', encoding='utf-8').write(html)
        render_pdf(html_path, pdf_path)
        pages = pdf_pages(pdf_path)
        txt = subprocess.run(
            ['pdftotext', '-layout', pdf_path, '-'], capture_output=True, text=True
        ).stdout
        meta['pdf'] = pdf_path
        meta['html'] = html_path
        meta['pages'] = pages
        meta['has_sat'] = '卫星图对比' in txt and '峰值绿度' in txt
        meta['has_why'] = ('靠前的证据' in txt) or ('排行解读' in txt)
        meta['has_score'] = '综合分' in txt
        meta['has_y3'] = '近三年' in txt
        meta['has_ring_yoy'] = ('区位常态' in txt) or ('相对周边好于往年' in txt) or ('相对周边比往年更弱' in txt)
        meta['has_nuance'] = '不能单凭今年' in txt or '一篇盖不全' in txt or '区位/立地常态' in txt
        meta['bad'] = [b for b in ('百分位', '置信度', '选地评估', '巡田优先', '可能施肥') if b in txt]
        # sample head/tail
        sample = ''
        for line in txt.splitlines():
            if '超过周边约' in line and '持续弱' in line and len(line.strip()) > 35:
                sample = line.strip()[:150]
                break
        meta['sample'] = sample
        json.dump(meta, open(os.path.join(OUT_DIR, tag + '_meta.json'), 'w'),
                  ensure_ascii=False, indent=2)
        results.append(meta)
        print(f'{prov}: pages={pages} figs≈{meta["n_figs"]} sat={meta["has_sat"]} '
              f'why={meta["has_why"]} score={meta["has_score"]} y3={meta["has_y3"]} '
              f'ring_yoy={meta.get("has_ring_yoy")} nuance={meta.get("has_nuance")} bad={meta["bad"]}')
    json.dump(results, open(os.path.join(OUT_DIR, 'SUMMARY.json'), 'w'),
              ensure_ascii=False, indent=2)
    return results


if __name__ == '__main__':
    build_all()
