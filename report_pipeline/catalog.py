# -*- coding: utf-8 -*-
"""Project catalog for rebuild (25 PDFs; 虞乡 done; newfmt skipped)."""
import json, os

ROOT = '/workspace/report_pipeline_20261027'
DATA = ROOT + '/data'
FIG = ROOT + '/fig'
STATUS = ROOT + '/STATUS.md'

def _n5():
    import sys
    sys.path.insert(0, '/workspace/new5_20261027')
    import text5
    from ana import cfg
    jobs = json.load(open('/workspace/new5_20261027/jobs.json'))
    gid2cl = {}
    for cl, gids in jobs.items():
        for g in gids:
            gid2cl[g] = cl
    out = []
    for gid, info in text5.I.items():
        k = 'p' + gid
        out.append(dict(
            batch='new5', key=k, gid=gid, name=info['name'],
            parcels=f'/workspace/new5_20261027/P/{k}_parcels.json',
            rs=f'/workspace/new5_20261027/ana/{k}_rs.json',
            labmap=f'/workspace/new5_20261027/ana/{k}_labmap.json',
            npz_cl=gid2cl[gid],
            npz_dir='/workspace/new5_20261027/rs',
            gdd_key=k, gdd='/workspace/new5_20261027/ana/gdd.json',
            fig_dir='/workspace/new5_20261027/fig',
            fig_prefix=k + '_',
            out_pdf=f'/workspace/new5_20261027/{info["name"]}项目分析报告.pdf',
            epsg=32650,
            spring=gid in cfg.SPR,
            em=cfg.EM.get(gid), end=cfg.END.get(gid),
            uav_key=None,
            farm=True, farm_src='new5',
            text_gid=gid,
        ))
    return out

PROJECTS = [
    # new2
    dict(batch='new2', key='dt', gid='1557', name='临沭分支店头镇新农人',
         parcels='/workspace/new2_20261027/dt_parcels.json',
         rs='/workspace/new2_20261027/ana/dt_rs.json', labmap=None,
         npz_cl='dt', npz_dir='/workspace/new2_20261027/rs',
         gdd_key='dt', gdd='/workspace/new2_20261027/ana/gdd.json',
         fig_dir='/workspace/new2_20261027/fig', fig_prefix='dt_',
         out_pdf='/workspace/new2_20261027/临沭分支店头镇新农人项目分析报告.pdf',
         epsg=32650, spring=False, em='07-08', end='10-15',
         uav_key='dt', farm=True, farm_src='new2', ph_short='店头'),
    dict(batch='new2', key='bq', gid='1556', name='临沭分支板泉镇新农人',
         parcels='/workspace/new2_20261027/bq_parcels.json',
         rs='/workspace/new2_20261027/ana/bq_rs.json', labmap=None,
         npz_cl='bq', npz_dir='/workspace/new2_20261027/rs',
         gdd_key='bq', gdd='/workspace/new2_20261027/ana/gdd.json',
         fig_dir='/workspace/new2_20261027/fig', fig_prefix='bq_',
         out_pdf='/workspace/new2_20261027/临沭分支板泉镇新农人项目分析报告.pdf',
         epsg=32650, spring=False, em='07-08', end='10-15',
         uav_key='bq', farm=True, farm_src='new2', ph_short='板泉'),
    # new3 (skip 297)
    dict(batch='new3', key='p2784', gid='2784', name='永济石桥新农人',
         parcels='/workspace/new3_20261027/p2784_parcels.json',
         rs='/workspace/new3_20261027/ana/p2784_rs.json', labmap=None,
         npz_cl='p2784', npz_dir='/workspace/new3_20261027/rs',
         gdd_key='p2784', gdd='/workspace/new3_20261027/ana/gdd.json',
         fig_dir='/workspace/new3_20261027/fig', fig_prefix='p2784_',
         out_pdf='/workspace/new3_20261027/永济石桥新农人项目分析报告.pdf',
         epsg=32649, spring=False, em='06-20', end='10-13',
         uav_key='p2784', farm=True, farm_src='new3', ph_short='石桥'),
    dict(batch='new3', key='p4116', gid='4116', name='永济董村农场新农人',
         parcels='/workspace/new3_20261027/p4116_parcels.json',
         rs='/workspace/new3_20261027/ana/p4116_rs.json', labmap=None,
         npz_cl='p4116', npz_dir='/workspace/new3_20261027/rs',
         gdd_key='p4116', gdd='/workspace/new3_20261027/ana/gdd.json',
         fig_dir='/workspace/new3_20261027/fig', fig_prefix='p4116_',
         out_pdf='/workspace/new3_20261027/永济董村农场新农人项目分析报告.pdf',
         epsg=32649, spring=False, em='06-20', end='10-13',
         uav_key=None, farm=True, farm_src='new3', ph_short='董村'),
    # new4
    dict(batch='new4', key='p2878', gid='2878', name='沈丘分支自种新农人',
         parcels='/workspace/new4_20261027/p2878_parcels.json',
         rs='/workspace/new4_20261027/ana/p2878_rs.json', labmap=None,
         npz_cl='p2878', npz_dir='/workspace/new4_20261027/rs',
         gdd_key='p2878', gdd='/workspace/new4_20261027/ana/gdd.json',
         fig_dir='/workspace/new4_20261027/fig', fig_prefix='p2878_',
         out_pdf='/workspace/new4_20261027/沈丘分支自种新农人项目分析报告.pdf',
         epsg=32650, spring=False, em='06-15', end='10-15',
         uav_key=None, farm=True, farm_src='new4', ph_short='沈丘'),
    # new6
    dict(batch='new6', key='p109', gid='109', name='东昌府分支堂邑镇童妍新农人',
         parcels='/workspace/new6_20261027/P/p109_parcels.json',
         rs='/workspace/new6_20261027/ana/p109_rs.json',
         labmap='/workspace/new6_20261027/ana/p109_labmap.json',
         npz_cl='c6', npz_dir='/workspace/new6_20261027/rs',
         gdd_key='p109', gdd='/workspace/new6_20261027/ana/gdd.json',
         fig_dir='/workspace/new6_20261027/fig', fig_prefix='p109_',
         out_pdf='/workspace/new6_20261027/东昌府分支堂邑镇童妍新农人项目分析报告.pdf',
         epsg=32650, spring=False, em='06-20', end='10-15',
         uav_key='p109', farm=False, farm_src=None),
    dict(batch='new6', key='p7155', gid='7155', name='东昌府公司合种（新农人保底）郑家温集',
         parcels='/workspace/new6_20261027/P/p7155_parcels.json',
         rs='/workspace/new6_20261027/ana/p7155_rs.json',
         labmap='/workspace/new6_20261027/ana/p7155_labmap.json',
         npz_cl='c6', npz_dir='/workspace/new6_20261027/rs',
         gdd_key='p7155', gdd='/workspace/new6_20261027/ana/gdd.json',
         fig_dir='/workspace/new6_20261027/fig', fig_prefix='p7155_',
         out_pdf='/workspace/new6_20261027/东昌府公司合种（新农人保底）郑家温集项目分析报告.pdf',
         epsg=32650, spring=False, em='06-20', end='10-15',
         uav_key=None, farm=False, farm_src=None),
]

PROJECTS = PROJECTS + _n5()

assert len(PROJECTS) == 25, len(PROJECTS)

def by_key(k):
    for p in PROJECTS:
        if p['key'] == k:
            return p
    raise KeyError(k)
