#!/usr/bin/env python3
import json, urllib.request, urllib.parse
from pathlib import Path
import make_flag_cards as m

codes = list(m.SOVEREIGN)
# one big query
vals = ' '.join(f'"{c}"' for c in codes)
q = f'''SELECT DISTINCT ?iso ?langLabel ?curLabel WHERE {{
  VALUES ?iso {{ {vals} }}
  ?item wdt:P297 ?iso .
  OPTIONAL {{ ?item wdt:P37 ?lang . }}
  OPTIONAL {{ ?item wdt:P38 ?cur . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "pl,en" . }}
}}'''
url = 'https://query.wikidata.org/sparql?' + urllib.parse.urlencode({'query': q, 'format': 'json'})
req = urllib.request.Request(url, headers={'User-Agent': 'make_flag_cards.py/1.0'})
with urllib.request.urlopen(req, timeout=300) as r:
    data = json.loads(r.read())
from collections import defaultdict
langs = defaultdict(list); curs = {}
for b in data['results']['bindings']:
    iso = b['iso']['value']
    if 'langLabel' in b:
        l = b['langLabel']['value']
        if l and not l.startswith('Q'):
            if l.startswith('język '): l2 = l[len('język '):]
            elif l.startswith('language '): l2 = l
            else: l2 = l
            if l2 not in langs[iso]: langs[iso].append(l2)
    if 'curLabel' in b and iso not in curs:
        c = b['curLabel']['value']
        if c and not c.startswith('Q'): curs[iso] = c
facts = {}
for c in codes:
    ls = langs.get(c, [])[:2]
    cur = curs.get(c)
    if cur and cur.lower() == 'euro': cur = 'euro'
    parts = []
    if ls: parts.append('/'.join(ls))
    if cur: parts.append(cur)
    if parts: facts[c] = ' • '.join(parts)
Path('/root/flag_cards/facts_lang_cur.json').write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding='utf-8')
print(len(facts))
