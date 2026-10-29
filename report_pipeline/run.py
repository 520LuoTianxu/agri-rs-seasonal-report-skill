# -*- coding: utf-8 -*-
"""Orchestrate analyze → figs → build for one or many projects."""
import sys, os, json, time, traceback
sys.path.insert(0, '/workspace/report_pipeline_20261027')
from catalog import PROJECTS, by_key, STATUS, DATA, FIG
from analyze import run_weak
from geo_figs import make_figs
from build import build_one

def update_status(done, failed, pending):
    lines = ['# Report rebuild STATUS', '',
             f'Updated: {time.strftime("%Y-%m-%d %H:%M:%S")} Asia/Shanghai', '',
             f'Done: {len(done)}  Failed: {len(failed)}  Pending: {len(pending)}', '',
             '## Done']
    for x in done:
        lines.append(f"- {x['key']} | {x.get('pages','?')}p | drone={x.get('drone')} farm={x.get('farm')} | {x['pdf']}")
    lines += ['', '## Failed']
    for x in failed:
        lines.append(f"- {x['key']}: {x['err'][:300]}")
    lines += ['', '## Pending']
    for k in pending:
        lines.append(f'- {k}')
    open(STATUS, 'w').write('\n'.join(lines) + '\n')

def run_one(P, skip_ana=False, force_ana=False):
    t0 = time.time()
    weak_path=f"{DATA}/{P['key']}_weak.json"
    if force_ana or not os.path.exists(weak_path):
        run_weak(P)
    # optional drought/flood on weak parcels (side JSON; report gate inside module)
    try:
        from hazard_analyze import analyze_project as _hazard
        if P.get('hazard', True):
            flood_csv = P.get('flood_csv')
            rain_glob = P.get('rain_glob')
            kw = {}
            if flood_csv: kw['flood_csv'] = flood_csv
            if rain_glob: kw['rain_glob'] = rain_glob
            _hazard(P['key'], **kw)
    except Exception as e:
        print('hazard skip', P.get('key'), e, flush=True)
    make_figs(P)
    pages = build_one(P)
    return dict(key=P['key'], pages=pages, pdf=P['out_pdf'],
                drone=bool(P.get('uav_key')), farm=bool(P.get('farm')),
                sec=round(time.time() - t0, 1))

def main(keys):
    done, failed = [], []
    # load previous done from status if any
    pending = list(keys)
    update_status(done, failed, pending)
    for k in keys:
        P = by_key(k)
        print('=' * 60, 'RUN', k, flush=True)
        try:
            info = run_one(P)
            done.append(info)
            print('OK', info, flush=True)
        except Exception as e:
            traceback.print_exc()
            failed.append(dict(key=k, err=str(e)))
            print('FAIL', k, e, flush=True)
        pending = [x for x in keys if x not in {d['key'] for d in done} | {f['key'] for f in failed}]
        update_status(done, failed, pending)
    print('ALL DONE', len(done), 'fail', len(failed))

if __name__ == '__main__':
    keys = sys.argv[1:]
    if not keys:
        keys = [p['key'] for p in PROJECTS]
    main(keys)
