# -*- coding: utf-8 -*-
"""Pixel-level lon/lat figures: stages RGB, peak NDRE map, multi-stage weak map."""
import json, os, numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.colors import TwoSlopeNorm
from pyproj import Transformer
from analyze import load_cube, vi, idx_at, clear_mask, crop_to_lab
from catalog import DATA, FIG

F = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
fm.fontManager.addfont(F)
plt.rcParams['font.sans-serif'] = ['Noto Sans CJK JP']
plt.rcParams['axes.unicode_minus'] = False
os.makedirs(FIG, exist_ok=True)

def _inv(epsg, x0, y1):
    return Transformer.from_crs(epsg, 4326, always_xy=True).transform

def mesh(inv, x0, y1, s):
    r = np.arange(s[0].start, s[0].stop + 1)
    c = np.arange(s[1].start, s[1].stop + 1)
    X, Y = np.meshgrid(x0 + c * 10, y1 - r * 10)
    return inv(X, Y)

def show(a, inv, x0, y1, s, v, **kw):
    LO, LA = mesh(inv, x0, y1, s)
    return a.pcolormesh(LO, LA, np.ma.masked_invalid(v), shading='flat',
                        edgecolors='none', antialiased=False, **kw)

def show_rgb(a, inv, x0, y1, s, im):
    LO, LA = mesh(inv, x0, y1, s)
    q = a.pcolormesh(LO, LA, np.zeros(im.shape[:2]), shading='flat', antialiased=False)
    q.set_array(None); q.set_facecolor(im.reshape(-1, 3)); q.set_edgecolor('face'); q.set_linewidth(0)

def rgbz(z, j, s, f=1.0):
    im = np.dstack([z[k][j][s] for k in ('B04', 'B03', 'B02')]).astype(float)
    return np.clip(np.nan_to_num(np.clip(im * 3.2 * f, 0, 1) ** 0.85), 0, 1)

def geo(a, lat, fs=7):
    a.set_aspect(1 / np.cos(np.radians(lat)))
    a.set_xlabel('经度（°E）', fontsize=fs)
    a.set_ylabel('纬度（°N）', fontsize=fs)
    a.tick_params(labelsize=fs - 1)
    a.ticklabel_format(useOffset=False, style='plain')

def outl(a, PL, col='k', lw=.5):
    for p in PL:
        g = p['geom']
        rs = [g['coordinates'][0]] if g['type'] == 'Polygon' else [q[0] for q in g['coordinates']]
        for r_ in rs:
            r_ = np.array(r_); a.plot(r_[:, 0], r_[:, 1], color=col, lw=lw)

def sl_pad(LAB, pad=20):
    ys, xs = np.where(LAB > 0)
    if len(ys) == 0:
        return (slice(0, LAB.shape[0]), slice(0, LAB.shape[1]))
    return (slice(max(ys.min() - pad, 0), ys.max() + pad),
            slice(max(xs.min() - pad, 0), xs.max() + pad))

def make_figs(P, weak=None):
    dates, LAB0, z0, x0, y1, PL, mu = load_cube(P)
    z, LAB, x0, y1 = crop_to_lab(z0, LAB0)
    inv = _inv(P['epsg'], x0, y1)
    # centroid lat
    ys, xs = np.where(LAB > 0)
    if len(ys):
        lo, la = inv(x0 + xs.mean() * 10, y1 - ys.mean() * 10)
    else:
        la = 35.0
    sl = sl_pad(LAB)
    out_prefix = f"{P['fig_dir']}/{P['fig_prefix']}"
    os.makedirs(P['fig_dir'], exist_ok=True)
    pipe_prefix = f"{FIG}/{P['key']}_"

    if weak is None:
        weak = json.load(open(f"{DATA}/{P['key']}_weak.json"))

    # ---- stages RGB: pick up to 6 dates from group stages ----
    st_dates = []
    for g, M in weak['groups'].items():
        for d, nm, ix, th in M['ST']:
            if d not in [x[0] for x in st_dates]:
                st_dates.append((d, nm))
    st_dates = sorted(st_dates, key=lambda x: x[0])[:6]
    if len(st_dates) < 4:
        # fallback targets
        for td, nm in [('06-15','苗期'),('07-05','拔节'),('07-23','抽雄'),('08-14','灌浆'),('09-05','成熟')]:
            try:
                j, d, cov = idx_at(dates, z, LAB, td, 0.3)
                if d not in [x[0] for x in st_dates]:
                    st_dates.append((d, nm))
            except Exception:
                pass
        st_dates = sorted(st_dates, key=lambda x: x[0])[:6]

    n = len(st_dates) or 1
    ncols = 2; nrows = (n + 1) // 2
    fig, ax = plt.subplots(nrows, ncols, figsize=(11, 4.2 * nrows))
    ax = np.atleast_1d(ax).ravel()
    for a, (d, nm) in zip(ax, st_dates):
        j = dates.index(d)
        show_rgb(a, inv, x0, y1, sl, rgbz(z, j, sl))
        outl(a, PL, '#ffe600', .55)
        a.set_title(f'{nm}　2026-{d}', fontsize=10.5, color='#0d3b66')
        geo(a, la)
    for a in ax[len(st_dates):]:
        a.axis('off')
    plt.tight_layout()
    for path in (out_prefix + 'stages.png', pipe_prefix + 'stages.png'):
        plt.savefig(path, dpi=180)
    plt.close()

    # ---- peak NDRE pixel map ----
    pa, pb = weak['peak_window']
    ix = [i for i, d in enumerate(dates) if pa <= d <= pb]
    mproj=LAB>0; scored=[]
    for i in ix:
        ok=clear_mask(z,i); cov=float(ok[mproj].mean()) if mproj.any() else 0
        if cov>=0.35: scored.append(i)
    if len(scored)>8:
        step=max(1,len(scored)//8); scored=scored[::step][:8]
    stack=[vi(z,i,'NDRE') for i in scored]
    with np.errstate(all='ignore'):
        pk = np.nanmax(np.stack(stack, 0), 0) if stack else np.full(LAB.shape, np.nan)
    # relative to group median
    # build group med per pixel
    gmed_map = np.full(LAB.shape, np.nan)
    for g, M in weak['groups'].items():
        vals = [weak['parcel_peak'][i] for i in M['KS'] if weak['parcel_peak'][i] is not None]
        if not vals: continue
        gm = float(np.median(vals))
        for i in M['KS']:
            gmed_map[LAB == i + 1] = gm
    rel = (pk / gmed_map - 1) * 100
    rel[LAB == 0] = np.nan

    fig, axs = plt.subplots(1, 2, figsize=(12, 5.5))
    a = axs[0]
    # RGB backdrop dim + peak overlay
    # pick a mid date for backdrop
    try:
        jb, db, _ = idx_at(dates, z, LAB, '08-01' if 'summer' in weak['groups'] else '07-20', 0.2)
    except Exception:
        jb = ix[len(ix)//2] if ix else 0
    show_rgb(a, inv, x0, y1, sl, rgbz(z, jb, sl) * 0.45 + 0.2)
    m = show(a, inv, x0, y1, sl, np.where(LAB[sl] > 0, pk[sl], np.nan),
             cmap='RdYlGn', vmin=0.35, vmax=0.75)
    outl(a, PL, '#222', .4); plt.colorbar(m, ax=a, fraction=.035, label='峰值 NDRE')
    a.set_title(f'拔节后峰值 NDRE（{pa}～{pb}，10 米原始像素）', fontsize=10, color='#0d3b66')
    geo(a, la)

    a = axs[1]
    show_rgb(a, inv, x0, y1, sl, rgbz(z, jb, sl) * 0.45 + 0.2)
    norm = TwoSlopeNorm(vmin=-30, vcenter=0, vmax=30)
    m = show(a, inv, x0, y1, sl, np.where(LAB[sl] > 0, rel[sl], np.nan),
             cmap='RdYlGn', norm=norm)
    outl(a, PL, '#222', .4); plt.colorbar(m, ax=a, fraction=.035, label='相对同组中位数（%）')
    a.set_title('比同组地块中位数高或低（%）', fontsize=10, color='#0d3b66')
    geo(a, la)
    plt.tight_layout()
    for path in (out_prefix + 'pmap_px.png', pipe_prefix + 'pmap_px.png'):
        plt.savefig(path, dpi=180)
    plt.close()

    # ---- multi-stage relative maps ----
    groups = list(weak['groups'].items())
    # For each group, show stage rel panels + count
    panels = []
    for g, M in groups:
        npz = np.load(f"{DATA}/{P['key']}_ms_{g}.npz")
        REL = npz['REL']; CNT = npz['CNT']
        for s, (d, nm, ixn, th) in enumerate(M['ST']):
            panels.append((g, s, d, nm, ixn, REL[s], 'rel'))
        panels.append((g, -1, '', '偏弱期数', '', CNT.astype(float), 'cnt'))

    n = len(panels)
    if n == 0:
        return
    ncols = min(3, n)
    nrows = (n + ncols - 1) // ncols
    fig, ax = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 3.8 * nrows))
    ax = np.atleast_1d(ax).ravel()
    for a, (g, s, d, nm, ixn, arr, kind) in zip(ax, panels):
        show_rgb(a, inv, x0, y1, sl, rgbz(z, jb, sl) * 0.4 + 0.25)
        if kind == 'rel':
            norm = TwoSlopeNorm(vmin=-30, vcenter=0, vmax=30)
            m = show(a, inv, x0, y1, sl, np.where(LAB[sl] > 0, arr[sl], np.nan),
                     cmap='RdYlGn', norm=norm)
            a.set_title(f'{("春" if g=="spring" else "夏")}·{nm} {d}（{ixn}）', fontsize=9, color='#0d3b66')
        else:
            m = show(a, inv, x0, y1, sl, np.where(LAB[sl] > 0, arr[sl], np.nan),
                     cmap='YlOrRd', vmin=0, vmax=max(3, np.nanmax(arr[LAB>0]) if (LAB>0).any() else 3))
            a.set_title(f'{("春" if g=="spring" else "夏")}·偏弱期数', fontsize=9, color='#0d3b66')
        outl(a, PL, '#222', .35); geo(a, la, 6)
        plt.colorbar(m, ax=a, fraction=.04)
    for a in ax[len(panels):]:
        a.axis('off')
    plt.tight_layout()
    for path in (out_prefix + 'ms.png', pipe_prefix + 'ms.png'):
        plt.savefig(path, dpi=160)
    plt.close()
    print('figs', P['key'], 'ok')

if __name__ == '__main__':
    import sys
    from catalog import by_key
    for k in sys.argv[1:]:
        make_figs(by_key(k))
