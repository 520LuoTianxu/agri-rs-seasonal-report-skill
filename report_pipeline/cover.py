# -*- coding: utf-8 -*-
"""乡合农服 项目季报封面 HTML（定稿规格）。"""
import os

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
LOGO = os.path.join(ASSETS, 'xianghe_logo_full.png')
WATERMARK = os.path.join(ASSETS, 'xianghe_watermark_xiang.png')

PRIMARY = '#1F4D38'
GREEN_BAR = '#2E7D4F'
BLUE_BAR = '#2F6FED'
GOLD_BAR = '#D4A017'

# key → 省；未命中再按名称关键字
PROVINCE_BY_KEY = {
    'p2878': '河南',
    'dt': '山东', 'bq': '山东', 'p109': '山东', 'p7155': '山东',
    'p2784': '山西', 'p4116': '山西', 'p297': '山西',
}

NAME_PROVINCE = (
    ('沈丘', '河南'), ('邓州', '河南'), ('镇平', '河南'),
    ('临沭', '山东'), ('东昌府', '山东'), ('聊城', '山东'),
    ('永济', '山西'), ('屯留', '山西'), ('运城', '山西'),
    ('邯山', '河北'), ('宁晋', '河北'), ('临城', '河北'),
    ('海兴', '河北'), ('张北', '河北'), ('涞水', '河北'),
    ('怀安', '河北'), ('定兴', '河北'), ('邯郸', '河北'),
)


def province_of(P):
    if P.get('province'):
        return P['province']
    k = P.get('key')
    if k in PROVINCE_BY_KEY:
        return PROVINCE_BY_KEY[k]
    name = P.get('name') or ''
    for tip, prov in NAME_PROVINCE:
        if tip in name:
            return prov
    # new5 河北兜底
    if P.get('batch') == 'new5':
        return '河北'
    return '—'


def make_cover_html(meta):
    """meta: name, province, season, mu, n_parcels, report_date(可选);
    可选 title / report_type / scale / show_proj(默认True)。"""
    name = meta['name']
    # 项目名展示：已带「项目」则不重复
    proj = name if name.endswith('项目') else (name + '项目')
    province = meta['province']
    season = meta['season']
    mu = meta['mu']
    np_ = meta['n_parcels']
    date = meta.get('report_date') or '2026年10月28日'
    title = meta.get('title') or '地块遥感长势分析报告'
    report_type = meta.get('report_type') or '全季度长势分析'
    scale = meta.get('scale') or f'{mu} 亩 · {np_} 个地块'
    show_proj = meta.get('show_proj', True)
    logo = 'file://' + LOGO
    wm = 'file://' + WATERMARK
    rows = [
        ('所属省份', province),
        ('分析季节', season),
        ('项目规模', scale),
        ('报告类型', report_type),
        ('报告日期', date),
    ]
    trs = ''.join(
        f'<tr><td class="k">{k}</td><td class="v">{v}</td></tr>' for k, v in rows
    )
    return f'''<div class="rs-cover">
  <div class="rs-cover-inner">
    <div class="rs-brand">
      <img class="rs-logo" src="{logo}" alt="乡合">
      <div class="rs-brand-txt">
        <div class="rs-brand-name">乡合农服</div>
        <div class="rs-brand-sub">农业遥感评估</div>
      </div>
    </div>
    <div class="rs-title-block">
      <div class="rs-title">{title}</div>
      <div class="rs-title-line"></div>
      {f'<div class="rs-proj">{proj}</div>' if show_proj else ''}
    </div>
    <table class="rs-meta">{trs}</table>
    <img class="rs-wm" src="{wm}" alt="">
    <div class="rs-foot">
      <div class="rs-foot-brand">乡合农服</div>
      <div class="rs-foot-slogan">用遥感数据，服务现代农业</div>
      <div class="rs-foot-note">提示：遥感数据不一定准确，分析结论仅供参考，不作为最终准入或交易依据。</div>
    </div>
  </div>
  <div class="rs-bar"><span class="g"></span><span class="b"></span><span class="y"></span></div>
</div>'''


COVER_CSS = f'''
.rs-cover{{
  page-break-after:always; break-after:page;
  position:relative;
  /* 吃满一页可视高度（A4 297mm − 上下边距约 32mm） */
  min-height:252mm;
  margin:0 -2mm;
  box-sizing:border-box;
  color:{PRIMARY};
  overflow:hidden;
}}
.rs-cover-inner{{position:relative; min-height:244mm; padding:2mm 2mm 0; box-sizing:border-box;}}
.rs-brand{{display:flex; align-items:center; gap:10px; margin-bottom:28mm;}}
.rs-logo{{width:42px; height:42px; object-fit:contain; border-radius:6px;}}
.rs-brand-name{{font-size:16pt; font-weight:700; color:{PRIMARY}; line-height:1.2;}}
.rs-brand-sub{{font-size:9pt; color:#8a8a8a; margin-top:2px;}}
.rs-title-block{{margin:8mm 0 10mm;}}
.rs-title{{font-size:26pt; font-weight:700; color:{PRIMARY}; letter-spacing:1px; line-height:1.35;}}
.rs-title-line{{width:72px; height:2.5px; background:{PRIMARY}; margin:10px 0 14px;}}
.rs-proj{{font-size:14pt; font-weight:700; color:{PRIMARY}; margin-top:2px;}}
table.rs-meta{{border-collapse:collapse; width:78%; margin-top:6mm; font-size:11pt;}}
table.rs-meta td{{padding:9px 4px; border-bottom:1px solid #d8d8d8; vertical-align:middle;}}
table.rs-meta td.k{{width:28%; color:#666; font-weight:500;}}
table.rs-meta td.v{{color:#222; font-weight:600;}}
.rs-wm{{
  position:absolute; right:-8mm; bottom:28mm;
  width:118mm; height:auto; opacity:1;
  pointer-events:none; z-index:0;
}}
.rs-foot{{position:absolute; left:2mm; right:2mm; bottom:10mm; z-index:1;}}
.rs-foot-brand{{font-size:12pt; font-weight:600; color:#6b6b6b;}}
.rs-foot-slogan{{font-size:9pt; color:#8a8a8a; margin-top:3px;}}
.rs-foot-note{{font-size:7.2pt; color:#b0b0b0; margin-top:6px; line-height:1.45;}}
.rs-bar{{display:flex; height:5px; width:100%; margin-top:4mm;}}
.rs-bar span{{display:block; height:100%;}}
.rs-bar .g{{flex:4; background:{GREEN_BAR};}}
.rs-bar .b{{flex:3; background:{BLUE_BAR};}}
.rs-bar .y{{flex:3; background:{GOLD_BAR};}}
'''
