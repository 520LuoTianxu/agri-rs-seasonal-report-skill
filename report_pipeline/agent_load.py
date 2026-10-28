# -*- coding: utf-8 -*-
"""Load per-project agent-authored analysis overrides."""
import os, json, re

ROOT = '/workspace/report_pipeline_20261027/data/agent_analysis'

def path_for(key):
    return f'{ROOT}/{key}.json'

def load_agent(key):
    p = path_for(key)
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding='utf-8'))

def render_agent(html, EV, LN, b, g, r):
    """Resolve {{EV:k}} and {{LN:k:color:text}} placeholders."""
    if not html:
        return html
    def ev(m):
        return EV(m.group(1))
    def ln(m):
        key, color, text = m.group(1), m.group(2), m.group(3)
        fn = {'r': r, 'b': b, 'g': g}.get(color, b)
        return LN(fn(text), key)
    html = re.sub(r'\{\{EV:([A-Za-z0-9_]+)\}\}', ev, html)
    html = re.sub(r'\{\{LN:([A-Za-z0-9_]+):(r|b|g):([^}]+)\}\}', ln, html)
    return html
