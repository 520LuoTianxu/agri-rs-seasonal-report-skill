# -*- coding: utf-8 -*-
"""Unified PDF builder matching 虞乡 final standards."""
import sys, re, json, os, subprocess, glob
import numpy as np
sys.path.insert(0, '/workspace/report_pipeline_20261027')
sys.path.insert(0, '/workspace/henan_analysis_20261020/zhenping/build/rep')
sys.path.insert(0, '/workspace/newfmt_20261020')
import common, gloss
from common import b, g, r
from catalog import DATA, by_key
from analyze import load_cube
from harden_helpers import (
    farm_issues, wx_anomalies, has_confirmed_disaster, relative_phrase,
    classic_judge, suggest_text, farm_core_bits, mech_paragraphs, uav_clues,
    last_stage_date,
)
from agent_load import load_agent, render_agent

def f2(v):
    return '—' if v is None or (isinstance(v, float) and not np.isfinite(v)) else f'{v:.2f}'
def f1(v):
    return '—' if v is None else f'{v:.1f}'
def f3(v):
    return '—' if v is None else f'{v:.3f}'

def nm(s):
    return s.replace('农农场', '农场')

class D(common.Doc):
    K = {}; last = None
    BK = '　<a class="back" href="#core">返回核心结论</a>'
    def __init__(s, *a, **k):
        common.Doc.__init__(s, *a, **k); s.K = {}; s.last = None
    def FIGP(s, path, cap, w=100):
        if not os.path.exists(path):
            return f'<p style="color:#999">（缺图：{os.path.basename(path)}）</p>'
        s.fn += 1; s.last = ('图', s.fn, f'fig{s.fn}')
        return f'<div class="fig" id="fig{s.fn}"><img src="file://{path}" style="width:{w}%"><p>图 {s.fn}　{cap}{s.BK}</p></div>'
    def TBL(s, head, rows, cls='t', widths=None, cap=None):
        h = common.Doc.TBL(s, head, rows, cls, widths, cap)
        if cap:
            s.last = ('表', s.tn, f'tbl{s.tn}')
            h = h.replace(f'<p class="tcap">表 {s.tn}　{cap}</p>',
                          f'<p class="tcap" id="tbl{s.tn}">表 {s.tn}　{cap}{s.BK}</p>', 1)
        return h
    def render_pdf(s, h, tag, bd):
        ht = bd + tag + '.html'; open(ht, 'w').write(h)
        subprocess.run(['google-chrome', '--headless=new', '--no-sandbox', '--disable-gpu',
                        '--no-pdf-header-footer', f'--print-to-pdf={s.out}', 'file://' + ht],
                       capture_output=True, timeout=300)
    def build(s, cover, tag, bd):
        s.render_pdf(s.html(s.mk(), cover), tag, bd)
        info = subprocess.run(['pdfinfo', s.out], capture_output=True, text=True).stdout
        N = int(re.search(r'Pages:\s+(\d+)', info).group(1))
        txt = lambda k: subprocess.run(['pdftotext', '-f', str(k), '-l', str(k), '-layout', s.out, '-'],
                                       capture_output=True, text=True).stdout
        pg = {}; cur = 2
        for a, ti in s.secs:
            for k in range(cur, N + 1):
                if re.search(rf'^\s*{re.escape(a)}\s+{re.escape(ti[:5])}', txt(k), re.M):
                    pg[a] = k; cur = k; break
        s.render_pdf(s.html(s.mk(pg), cover), tag, bd)
        json.dump({'secs': s.secs, 'pg': pg, 'out': s.out, 'footer': s.footer},
                  open(bd + tag + '_toc.json', 'w'), ensure_ascii=False)
        res = subprocess.run(['/workspace/venv-report/bin/python',
                              '/workspace/henan_analysis_20261020/zhenping/build/rep/post.py',
                              bd + tag + '_toc.json'], capture_output=True, text=True)
        missing = [a for a, _ in s.secs if a not in pg]
        print('pages', N, 'missing', missing, res.stdout[-200:] if res.stdout else '', res.stderr[-300:] if res.stderr else '')
        return N

def build_one(P):
    K = P['key']; NAME = P['name']
    PL = json.load(open(P['parcels'])); MU = f"{sum(p['mu'] for p in PL):.2f}"; NP = len(PL)
    OUT = P['out_pdf']; BD = os.path.dirname(OUT) + '/build/'; os.makedirs(BD, exist_ok=True)
    FG = f"{P['fig_dir']}/{P['fig_prefix']}"
    R = json.load(open(P['rs'])); G = json.load(open(P['gdd']))[P['gdd_key']]; o = R['2026']
    W = json.load(open(f"{DATA}/{K}_weak.json"))
    SP = P.get('spring') or ('spring' in W['groups'] and 'summer' not in W['groups'])
    # if mixed, treat as mixed in text
    mixed = len(W['groups']) > 1
    dates = [x[5:] if len(x) > 5 else x for x in o['dates']]
    def at(ser, dd):
        # exact or nearest
        if dd in dates: return ser[dates.index(dd)]
        # try full
        full = o['dates']
        for i, d in enumerate(full):
            if d.endswith(dd) or d[5:] == dd: return ser[i]
        return None

    d = D(NAME + '项目分析报告', OUT, NAME + '项目分析报告')
    H1, H2, TBL = d.H1, d.H2, d.TBL
    def KEY(k, it=None):
        d.K[k] = it or d.last; return ''
    def EV(k):
        return f'<a class="ev" href="#@@A:{k}@@">→证据：@@L:{k}@@</a>'
    def LN(x, k):
        return f'<a class="evn" href="#@@A:{k}@@">{x}</a>'

    # gdd bits
    e = G['em']; em = list(e.values())[0]; emd = list(e.keys())[0]
    mon = G['mon']['2026']; cl = G['clim']; GM = G['mon']
    _at = em['y2026']['at']; _nat = em['normal']['at']
    _dp = 100 * (_at - _nat) / _nat if _nat else 0

    # weak totals
    P2 = sum(M['P2'] for M in W['groups'].values())
    TT = sum(M['T'] for M in W['groups'].values())
    top_persist = []
    for gname, M in W['groups'].items():
        for x in M['per']:
            top_persist.append((x['p2'], x, gname))
    top_persist.sort(key=lambda x: -x[0])

    # rank from rs (existing NDVI-based) — also show NDRE peak
    pct = round(o.get('rank_pct') or 0)
    ndre_peak = W.get('proj_peak')
    ring50 = o.get('ring_peak_pctl', {}).get('50')

    issues = farm_issues(P)
    uav_txt = uav_clues(P)
    p2_ratio = (P2 / TT) if TT else 0
    hard_abs = (p2_ratio >= 0.10) or has_confirmed_disaster(issues)

    def judge(p):
        # relative-only wording; absolute caveats added separately when hard_abs
        if hard_abs and p >= 60:
            return relative_phrase(p, b, g, r)
        return classic_judge(p, b, g, r)

    SEA_SHORT = '春玉米' if SP and not mixed else ('夏玉米' if not mixed else '玉米')
    SEA = f'2026 年{SEA_SHORT}季'

    # ========== CORE ==========
    AG = load_agent(K)
    S = H1('一', '核心结论', brk=True) + '<span id="core"></span>'
    peak_txt = f3(ndre_peak) if ndre_peak is not None else f3(o.get('proj_peak'))
    if AG and AG.get('core_growth_html'):
        S += render_agent(AG['core_growth_html'], EV, LN, b, g, r)
        if AG.get('core_farm_html'):
            S += render_agent(AG['core_farm_html'], EV, LN, b, g, r)
        if AG.get('core_key_parcels_html'):
            S += render_agent(AG['core_key_parcels_html'], EV, LN, b, g, r)
        if P.get('uav_key') and not AG.get('skip_auto_uav_in_core'):
            sys.path.insert(0, '/workspace/uav_20261027')
            import uav
            S += uav.core(P['uav_key'], b, EV)
        # 季后报告：仅在 agent 显式提供非空收束段时输出；空字符串则整段不输出，绝不回落自动「建议：」
        _sug = (AG.get('core_suggest_html') or '').strip()
        if _sug:
            S += render_agent(_sug, EV, LN, b, g, r)
    else:
        # fallback auto (should be rare once agent drafts exist)
        S += (f"<p><b>长势结论：</b>2026 年{SEA_SHORT}长势{judge(pct)}。"
              f"玉米拔节以后叶片封垄，NDVI（绿度）拉不开差距，所以拔节后的长势用 NDRE（叶片营养指数）判断。"
              f"全项目拔节后峰值 NDRE {LN(b(peak_txt),'pmap')}；"
              f"按峰值 NDVI 与周边 1–2 公里同季耕地比，约在第 {b(pct)} 百分位 {EV('ring')}。")
        if hard_abs:
            top_abs = []
            for p2, x, gn in top_persist[:3]:
                if p2 < 0.5: break
                lab = ('春播' if gn == 'spring' else '夏播') if mixed else ''
                top_abs.append(f"{lab}{nm(x['name'])} {f1(p2)} 亩")
            where = ('，其中' + '、'.join(top_abs)) if top_abs else ''
            S += (f"相对周边的名次不代表田内无问题：田内持续弱长势共 "
                  f"{LN(r(f1(P2)),'dmgtab')} 亩，占全项目 {b(f1(TT))} 亩的 "
                  f"{r(f1(p2_ratio*100))}%{where} {EV('msfig')}。</p>")
        else:
            S += (f"至少 2 个关键期都偏弱的持续弱长势共 {LN(r(f1(P2)) if P2>=TT*0.05 else b(f1(P2)),'dmgtab')} 亩，"
                  f"占全项目 {b(f1(TT))} 亩的 {b(f1(P2/TT*100) if TT else '0')}% {EV('msfig')}。</p>")
        fbits = farm_core_bits(issues)
        if fbits:
            S += (f"<p><b>农事已记录的风险：</b>" + '；'.join(fbits) +
                  f"。详见第{'六' if P.get('uav_key') else '五'}章农事表，第四章说明其与卫星弱期的关系。</p>")
        if top_persist and top_persist[0][0] > 0.5:
            bits = []
            for p2, x, gn in top_persist[:4]:
                if p2 < 0.5: break
                lab = ('春播' if gn == 'spring' else '夏播') if mixed else ''
                bits.append(f"{lab}{nm(x['name'])}（{b(f1(p2))} 亩）")
            S += f"<p><b>重点地块：</b>按持续弱长势面积排序，较多的是{'、'.join(bits)}。"
            S += f"判断方法见第四章：拔节初用 NDVI，之后用 NDRE；像素比本地块中位数低 25%（NDVI）或 15%（NDRE）以上算偏弱 {EV('dmgtab')}。</p>"
        else:
            S += f"<p><b>重点地块：</b>各关键期田内较均匀，没有大面积持续偏弱的地块 {EV('dmgtab')}。</p>"
        if P.get('uav_key'):
            sys.path.insert(0, '/workspace/uav_20261027')
            import uav
            S += uav.core(P['uav_key'], b, EV)
        # 无 agent 稿时也不再自动生成「建议：」行动段

    CORE_AT = len(S)  # (unused placeholder)

    # ========== 二 遥感 ==========
    S += H1('二', '遥感比较')
    if mixed:
        gs = W['groups']
        S += ('<div class="sum"><b>小结：</b>本项目春播、夏播地块混种，两组分开比较。'
              f"持续弱长势春播组 {b(f1(gs.get('spring',{}).get('P2',0)))} 亩、"
              f"夏播组 {b(f1(gs.get('summer',{}).get('P2',0)))} 亩。"
              f"与周边同季耕地比，峰值约在第 {b(pct)} 百分位，{judge(pct)}。</div>")
    else:
        S += f"<div class=\"sum\"><b>小结：</b>峰值约在周边第 {b(pct)} 百分位，{judge(pct)}；拔节后用 NDRE 看长势。</div>"

    S += H2('2.1', '生育期卫星影像')
    S += d.FIGP(FG + 'stages.png', '各生育期 Sentinel-2 真彩色影像（10 米原始像素，经纬度坐标，黄线为项目地块边界）', 100)
    # stage table from weak ST
    rows = []
    for gname, M in W['groups'].items():
        pref = ('春播·' if gname == 'spring' else '夏播·') if mixed else ''
        for d_, nm_, ix, th in M['ST']:
            rows.append([pref + nm_, b(d_), ix, f'阈值 {int(th*100)}%'])
    S += TBL(['生育期', '代表影像', '指标', '弱长势阈值'], rows, cls='t small',
             cap='关键生育期时间轴（按晴空影像就近选取）'); KEY('stage')

    S += H2('2.2', '近三年长势对比')
    y3path = FG + '3y.png'
    if os.path.exists(y3path):
        S += d.FIGP(y3path, '2024–2026 年同一批地块 NDVI（面积加权）', 88)
    yrows = []
    for y in ('2024', '2025', '2026'):
        if y in R:
            yrows.append([b(y), b(f3(R[y].get('proj_peak'))), b(round(R[y].get('rank_pct') or 0)),
                          b(f3(R[y].get('ring_peak_pctl', {}).get('50')))])
    S += TBL(['年份', '峰值 NDVI', '在周边耕地中的百分位', '周边耕地峰值中位数'], yrows, cls='t small',
             cap='三年峰值长势（NDVI；拔节后长势详见第四章 NDRE）'); KEY('h3y')

    S += H2('2.3', '与周边对比')
    for fn, cap in [('ring.png', '本项目与周边 1–2 km 耕地 NDVI、NDRE 时序'),
                    ('map.png', '周边对照田位置（黄线＝项目地块）')]:
        if os.path.exists(FG + fn):
            S += d.FIGP(FG + fn, cap, 100 if 'ring' in fn else 48)
    S += (f"<p>按峰值 NDVI，本项目约在周边第 {b(pct)} 百分位"
          f"（周边中位 {b(f3(ring50))}）。拔节后峰值 NDRE 为 {b(f3(ndre_peak))}。</p>"); KEY('ring')

    if NP > 1:
        S += H2('2.4', '各地块峰值长势（逐像素）')
        S += d.FIGP(FG + 'pmap_px.png',
                    '各地块逐像素拔节后峰值 NDRE（10 米原始像素，经纬度坐标）：①峰值 NDRE；②比同组地块中位数高或低（%）', 100); KEY('pmap')
        # 统一按偏弱面积（亩）降序，与重点地块/持续弱口径一致
        lows = sorted(W.get('low_rows') or [], key=lambda x: -(x.get('lowmu') or 0))[:8]
        if lows:
            if mixed:
                hd = ['地块', '分组', '面积（亩）', '平均峰值 NDRE', '偏弱面积（亩）']
                rows = []
                for x in lows:
                    gLab = '春播' if x.get('g') == 'spring' else ('夏播' if x.get('g') == 'summer' else '—')
                    rows.append([
                        nm(x['name']), gLab, b(f"{x['mu']:.0f}"),
                        (r if x['mean'] is not None and x['mean'] < x['gmed'] * 0.95 else b)(f3(x['mean'])),
                        (r if x['low'] >= 0.1 else b)(f1(x['lowmu'])) + f"（{x['low']*100:.0f}%）",
                    ])
            else:
                hd = ['地块', '面积（亩）', '平均峰值 NDRE', '偏弱面积（亩）']
                rows = [[
                    nm(x['name']), b(f"{x['mu']:.0f}"),
                    (r if x['mean'] is not None and x['mean'] < x['gmed'] * 0.95 else b)(f3(x['mean'])),
                    (r if x['low'] >= 0.1 else b)(f1(x['lowmu'])) + f"（{x['low']*100:.0f}%）",
                ] for x in lows]
            S += TBL(hd, rows, cls='t small',
                     cap='偏弱面积较大的地块（按偏弱面积排序；偏弱＝峰值 NDRE 比同组中位数低 15% 以上）'); KEY('t4')

    # ========== 三 积温 ==========
    S += H1('三', '积温数据比较')
    GDD_SUM = (g('积温正常') if abs(_dp) <= 8 else (r('积温偏少') if _dp < 0 else b('积温偏多')))
    GDD_SUM += f"（出苗 {emd} 起活动积温 {b(f'{_at:.0f}')}℃，常年 {b(f'{_nat:.0f}')}℃）"
    _anoms = wx_anomalies(mon, cl, top_n=2)
    _wx_tail = ''
    if _anoms:
        _wx_tail = '本季最反常：' + '；'.join(a[1] for a in _anoms) + '，与第四章弱长势起始期对照见 4.2。'
    else:
        _wx_tail = '月尺度降水未出现极端偏离常年的月份。'
    S += f'<div class="sum"><b>小结：</b>{GDD_SUM}。{_wx_tail}</div>'
    if os.path.exists(FG + 'gdd.png'):
        S += d.FIGP(FG + 'gdd.png', '≥10℃ 活动积温累积（ERA5-Land，常年＝1996–2025 平均）', 48)
    GE = P.get('end') or '10-15'
    grow = [[f'出苗 {emd} 起 活动积温', b(f"{em['y2024']['at']:.0f}"), b(f"{em['y2025']['at']:.0f}"),
             b(f"{em['y2026']['at']:.0f}"), b(f"{em['normal']['at']:.0f}")],
            [f'出苗 {emd} 起 有效积温（减 10℃）', b(f"{em['y2024']['ef']:.0f}"), b(f"{em['y2025']['ef']:.0f}"),
             b(f"{em['y2026']['ef']:.0f}"), b(f"{em['normal']['ef']:.0f}")]]
    for m in GM['2026']:
        grow.append([f'{m} 月平均气温（℃）', b(GM['2024'][m]['t']), b(GM['2025'][m]['t']),
                     b(GM['2026'][m]['t']), b(cl[m]['t'])])
    for m in GM['2026']:
        grow.append([f'{m} 月降水（mm）', b(GM['2024'][m]['p']), b(GM['2025'][m]['p']),
                     (r if GM['2026'][m]['p'] < 0.5 * cl[m]['p'] else b)(GM['2026'][m]['p']), b(cl[m]['p'])])
    hs = lambda y: sum(v['hot'] for v in GM[y].values())
    grow.append([f'最高温 ≥35℃ 天数', b(hs('2024')), b(hs('2025')), b(hs('2026')), '—'])
    S += TBL(['指标', '2024', '2025', '2026', '常年'], grow, cls='t small',
             widths=['36%', '16%', '16%', '16%', '16%'], cap=f'积温与气象对比（积温统计到 {GE}）'); KEY('gdd')
    if os.path.exists(FG + 'wx.png'):
        S += d.FIGP(FG + 'wx.png', '2026 年生长季逐日气温与降水', 72); KEY('wx')

    # ========== 四 弱长势 ==========
    S += H1('四', '各地块分期弱长势与受损情况')
    bits = []
    for gname, M in W['groups'].items():
        lab = '春播组' if gname == 'spring' else ('夏播组' if gname == 'summer' else '本组')
        bits.append(f"{lab} {b(f1(M['P2']))} 亩（占本组 {b(f1(M['P2']/M['T']*100 if M['T'] else 0))}%）")
    S += ('<div class="sum"><b>小结：</b>按关键生育期逐像素检查，至少 2 期都偏弱的持续弱长势：'
          + '，'.join(bits) + f"，全项目合计 {b(f1(P2))} 亩（{b(f1(P2/TT*100 if TT else 0))}%）。</div>")
    S += H2('4.1', '各关键生育期每块地的弱长势面积')
    S += ('<p>判断方法：拔节初叶片没有封垄，用 NDVI；之后用 NDRE。'
          f"每期每块地内，像素比本地块中位数低 {b('25%')}（NDVI）或 {b('15%')}（NDRE）以上的算“弱长势”。"
          '至少 2 期都偏弱的像素算“持续弱长势”。有效像素不足一半的地块记为“云”。'
          + ('春播、夏播分组统计。' if mixed else '') + '</p>')
    S += d.FIGP(FG + 'ms.png', '各关键期逐像素长势（比本地块中位数高或低的百分比）及偏弱期数（10 米原始像素，经纬度坐标）', 100); KEY('msfig')

    def cl_cell(c):
        if c.get('st') == 'cloud': return '云'
        if c.get('st') == 'yellow': return '落黄'
        return (r if c.get('frac', 0) >= 0.1 else b)(f1(c.get('mu', 0))) + f"（{c.get('frac',0)*100:.0f}%）"

    for gname, M in W['groups'].items():
        lab = '春播组' if gname == 'spring' else ('夏播组' if mixed else '各地块')
        per = sorted(M['per'], key=lambda x: -x['p2'])
        top = 12 if len(per) > 14 else None
        rows = []
        for x in (per[:top] if top else per):
            rows.append([nm(x['name']), b(f"{x['mu']:.0f}")] + [cl_cell(c) for c in x['cells']] +
                        [(r if x['p2f'] >= 0.1 else b)(f1(x['p2'])) + f"（{x['p2f']*100:.0f}%）",
                         b(f1(x['pall']))])
        if top and len(per) > top:
            rest = per[top:]
            rows.append([f'其余 {len(rest)} 块', b(f"{sum(x['mu'] for x in rest):.0f}")] +
                        ['—'] * len(M['ST']) + [b(f1(sum(x['p2'] for x in rest))),
                                                 b(f1(sum(x['pall'] for x in rest)))])
        T = M['T']
        rows.append(['<b>本组合计</b>', b(f"{T:.0f}")] +
                    [b(f1(t['mu'])) + f"（{t['mu']/T*100 if T else 0:.1f}%）" for t in M['tot']] +
                    [b(f1(M['P2'])) + f"（{M['P2']/T*100 if T else 0:.1f}%）",
                     b(f1(M['PA'])) + f"（{M['PA']/T*100 if T else 0:.1f}%）"])
        hd = ['地块', '面积（亩）'] + [f"{a}<br>{n}·{ix}" for a, n, ix, th in M['ST']] + \
             ['持续弱长势（≥2 期）', '多数期都弱']
        cap = f'{lab}各地块各关键期弱长势面积（亩；括号内为占本地块比例）'
        keyname = 'dmgtab' if gname == list(W['groups'])[0] else 'dmgtab2'
        S += TBL(hd, rows, cls='t small', cap=cap); KEY(keyname)

    # brief note on top
    if top_persist and top_persist[0][0] > 0.5:
        tops = '、'.join(f"{nm(x['name'])}（{f1(p2)} 亩）" for p2, x, gn in top_persist[:5] if p2 > 0.5)
        S += f'<p>持续弱长势较多的地块（按持续弱面积）：{tops}。</p>'

    # 4.2 mechanism — prefer agent-authored
    if AG and AG.get('mech_html'):
        S += render_agent(AG['mech_html'], EV, LN, b, g, r)
    else:
        S += mech_paragraphs(top_persist, W, mon, cl, issues, mixed, nm, b, g, r, f1)

    # ========== 五 无人机（optional） ==========
    chap_farm = '五'
    if P.get('uav_key'):
        sys.path.insert(0, '/workspace/uav_20261027')
        import uav
        # refresh SAT peaks with NDRE parcel peaks if possible
        try:
            for lid, rid, dd, st in uav.P[P['uav_key']]:
                # find parcel
                for i, p in enumerate(PL):
                    if str(p.get('land_id')) == str(lid):
                        if W['parcel_peak'][i] is not None:
                            uav.SAT[lid]['pk'] = W['parcel_peak'][i]
                            uav.SAT[lid]['med'] = W.get('med_peak') or uav.SAT[lid].get('med')
                            uav.SAT[lid]['n'] = NP
                            below = sum(1 for v in W['parcel_peak'] if v is not None and v < W['parcel_peak'][i])
                            uav.SAT[lid]['below'] = below
                        break
        except Exception as e:
            print('uav sat refresh', e)
        S += uav.section(d, P['uav_key'], PL, b, g, r, KEY, N='五', n='5')
        chap_farm = '六'

    # ========== 农事 last ==========
    if P.get('farm'):
        S += H1(chap_farm, '农事记录佐证')
        farm_html = _farm_section(P, d, b, g, r, KEY, PL)
        S += farm_html

    # glossary after TOC only NDVI+NDRE
    GLS = [
        ('NDVI（绿度）', '卫星看庄稼绿不绿、密不密的一个数，越大越茂盛。玉米小的时候用它；长大以后叶子把地全盖住，大家分数都差不多，就分不出好坏了'),
        ('NDRE（叶片营养指数）', '卫星看叶子壮不壮、黄不黄的一个数。玉米长大、地盖满以后，它还能分出哪里长得好、哪里偏弱，所以后期看长势用它'),
    ]
    GLH = ('<div style="margin-top:14px"><h3 style="margin:0 0 4px">名词通俗解释</h3>'
           '<table class="t small"><thead><tr><th style="width:22%">名词</th><th>通俗解释</th></tr></thead><tbody>'
           + ''.join(f'<tr><td><b>{x}</b></td><td>{y}</td></tr>' for x, y in GLS) + '</tbody></table></div>')
    _h = d.html
    d.html = lambda toc, cover: _h(toc, cover).replace('</div><h1 id="s一"', '</div>' + GLH + '<h1 id="s一"', 1)

    def RES(S):
        for k, (t, n, anc) in d.K.items():
            S = S.replace(f'@@A:{k}@@', anc).replace(f'@@L:{k}@@', f'{t} {n}')
        # drop unresolved quietly
        S = re.sub(r'@@A:[^@]+@@', 'core', S)
        S = re.sub(r'@@L:[^@]+@@', '见正文', S)
        return S

    d.body = gloss.clean(RES(S))
    # strip forbidden
    for bad in ('待核实', '产量', '收益', '盐碱地', '亏损'):
        if bad in d.body and bad not in ('盐碱',):
            pass  # don't auto-delete mid-sentence aggressively; verify later
    common.CSS += ('h1.tocT{page-break-before:auto!important}.fig p{font-weight:600;color:#0d3b66}'
                   'ol li{margin:2px 0}a.ev{color:#1565c0;text-decoration:underline;font-size:8.3pt;'
                   'font-weight:400;white-space:nowrap}a.evn{color:#1565c0;text-decoration:underline}'
                   'a.back{color:#1565c0;text-decoration:underline;font-size:7.3pt;font-weight:400}.g2 img{width:86%}')
    cover = (f'<div style="text-align:center;margin:30px 0 20px">'
             f'<div style="font-size:24pt;font-weight:700;color:#0d3b66">{NAME}项目分析报告</div>'
             f'<div style="font-size:12pt;color:#555;margin-top:6px">{SEA} · {MU} 亩 · {NP} 个地块</div>'
             f'<div style="font-size:10pt;color:#777;margin-top:4px">报告日期 <span class="b">2026-10-28</span>'
             f'　颜色：<span class="g">绿＝正面</span>　<span class="r">红＝风险</span>　'
             f'<span class="b">蓝＝日期与数字</span></div></div>')
    pages = d.build(cover, K, BD)
    return pages


def _farm_section(P, d, b, g, r, KEY, PL):
    """Attach farm photos + table from existing sources; empty summary if missing."""
    H2, TBL = d.H2, d.TBL
    S = ''
    src = P.get('farm_src')
    # new5
    if src == 'new5':
        sys.path.insert(0, '/workspace/new5_20261027')
        import text5
        INFO = text5.I[P['text_gid']]
        S += f"<div class=\"sum\"><b>小结：</b>{INFO.get('ph_sum') or '见下方照片与记录。'}</div>"
        W = '/workspace/new5_20261027/'
        PH = W + 'ph/sel/' + INFO['name']
        try:
            _SEL = json.load(open(W + 'ph/sel2.json'))[P['text_gid']]
            _cap = {'3231': 2, '2879': 2}.get(P['text_gid'], 4)
            _SEL = _SEL[:1] + _SEL[-1:] if _cap == 2 and len(_SEL) > 2 else _SEL[:4]
            from PIL import Image as _I, ImageOps as _IO
            os.makedirs(W + 'ph/sel', exist_ok=True)
            _cells = []
            for _k, _p in enumerate(_SEL):
                _f = f"{PH}照片{'一二三四'[_k]}.png"
                _im = _IO.exif_transpose(_I.open(W + _p['f'])).convert('RGB')
                _im.thumbnail((900, 900)); _im.save(_f)
                _cells.append(f'<td style="width:50%;text-align:center;vertical-align:top;border:none">'
                              f'<img src="file://{_f}" style="max-width:96%;max-height:62mm">'
                              f'<div style="font-size:8.5pt;color:#0d3b66">{b(_p["date"])}　{_p["task"]}</div></td>')
            d.fn += 1; d.last = ('图', d.fn, f'fig{d.fn}')
            _rows = ''.join('<tr>' + ''.join(_cells[i:i+2]) + '</tr>' for i in range(0, len(_cells), 2))
            S += f'<div class="fig" id="fig{d.fn}"><table style="width:100%;border:none">{_rows}</table>'
            S += f'<p>图 {d.fn}　农事记录现场照片{d.BK}</p></div>'; KEY('ph1')
        except Exception as e:
            print('farm photos new5', e)
        def F(t):
            # limited eval context
            return t  # keep placeholders simple — already mostly plain in phtab last col via eval in old build
        # Evaluate phtab with minimal context
        rows = []
        for a, bb, c, dd in INFO['phtab']:
            try:
                dd2 = eval('f"""' + dd + '"""', {'b': b, 'g': g, 'r': r})
            except Exception:
                dd2 = dd
            rows.append([b(a), bb, c, dd2])
        S += TBL(['日期', '环节', '田间状况', '说明的问题'], rows,
                 widths=['15%', '14%', '45%', '26%'], cls='t small', cap='农事照片与记录佐证汇总'); KEY('phtab')
        return S

    # new2 / new3 / new4 — use existing selected PNGs
    short = P.get('ph_short') or ''
    base = {'new2': '/workspace/new2_20261027/ph/sel/',
            'new3': '/workspace/new3_20261027/ph/sel/',
            'new4': '/workspace/new4_20261027/ph/sel/'}.get(src)
    S += '<div class="sum"><b>小结：</b>见下方农事照片与记录。</div>'
    if base and short:
        pics = sorted(glob.glob(base + short + '照片*.png'))[:6]
        if pics:
            # show 2x3 or 2x2
            cells = []
            for i, fp in enumerate(pics):
                cells.append(f'<td style="width:50%;text-align:center;vertical-align:top;border:none">'
                             f'<img src="file://{fp}" style="max-width:96%;max-height:62mm"></td>')
            d.fn += 1; d.last = ('图', d.fn, f'fig{d.fn}')
            rows = ''.join('<tr>' + ''.join(cells[i:i+2]) + '</tr>' for i in range(0, len(cells), 2))
            S += f'<div class="fig" id="fig{d.fn}"><table style="width:100%;border:none">{rows}</table>'
            S += f'<p>图 {d.fn}　农事记录现场照片{d.BK}</p></div>'; KEY('ph1')
    # try reuse text from text.json if new3
    if src == 'new3':
        try:
            T = json.load(open('/workspace/new3_20261027/text.json'))[P['key']]
            S = S.replace('见下方农事照片与记录。', T.get('ph_sum', '见下方农事照片与记录。'))
            if T.get('phtab'):
                def F(t):
                    try: return eval('f"""' + t + '"""', {'b': b, 'g': g, 'r': r})
                    except Exception: return t
                rows = [[b(a), bb, c, F(dd)] for a, bb, c, dd in T['phtab']]
                S += TBL(['日期', '环节', '田间状况', '说明的问题'], rows,
                         widths=['15%', '14%', '45%', '26%'], cls='t small', cap='农事照片与记录佐证汇总'); KEY('phtab')
        except Exception as e:
            print('new3 farm text', e)
    if src == 'new2':
        # hardcode minimal from previous build patterns — keep photos only if no table easily available
        pass
    if src == 'new4':
        try:
            T = json.load(open('/workspace/new4_20261027/text.json'))
            key = P['key'] if P['key'] in T else list(T)[0]
            info = T[key]
            if info.get('ph_sum'):
                S = S.replace('见下方农事照片与记录。', info['ph_sum'])
            if info.get('phtab'):
                rows = [[b(a), bb, c, dd] for a, bb, c, dd in info['phtab']]
                S += TBL(['日期', '环节', '田间状况', '说明的问题'], rows,
                         widths=['15%', '14%', '45%', '26%'], cls='t small', cap='农事照片与记录佐证汇总'); KEY('phtab')
        except Exception as e:
            print('new4 farm', e)
    return S


if __name__ == '__main__':
    for k in sys.argv[1:]:
        P = by_key(k)
        print('BUILD', k)
        n = build_one(P)
        print('DONE', k, n)
