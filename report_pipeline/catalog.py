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
            text_gid=gid, hazard=False,
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
         uav_key='dt', farm=True, farm_src='new2', ph_short='店头',
         dedup=True, lands_json='/workspace/new2_20261027/lands_1557.json', hazard=False),
    dict(batch='new2', key='bq', gid='1556', name='临沭分支板泉镇新农人',
         parcels='/workspace/new2_20261027/bq_parcels.json',
         rs='/workspace/new2_20261027/ana/bq_rs.json', labmap=None,
         npz_cl='bq', npz_dir='/workspace/new2_20261027/rs',
         gdd_key='bq', gdd='/workspace/new2_20261027/ana/gdd.json',
         fig_dir='/workspace/new2_20261027/fig', fig_prefix='bq_',
         out_pdf='/workspace/new2_20261027/临沭分支板泉镇新农人项目分析报告.pdf',
         epsg=32650, spring=False, force_season='summer', em='07-08', end='10-15',
         uav_key='bq', farm=True, farm_src='new2', ph_short='板泉', hazard=False),
    # new3 (skip 297)
    dict(batch='new3', key='p2784', gid='2784', name='永济石桥新农人',
         parcels='/workspace/new3_20261027/p2784_parcels.json',
         rs='/workspace/new3_20261027/ana/p2784_rs.json', labmap=None,
         npz_cl='p2784', npz_dir='/workspace/new3_20261027/rs',
         gdd_key='p2784', gdd='/workspace/new3_20261027/ana/gdd.json',
         fig_dir='/workspace/new3_20261027/fig', fig_prefix='p2784_',
         out_pdf='/workspace/new3_20261027/永济石桥新农人项目分析报告.pdf',
         epsg=32649, spring=False, em='06-20', end='10-13',
         uav_key='p2784', farm=True, farm_src='new3', ph_short='石桥', hazard=False),
    dict(batch='new3', key='p4116', gid='4116', name='永济董村农场新农人',
         parcels='/workspace/new3_20261027/p4116_parcels.json',
         rs='/workspace/new3_20261027/ana/p4116_rs.json', labmap=None,
         npz_cl='p4116', npz_dir='/workspace/new3_20261027/rs',
         gdd_key='p4116', gdd='/workspace/new3_20261027/ana/gdd.json',
         fig_dir='/workspace/new3_20261027/fig', fig_prefix='p4116_',
         out_pdf='/workspace/new3_20261027/永济董村农场新农人项目分析报告.pdf',
         epsg=32649, spring=False, em='06-20', end='10-13',
         uav_key=None, farm=True, farm_src='new3', ph_short='董村', hazard=False),
    dict(batch='new3', key='p297', gid='297', name='永济虞乡农场新农人',
         parcels='/workspace/new3_20261027/p297_parcels.json',
         rs='/workspace/new3_20261027/ana/p297_rs.json', labmap=None,
         npz_cl='p297', npz_dir='/workspace/new3_20261027/rs',
         gdd_key='p297', gdd='/workspace/new3_20261027/ana/gdd.json',
         fig_dir='/workspace/new3_20261027/fig', fig_prefix='p297_',
         out_pdf='/workspace/new3_20261027/永济虞乡农场新农人项目分析报告.pdf',
         epsg=32649, spring=True, em='05-20', end='09-15',
         uav_key='p297', farm=True, farm_src='new3', ph_short='虞乡', hazard=False),
    # new4
    dict(batch='new4', key='p2878', gid='2878', name='沈丘分支自种新农人',
         parcels='/workspace/new4_20261027/p2878_parcels.json',
         rs='/workspace/new4_20261027/ana/p2878_rs.json', labmap=None,
         npz_cl='p2878', npz_dir='/workspace/new4_20261027/rs',
         gdd_key='p2878', gdd='/workspace/new4_20261027/ana/gdd.json',
         fig_dir='/workspace/new4_20261027/fig', fig_prefix='p2878_',
         out_pdf='/workspace/new4_20261027/沈丘分支自种新农人项目分析报告.pdf',
         epsg=32650, spring=False, em='06-15', end='10-15',
         uav_key=None, farm=True, farm_src='new4', ph_short='沈丘',
         dedup=True, lands_json='/workspace/analysis/group2878/lands_2878.json',
         pixel_m=20,
         hazard=True,
         flood_csv='/workspace/project2878_20261019/flood/flood_indices_per_parcel.csv',
         rain_glob='/workspace/project2878_20261019/flood/rain_*.json'),
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
         uav_key='p109', farm=False, farm_src=None, hazard=False),
    dict(batch='new6', key='p7155', gid='7155', name='东昌府公司合种（新农人保底）郑家温集',
         parcels='/workspace/new6_20261027/P/p7155_parcels.json',
         rs='/workspace/new6_20261027/ana/p7155_rs.json',
         labmap='/workspace/new6_20261027/ana/p7155_labmap.json',
         npz_cl='c6', npz_dir='/workspace/new6_20261027/rs',
         gdd_key='p7155', gdd='/workspace/new6_20261027/ana/gdd.json',
         fig_dir='/workspace/new6_20261027/fig', fig_prefix='p7155_',
         out_pdf='/workspace/new6_20261027/东昌府公司合种（新农人保底）郑家温集项目分析报告.pdf',
         epsg=32650, spring=False, em='06-20', end='10-15',
         uav_key=None, farm=False, farm_src=None, hazard=False),
    # Liaoning Jianping (group 119) — spring corn
    dict(batch='ln119', key='p119', gid='119', name='辽宁区域建平分支自种地',
         parcels='/workspace/ln119_20261028/p119_parcels.json',
         rs='/workspace/ln119_20261028/ana/p119_rs.json', labmap=None,
         npz_cl='p119', npz_dir='/workspace/ln119_20261028/rs',
         gdd_key='p119', gdd='/workspace/ln119_20261028/ana/gdd.json',
         fig_dir='/workspace/ln119_20261028/fig', fig_prefix='p119_',
         out_pdf='/workspace/ln119_20261028/辽宁区域建平分支自种地项目分析报告.pdf',
         epsg=32650, spring=True, force_season='spring', em='05-10', end='10-14',
         uav_key=None, farm=False, farm_src=None, ph_short='建平',
         pixel_m=10, hazard=False),
]

PROJECTS = PROJECTS + _n5()


# Season overrides: mid-June NDVI≥0.35 mislabels residual green (Banquan: leftover
# potatoes not yet harvested; elsewhere wheat/weeds) as spring. Prefer farm records
# + regional phenology over greenness alone.
_FORCE_SEASON = {
    'p119': 'spring',  # 辽宁建平：农事春播 4-26；辽西春玉米
    # Bashang spring corn; mid-June bare patches were mislabeled summer
    'p434': 'spring',  # 张北三号乡：4-28~5-21 分批春播
    'p436': 'spring',  # 张北大囫囵：6-16 已五叶，春播区
    'p539': 'spring',  # 怀安瓦窑湾：5-01 播种 / 5-16 出苗
    'p544': 'spring',  # 怀安张北疙瘩村：5-13 播种
    # North China Plain summer corn; mid-June residual green → false spring
    'p451': 'summer',  # 涞水孔村：农事 6-23 播种偏晚
    'p828': 'summer',  # 涞水南山南：同片平原夏玉米，EM≈06-12
    'p970': 'summer',  # 涞水西明义：农事 6-05 播种
    'p633': 'summer',  # 定兴北七：农事 6-23 播种；冀中南夏玉米
    # bq already has force_season='summer' on its dict
}
for _p in PROJECTS:
    if _p['key'] in _FORCE_SEASON:
        _p['force_season'] = _FORCE_SEASON[_p['key']]

assert len(PROJECTS) == 27, len(PROJECTS)

def by_key(k):
    for p in PROJECTS:
        if p['key'] == k:
            return p
    raise KeyError(k)
