# -*- coding: utf-8 -*-
"""Helpers for report hardening (5 fixes): farm issues, wx anomalies, onset, tone, suggestions."""
import re, json, os, glob

TOPIC_PATTERNS = [
    ('早霜', re.compile(r'早霜|霜冻|受冻')),
    ('积水', re.compile(r'积水|渍涝|内涝')),
    ('倒伏', re.compile(r'倒伏')),
    ('出苗不齐', re.compile(r'出苗不齐|出苗率|缺苗|齐苗率')),
    ('病害', re.compile(r'青枯|大斑病|病害|枯死|发病')),
    ('秃尖', re.compile(r'秃尖')),
    ('虫害', re.compile(r'蚜虫|虫害|啃食')),
    ('播种偏晚', re.compile(r'播种偏晚|播种晚')),
    ('水肥', re.compile(r'水肥|滴灌带.*晚|追肥')),
]

RISK_MARK = re.compile(r"\{r\(|'r'|\"r\"|风险|偏弱|不齐|早霜|积水|倒伏|秃尖|病害|发病|受冻|霜冻|缺苗")


def _strip_fmt(s):
    if not isinstance(s, str):
        return str(s)
    s = re.sub(r"\{[rgb]\('([^']*)'\)\}", r'\1', s)
    s = re.sub(r'\{[rgb]\("([^"]*)"\)\}', r'\1', s)
    return s


def _day(mmdd):
    a, b = str(mmdd).replace('/', '-').split('-')[:2]
    return int(a) * 31 + int(b)


def classify_topic(text):
    text = _strip_fmt(text)
    for name, pat in TOPIC_PATTERNS:
        if pat.search(text):
            return name
    return None


def load_farm_rows(P):
    """Return list of (date, stage, status, issue_text) from farm sources."""
    rows = []
    src = P.get('farm_src')
    if not P.get('farm'):
        return rows
    try:
        if src == 'new5':
            import sys
            sys.path.insert(0, '/workspace/new5_20261027')
            import text5
            INFO = text5.I[P['text_gid']]
            for a, bb, c, dd in INFO.get('phtab') or []:
                rows.append((a, bb, c, _strip_fmt(dd)))
        elif src == 'new3':
            T = json.load(open('/workspace/new3_20261027/text.json'))[P['key']]
            for a, bb, c, dd in T.get('phtab') or []:
                rows.append((a, bb, c, _strip_fmt(dd)))
        elif src == 'new4':
            T = json.load(open('/workspace/new4_20261027/text.json'))
            key = P['key'] if P['key'] in T else list(T)[0]
            for a, bb, c, dd in T[key].get('phtab') or []:
                rows.append((a, bb, c, _strip_fmt(dd)))
    except Exception as e:
        print('load_farm_rows', P.get('key'), e)
    return rows


def farm_issues(P):
    """Risk-tagged farm issues: [{date, stage, status, issue, topic}]."""
    out = []
    for a, bb, c, dd in load_farm_rows(P):
        blob = f'{bb} {c} {dd}'
        topic = classify_topic(blob)
        risk = bool(topic) or bool(RISK_MARK.search(blob))
        if risk and topic:
            out.append(dict(date=a, stage=bb, status=c, issue=dd, topic=topic))
        elif risk:
            out.append(dict(date=a, stage=bb, status=c, issue=dd, topic=topic or '其他'))
    return out


def wx_anomalies(mon, clim, top_n=3):
    """Most anomalous precip months vs climate; return list of (score, sentence, month)."""
    items = []
    for m, v in mon.items():
        if m not in clim:
            continue
        cp = clim[m].get('p') or 0
        p = v.get('p') or 0
        if not cp:
            continue
        ratio = p / cp
        if ratio <= 0.55:
            score = (0.55 - ratio) + 0.5  # dry heavier
            items.append((score, f'{m} 月降水 {p} mm，约为常年 {cp} mm 的 {ratio*100:.0f}%（明显偏少）', m, 'dry', p, cp))
        elif ratio >= 1.5:
            score = ratio - 1.5
            items.append((score, f'{m} 月降水 {p} mm，约为常年 {cp} mm 的 {ratio*100:.0f}%（明显偏多）', m, 'wet', p, cp))
    items.sort(key=lambda x: -x[0])
    return items[:top_n]


def onset_info(x, ST, frac_th=0.10):
    """First stage where weak frac >= th; list of weak stages."""
    weak = []
    onset = None
    for i, c in enumerate(x.get('cells') or []):
        if c.get('st') != 'ok':
            continue
        frac = c.get('frac') or 0
        if frac >= frac_th:
            weak.append((i, ST[i][0], ST[i][1], ST[i][2], frac))
            if onset is None:
                onset = (i, ST[i][0], ST[i][1], ST[i][2], frac)
    # softer fallback
    if onset is None:
        for i, c in enumerate(x.get('cells') or []):
            if c.get('st') == 'ok' and (c.get('frac') or 0) >= 0.08:
                onset = (i, ST[i][0], ST[i][1], ST[i][2], c['frac'])
                break
    last_img = ST[-1][0] if ST else None
    return onset, weak, last_img


def last_stage_date(W):
    last = None
    for M in W['groups'].values():
        if M.get('ST'):
            d = M['ST'][-1][0]
            if last is None or _day(d) > _day(last):
                last = d
    return last


def uav_clues(P):
    """Short UAV clue string if any."""
    uk = P.get('uav_key')
    if not uk:
        return ''
    try:
        import sys
        sys.path.insert(0, '/workspace/uav_20261027')
        import uav
        return uav.CORE.get(uk, '')
    except Exception:
        return ''


def has_confirmed_disaster(issues):
    keys = {'早霜', '积水', '倒伏', '出苗不齐', '病害', '秃尖'}
    return any(i['topic'] in keys for i in issues)


def relative_phrase(pct, b, g, r):
    if pct >= 80:
        return g('相对周边偏高')
    if pct >= 60:
        return g('相对周边略高')
    if pct >= 40:
        return b('与周边基本持平')
    return r('相对周边偏低')


def classic_judge(pct, b, g, r):
    if pct >= 80:
        return g('明显好于周边')
    if pct >= 60:
        return g('略好于周边')
    if pct >= 40:
        return b('与周边基本持平')
    return r('略弱于周边')


def suggest_text(sug_names, issues, uav_txt, P2, TT):
    """Non-template suggestion based on farm/UAV evidence."""
    topics = {i['topic'] for i in issues}
    parts = []
    if sug_names:
        parts.append('下次巡田优先看 ' + '、'.join(sug_names))
    # converge hypotheses
    bits = []
    if '积水' in topics:
        bits.append('对照积水记录查排水与低洼带')
    if '出苗不齐' in topics:
        bits.append('核对播栽密度与补种情况')
    if '倒伏' in topics:
        bits.append('现场复核倒伏范围（农事已记录倒伏，不再猜测是否倒伏）')
    if '早霜' in topics:
        bits.append('早霜多发生在灌浆末景之后，弱长势表覆盖不到霜害，需结合收获籽粒与田间复核')
    if '病害' in topics:
        bits.append('对照病害记录核查发病地块')
    if '秃尖' in topics:
        bits.append('结合秃尖与灌浆情况评估穗部损失')
    # UAV keywords
    if uav_txt:
        if '缺苗' in uav_txt or '露土' in uav_txt:
            bits.append('无人机已见露土/缺苗迹象，优先核对出苗与补种')
        if '缺氮' in uav_txt:
            bits.append('无人机疑似缺氮处可抽查叶色与追肥')
        if '长势弱' in uav_txt and not bits:
            bits.append('对照无人机成片弱区核实原因')
    if bits:
        tip = '；'.join(bits[:3])
        if parts:
            return f"<b>建议：</b>{parts[0]}；{tip}。"
        return f"<b>建议：</b>{tip}。"
    if sug_names:
        # no farm/uav clue — cautious, not the dead 三选一 alone as only analysis
        return (f"<b>建议：</b>{parts[0]}。"
                f"现有农事与无人机线索不足以区分缺苗、渍涝或倒伏，卫星也无法单独判定原因，需现场确认。")
    return "<b>建议：</b>继续按现有管理跟进，重点留意局部偏弱的边角地块。"


def farm_core_bits(issues, max_n=3):
    """Short phrases for core conclusion linking farm topics."""
    seen = set()
    bits = []
    for i in issues:
        t = i['topic']
        if t in seen or t == '其他':
            continue
        seen.add(t)
        bits.append(f"{i['date']} {t}（{i['status'][:28]}）")
        if len(bits) >= max_n:
            break
    return bits


def wx_near_onset(onset_date, anoms, window=45):
    """Pick anomalies whose month is near onset (rough)."""
    if not onset_date or not anoms:
        return anoms[:1] if anoms else []
    try:
        om = int(str(onset_date).split('-')[0])
    except Exception:
        return anoms[:1]
    near = [a for a in anoms if abs(int(a[2]) - om) <= 1]
    return near[:2] if near else anoms[:1]


def mech_paragraphs(top_persist, W, mon, clim, issues, mixed, nm, b, g, r, f1):
    """Build 4.2 mechanism HTML for top 1-2 persistent-weak parcels."""
    if not top_persist or top_persist[0][0] < 0.5:
        return ''
    anoms = wx_anomalies(mon, clim, top_n=4)
    last_all = last_stage_date(W)
    # frost / late disasters after last image
    late_notes = []
    for i in issues:
        if i['topic'] in ('早霜', '倒伏', '秃尖'):
            # extract mm-dd from date field like 9-12 or 09-12 or 10-23
            m = re.search(r'(\d{1,2})[-/](\d{1,2})', str(i['date']))
            if m and last_all:
                dd = f"{int(m.group(1)):02d}-{int(m.group(2)):02d}"
                if _day(dd) > _day(last_all):
                    late_notes.append((i['topic'], dd, i['status'], i.get('stage', '')))

    blocks = []
    blocks.append('<h2>4.2 重点地块偏弱起始与边界说明</h2>')
    blocks.append(
        '<p>对持续弱长势最多的地块，按关键期逐期检查：偏弱从哪一期开始、之后是否延续；'
        '并与同期降水异常、农事记录对照。无充分证据时写明“卫星无法区分原因”，不空猜。</p>'
    )
    used = 0
    for p2, x, gn in top_persist:
        if p2 < 0.5 or used >= 2:
            break
        M = W['groups'][gn]
        ST = M['ST']
        onset, weak, last_img = onset_info(x, ST)
        lab = ('春播·' if gn == 'spring' else '夏播·') if mixed else ''
        name = nm(x['name'])
        lines = [f"<p><b>{lab}{name}</b>（持续弱 {b(f1(p2))} 亩，占本地块 {b(f1(x['p2f']*100))}%）："]
        if onset:
            oi, od, onm, oix, ofrac = onset
            lines.append(
                f"偏弱从代表影像 {b(od)}（{onm}，{oix}）起较明显"
                f"（该期弱长势约占本地块 {b(f'{ofrac*100:.0f}')}%）"
            )
            if len(weak) >= 2:
                cont = '、'.join(f"{d}（{n}）" for _, d, n, _, _ in weak[1:4])
                lines.append(f"；此后在 {cont} 等期仍可见延续")
            lines.append('。')
        else:
            lines.append('各关键期弱斑分散，难以定出单一起始期。')

        # weather link
        near = wx_near_onset(onset[1] if onset else None, anoms)
        if near:
            lines.append('同期气象：' + '；'.join(a[1] for a in near) + '。')
            # cautious coupling
            if near[0][3] == 'dry':
                lines.append('降水偏少与弱长势在时间上接近，但卫星无法单独判定是干旱胁迫还是播栽/管理差异。')
            elif near[0][3] == 'wet':
                lines.append('降水偏多与弱长势在时间上接近，需结合低洼积水与排水情况现场核实。')
        else:
            lines.append('现有月尺度降水未显示与该弱期一一对应的极端异常。')

        # farm match by parcel name digits / topic
        matched = []
        for i in issues:
            # if status/issue mentions parcel-ish number from name
            nums = re.findall(r'\d+', name)
            hit = False
            for n in nums:
                if n and (n in i['status'] or n in i['issue'] or (n + '号') in i['status']):
                    hit = True
            if i['topic'] in ('积水', '出苗不齐', '病害') and (hit or used == 0):
                matched.append(i)
        # also general early-season issues for early onset
        if onset and onset[0] <= 1:
            for i in issues:
                if i['topic'] == '出苗不齐' and i not in matched:
                    matched.append(i)
        if matched:
            m0 = matched[0]
            lines.append(
                f"农事方面：{b(m0['date'])} 记录“{m0['status'][:40]}”（{m0['topic']}），"
                f"与上述弱期{'时间吻合，可对照核实' if True else ''}。"
            )
        else:
            if not near:
                lines.append('卫星无法区分缺苗、渍涝或养分差异等具体原因。')
            else:
                lines.append('在缺少对应农事细节时，卫星无法进一步区分原因。')
        lines.append('</p>')
        blocks.append(''.join(lines))
        used += 1

    if late_notes:
        bits = []
        for topic, dd, status, stage in late_notes[:3]:
            bits.append(
                f"{topic}记录于 {b(dd)}（{status[:24]}），晚于本项目弱长势表末景 {b(last_all)}，"
                f"本报告卫星弱长势面积覆盖不到该时段的{topic}"
            )
        blocks.append('<p><b>方法边界：</b>' + '；'.join(bits) + '。结论中的持续弱面积主要反映末景及以前的田内相对偏弱，不代表霜后籽粒与倒伏损失。</p>')
    elif any(i['topic'] == '早霜' for i in issues) and last_all:
        blocks.append(
            f'<p><b>方法边界：</b>农事有早霜记录，请对照末景日期 {b(last_all)}：'
            f'若早霜发生在末景之后，则弱长势表覆盖不到霜害，需以田间与收获情况为准。</p>'
        )
    return '\n'.join(blocks)
