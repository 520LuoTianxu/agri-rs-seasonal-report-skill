# -*- coding: utf-8 -*-
"""Season classify + multi-stage weak-growth + peak NDRE stats from pixel npz."""
import json, os, numpy as np
from catalog import DATA

os.makedirs(DATA, exist_ok=True)

def crop_to_lab(z, LAB, pad=30):
    ys,xs=np.where(LAB>0)
    if len(ys)==0:
        return z, LAB, 0, 0
    r0=max(int(ys.min())-pad,0); r1=min(int(ys.max())+pad+1, LAB.shape[0])
    c0=max(int(xs.min())-pad,0); c1=min(int(xs.max())+pad+1, LAB.shape[1])
    sl=(slice(r0,r1), slice(c0,c1))
    zc={k: (z[k] if z[k].ndim==0 or k=='dates' else (z[k][:,r0:r1,c0:c1] if z[k].ndim==3 else z[k][r0:r1,c0:c1])) for k in z.files}
    # keep as dict-like
    class Z:
        def __getitem__(self,k):
            return zc[k]
        @property
        def files(self):
            return list(zc)
    return Z(), LAB[sl], float(z['x0'])+c0*10, float(z['y1'])-r0*10

def load_cube(P):
    """Return dates(mm-dd), LAB (1..n parcels), bands dict, x0, y1, PL, mu."""
    PL = json.load(open(P['parcels']))
    z = np.load(f"{P['npz_dir']}/{P['npz_cl']}_2026.npz")
    dates = [str(x)[5:] if len(str(x)) > 5 else str(x) for x in z['dates']]
    LAB = z['LAB'].astype(np.int32)
    if P.get('labmap'):
        lm = json.load(open(P['labmap']))
        LAB = np.array(lm['map'], dtype=np.int32)[LAB]
    return dates, LAB, z, float(z['x0']), float(z['y1']), PL, np.array([p['mu'] for p in PL], float)

def clear_mask(z, j, strict=False):
    b02_th = 0.12 if strict else 0.2
    return (np.isin(z['SCL'][j], [4, 5]) & np.isfinite(z['B04'][j]) &
            (z['B02'][j] < b02_th) & (z['B04'][j] > 0) & (z['B05'][j] > 0))

def date_covers(dates, z, LAB):
    m = LAB > 0
    out=[]
    for i,d in enumerate(dates):
        if not m.any():
            out.append(0.0); continue
        ok=clear_mask(z,i)
        out.append(float(ok[m].mean()))
    return out

def idx_at(dates, z, LAB, target, min_cover=0.35, covers=None):
    """Nearest date with enough clear cover on project pixels."""
    if covers is None:
        covers=date_covers(dates,z,LAB)
    cands=[]
    for i,d in enumerate(dates):
        cov=covers[i]
        cands.append((abs(_day(d)-_day(target)), -cov, i, d, cov))
    cands.sort()
    for _,__,i,d,cov in cands:
        if cov>=min_cover:
            return i,d,cov
    if cands:
        _,__,i,d,cov=cands[0]
        return i,d,cov
    raise RuntimeError(f'no date near {target}')

def _day(mmdd):
    a, b = mmdd.split('-')
    return int(a) * 31 + int(b)

def vi(z, j, kind):
    ok = clear_mask(z, j)
    b = 'B04' if kind == 'NDVI' else 'B05'
    with np.errstate(all='ignore'):
        v = np.where(ok, (z['B08'][j] - z[b][j]) / (z['B08'][j] + z[b][j]), np.nan)
    v[(v > 1) | (v < -1)] = np.nan
    return v

def classify_season(dates, z, LAB, PL, spring_hint=False):
    """Return list of 'spring'|'summer' per parcel from mid-June NDVI."""
    # find date near 06-15
    try:
        j, d, cov = idx_at(dates, z, LAB, '06-15', 0.25)
    except Exception:
        return ['spring' if spring_hint else 'summer'] * len(PL)
    V = vi(z, j, 'NDVI')
    # also need late peak date ~08-14
    try:
        j2, d2, _ = idx_at(dates, z, LAB, '08-14', 0.25)
        V2 = vi(z, j2, 'NDVI')
    except Exception:
        V2 = None
    out = []
    for k in range(len(PL)):
        m = LAB == k + 1
        if not m.any():
            out.append('spring' if spring_hint else 'summer'); continue
        med = float(np.nanmedian(V[m]))
        if not np.isfinite(med):
            out.append('spring' if spring_hint else 'summer'); continue
        # spring if already green mid-June; summer if still bare
        if med >= 0.35:
            out.append('spring')
        elif med <= 0.22:
            out.append('summer')
        else:
            # ambiguous: use spring_hint / late peak
            if V2 is not None:
                med2 = float(np.nanmedian(V2[m]))
                # if still rising a lot into August → summer-ish; if already high mid-Jun → spring
                out.append('summer' if med < 0.3 and med2 > med + 0.15 else ('spring' if spring_hint else 'summer'))
            else:
                out.append('spring' if spring_hint else 'summer')
    return out

# target stages by season (name, target date, index, threshold)
ST_SPRING = [
    ('拔节初', '06-15', 'NDVI', 0.25),
    ('拔节', '06-28', 'NDRE', 0.15),
    ('大喇叭口', '07-13', 'NDRE', 0.15),
    ('抽雄吐丝', '07-23', 'NDRE', 0.15),
    ('灌浆', '08-14', 'NDRE', 0.15),
]
ST_SUMMER = [
    ('拔节初', '07-05', 'NDVI', 0.25),
    ('拔节', '07-20', 'NDRE', 0.15),
    ('大喇叭口', '08-01', 'NDRE', 0.15),
    ('抽雄吐丝', '08-14', 'NDRE', 0.15),
    ('灌浆', '08-31', 'NDRE', 0.15),
]

def run_weak(P):
    dates, LAB0, z0, x0, y1, PL, mu = load_cube(P)
    z, LAB, x0, y1 = crop_to_lab(z0, LAB0)
    covers = date_covers(dates, z, LAB)
    seasons = classify_season(dates, z, LAB, PL, P.get('spring', False))
    # if almost all one season, force single group to avoid tiny mixed groups
    n_sp = sum(1 for s in seasons if s == 'spring')
    n_su = len(seasons) - n_sp
    if n_sp > 0 and n_su > 0 and min(n_sp, n_su) <= 1 and len(PL) <= 3:
        # keep mixed for 3-parcel cases with clear split; else majority
        pass
    if n_sp == 0 or n_su == 0:
        groups = {'spring' if n_sp else 'summer': list(range(len(PL)))}
    else:
        # require meaningful area in both
        mu_sp = sum(mu[i] for i, s in enumerate(seasons) if s == 'spring')
        mu_su = float(mu.sum()) - mu_sp
        if min(mu_sp, mu_su) < 0.05 * float(mu.sum()):
            maj = 'spring' if mu_sp >= mu_su else 'summer'
            groups = {maj: list(range(len(PL)))}
            seasons = [maj] * len(PL)
        else:
            groups = {
                'spring': [i for i, s in enumerate(seasons) if s == 'spring'],
                'summer': [i for i, s in enumerate(seasons) if s == 'summer'],
            }

    results = {}
    for gr, KS in groups.items():
        ST0 = ST_SPRING if gr == 'spring' else ST_SUMMER
        # resolve actual dates
        ST = []
        used = set()
        for nm, td, ix, th in ST0:
            j, d, cov = idx_at(dates, z, LAB, td, 0.30, covers=covers)
            # avoid duplicate dates: nudge forward
            tries = 0
            while d in used and tries < 5:
                # find next later date
                later = [(i, dd) for i, dd in enumerate(dates) if _day(dd) > _day(d)]
                if not later:
                    break
                # pick nearest later with cover
                best = None
                for i, dd in later:
                    ok = clear_mask(z, i); m = LAB > 0
                    cov2 = float(ok[m].mean()) if m.any() else 0
                    if cov2 >= 0.30:
                        best = (i, dd, cov2); break
                if best is None:
                    break
                j, d, cov = best
                tries += 1
            used.add(d)
            ST.append((d, nm, ix, th, j, cov))

        nS = len(ST)
        WK = np.zeros((nS,) + LAB.shape, bool)
        VAL = np.zeros_like(WK)
        REL = np.full((nS,) + LAB.shape, np.nan, np.float32)
        tab = {}
        for s, (dt, nm, ix, th, j, cov) in enumerate(ST):
            V = vi(z, j, ix)
            for k in KS:
                m = LAB == k + 1
                if not m.any():
                    tab[(k, s)] = dict(st='cloud'); continue
                v = V[m]; fin = np.isfinite(v); c = fin.mean()
                if c < 0.5:
                    tab[(k, s)] = dict(st='cloud'); continue
                md = float(np.nanmedian(v))
                REL[s][m] = (v / md - 1) * 100
                # yellowing skip for last spring stage
                if gr == 'spring' and s == nS - 1 and (k, nS - 2) in tab and tab[(k, nS - 2)].get('med') and md < tab[(k, nS - 2)]['med'] * 0.9:
                    tab[(k, s)] = dict(st='yellow', med=md); continue
                w = fin & (v < md * (1 - th))
                WK[s][m] = w; VAL[s][m] = fin
                tab[(k, s)] = dict(st='ok', med=md, frac=float(w.sum() / fin.sum()), mu=float(w.sum() / fin.sum() * mu[k]))

        cnt = WK.sum(0)
        post = VAL[1:].sum(0) if nS > 1 else VAL[0]
        allpost = (post >= max(1, nS - 2)) & (WK[1:].sum(0) == post) if nS > 1 else WK[0]
        per = []
        for k in KS:
            m = LAB == k + 1; n = max(int(m.sum()), 1)
            cells = [tab.get((k, s), dict(st='cloud')) for s in range(nS)]
            per.append(dict(
                name=PL[k]['name'], lid=str(PL[k].get('land_id', k)), idx=k,
                mu=float(mu[k]),
                cells=cells,
                p2=float((cnt[m] >= 2).sum() / n * mu[k]),
                p2f=float((cnt[m] >= 2).mean()),
                pall=float(allpost[m].sum() / n * mu[k]),
            ))
        tot = []
        for s in range(nS):
            rr = [tab[(k, s)] for k in KS if tab.get((k, s), {}).get('st') == 'ok']
            a = sum(mu[k] for k in KS if tab.get((k, s), {}).get('st') == 'ok')
            tot.append(dict(mu=sum(x['mu'] for x in rr), area=float(a), n=len(rr)))
        T = float(mu[KS].sum()); P2 = sum(x['p2'] for x in per); PA = sum(x['pall'] for x in per)
        results[gr] = dict(
            ST=[(d, nm, ix, th) for d, nm, ix, th, j, cov in ST],
            ST_full=[dict(d=d, nm=nm, ix=ix, th=th, j=j, cov=cov) for d, nm, ix, th, j, cov in ST],
            per=per, tot=tot, T=T, P2=P2, PA=PA, KS=KS,
        )
        np.savez_compressed(
            f"{DATA}/{P['key']}_ms_{gr}.npz",
            REL=REL, CNT=cnt.astype('int8'), VAL=VAL.astype(bool), WK=WK.astype(bool),
            LAB=LAB, x0=x0, y1=y1,
        )

    # peak NDRE (post-jointing window) per parcel — all pixels mean
    # window depends on majority season
    maj = max(results.keys(), key=lambda g: results[g]['T'])
    if maj == 'spring':
        pa, pb = '06-15', '08-20'
    else:
        pa, pb = '07-01', '09-15'
    ix = [i for i, d in enumerate(dates) if pa <= d <= pb]
    # keep only decent-cover dates; subsample to <=8 for speed
    scored=[]
    mproj = LAB>0
    for i in ix:
        ok=clear_mask(z,i); cov=float(ok[mproj].mean()) if mproj.any() else 0
        if cov>=0.35: scored.append((i,cov))
    if len(scored)>8:
        step=max(1,len(scored)//8); scored=scored[::step][:8]
    stack=[vi(z,i,'NDRE') for i,_ in scored]
    if stack:
        with np.errstate(all='ignore'):
            pk = np.nanmax(np.stack(stack, 0), 0)
    else:
        pk = np.full(LAB.shape, np.nan)
    parcel_peak = []
    for k in range(len(PL)):
        m = LAB == k + 1
        v = pk[m]; fin = np.isfinite(v)
        if fin.sum() < 0.3 * max(m.sum(), 1):
            parcel_peak.append(None)
        else:
            parcel_peak.append(float(np.nanmean(v[fin])))
    # project area-weighted
    ok = [i for i, v in enumerate(parcel_peak) if v is not None]
    if ok:
        proj_peak = float(np.average([parcel_peak[i] for i in ok], weights=mu[ok]))
        med_peak = float(np.median([parcel_peak[i] for i in ok]))
    else:
        proj_peak = med_peak = None

    # low area vs group median (15%)
    low_rows = []
    for gr, M in results.items():
        vals = [(x['idx'], parcel_peak[x['idx']]) for x in M['per'] if parcel_peak[x['idx']] is not None]
        if not vals:
            continue
        gmed = float(np.median([v for _, v in vals]))
        for idx, v in vals:
            m = LAB == idx + 1
            # pixels below 85% of parcel median of peak? use group median
            fin = np.isfinite(pk[m])
            if fin.sum() == 0: continue
            weak = fin & (pk[m] < gmed * 0.85)
            frac = float(weak.sum() / fin.sum())
            low_rows.append(dict(
                name=PL[idx]['name'], idx=idx, g=gr, mu=float(mu[idx]),
                mean=v, med=float(np.nanmedian(pk[m])),
                low=frac, lowmu=frac * float(mu[idx]), gmed=gmed,
            ))

    out = dict(
        key=P['key'], seasons=seasons, groups={g: results[g] for g in results},
        parcel_peak=parcel_peak, proj_peak=proj_peak, med_peak=med_peak,
        peak_window=(pa, pb), low_rows=low_rows,
        dates=dates, n_parcels=len(PL), total_mu=float(mu.sum()),
        x0=x0, y1=y1, epsg=P['epsg'],
    )
    # JSON-safe (drop huge)
    js = {k: v for k, v in out.items() if k != 'groups'}
    js['groups'] = {}
    for g, M in results.items():
        js['groups'][g] = dict(ST=M['ST'], ST_full=M['ST_full'], per=M['per'], tot=M['tot'],
                               T=M['T'], P2=M['P2'], PA=M['PA'], KS=M['KS'])
    path = f"{DATA}/{P['key']}_weak.json"
    json.dump(js, open(path, 'w'), ensure_ascii=False)
    print(P['key'], 'groups', list(results), 'P2',
          {g: round(results[g]['P2'], 1) for g in results},
          'proj_peak', proj_peak)
    return out

if __name__ == '__main__':
    import sys
    from catalog import PROJECTS, by_key
    keys = sys.argv[1:] or [p['key'] for p in PROJECTS]
    for k in keys:
        P = by_key(k)
        try:
            run_weak(P)
        except Exception as e:
            print('FAIL', k, e)
            import traceback; traceback.print_exc()
