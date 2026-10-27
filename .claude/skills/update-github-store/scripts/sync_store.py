#!/usr/bin/env python3
"""Sync the GitHub copy of the Omega Trade Route store with the live Claude store.

Usage:
  python3 -I sync_store.py LIVE_HTML [--repo DIR] [--write] [--expect-out FILE]

LIVE_HTML is the full live store page saved by the Artifact tool's read action.
Without --write it only reports the differences. With --write it rewrites the
otr-data block in DIR/index.html and decodes new photos into DIR/images/.

The result is the live store data with three exceptions:
  - store.storeLink, track, trackAt, trackSalt, trackSig keep the GitHub values;
  - every embedded photo (product img, store logo) is stored as
    images/<first 12 hex chars of SHA-1>.<ext> and referenced by that path;
  - nothing outside the otr-data block is touched.
"""
import argparse
import base64
import copy
import hashlib
import json
import os
import re
import sys

DATA_RE = re.compile(r'(<script type="application/json" id="otr-data">)(.*?)(</script>)', re.S)
KEEP_TOP = ['track', 'trackAt', 'trackSalt', 'trackSig']
KEEP_STORE = ['storeLink']
EXT = {'jpeg': 'jpg', 'jpg': 'jpg', 'png': 'png', 'webp': 'webp', 'gif': 'gif'}
PRODUCT_FIELDS = ['name', 'price', 'cat', 'note', 'options', 'options2', 'status', 'img',
                  'shipLo', 'shipHi', 'variantOf', 'variantLabel', 'vname']


def load(path):
    text = open(path, encoding='utf8').read()
    m = DATA_RE.search(text)
    if not m:
        sys.exit('No otr-data block found in %s' % path)
    return text, m, json.loads(m.group(2))


def dump(data):
    return json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')


def page_code(text):
    """Everything after </head><body> with the data block blanked out.
    The GitHub copy has its own <head> (link-preview tags), so the head is skipped."""
    body = text.split('</head><body>', 1)[-1]
    return DATA_RE.sub(r'\1\3', body)


def decode(uri):
    m = re.match(r'data:image/([a-zA-Z0-9.+-]+);base64,(.*)$', uri, re.S)
    if not m:
        return None, None
    raw = base64.b64decode(m.group(2))
    ext = EXT.get(m.group(1).lower(), m.group(1).lower())
    return 'images/%s.%s' % (hashlib.sha1(raw).hexdigest()[:12], ext), raw


def short(v, n=70):
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= n else s[:n] + '...'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('live')
    ap.add_argument('--repo', default='.')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--expect-out', help='write JSON of products the browser check should find')
    a = ap.parse_args()

    index = os.path.join(a.repo, 'index.html')
    gtext, gm, gh = load(index)
    ltext, _, live = load(a.live)
    problems, notes, new_files = [], [], {}

    if dump(gh) != gm.group(2):
        notes.append('Note: GitHub data does not round-trip byte for byte; formatting of the data line may change.')
    if page_code(gtext) != page_code(ltext):
        problems.append('Page code (HTML/CSS/JS outside the data) differs between live and GitHub. '
                        'Not applied: this sync only updates store data. Ask the user before changing page code.')

    def to_path(uri, label):
        if not isinstance(uri, str) or not uri:
            return uri
        if uri.startswith('data:'):
            path, raw = decode(uri)
            if not path:
                problems.append('%s: unrecognised embedded image, left out' % label)
                return uri
            full = os.path.join(a.repo, path)
            if os.path.exists(full):
                if open(full, 'rb').read() != raw:
                    problems.append('%s: %s exists with different bytes (SHA-1 prefix collision?)' % (label, path))
            else:
                new_files[path] = raw
            return path
        if not os.path.exists(os.path.join(a.repo, uri)) and not re.match(r'https?://', uri):
            problems.append('%s: image %s is not in the repo' % (label, uri))
        return uri

    new = copy.deepcopy(live)
    new['store']['logo'] = to_path(new['store'].get('logo'), 'store logo')
    for p in new['products']:
        p['img'] = to_path(p.get('img'), '#%s %s' % (p.get('id'), p.get('name')))
    for k in KEEP_STORE:
        if k in gh.get('store', {}):
            new['store'][k] = gh['store'][k]
        else:
            new['store'].pop(k, None)
    for k in KEEP_TOP:
        if k in gh:
            new[k] = gh[k]
        else:
            new.pop(k, None)

    # ---- report ----
    report = []
    gp = {p['id']: p for p in gh['products']}
    np_ = {p['id']: p for p in new['products']}
    added = [np_[i] for i in np_ if i not in gp]
    removed = [gp[i] for i in gp if i not in np_]
    changed = []
    for i, p in np_.items():
        if i in gp:
            fields = [f for f in sorted(set(p) | set(gp[i]) | set(PRODUCT_FIELDS)) if f != 'id' and p.get(f) != gp[i].get(f)]
            if fields:
                changed.append((p, fields))
    for p in added:
        report.append('ADDED   #%s %s | %s | %s %s | status %s%s' % (
            p['id'], p['name'], p.get('cat'), live.get('currency', ''), p.get('price'), p.get('status'),
            ' | variant of #%s' % p['variantOf'] if p.get('variantOf') is not None else ''))
    for p, fields in changed:
        report.append('CHANGED #%s %s' % (p['id'], p['name']))
        for f in fields:
            report.append('          %s: %s -> %s' % (f, short(gp[p['id']].get(f)), short(p.get(f))))
    for p in removed:
        report.append('REMOVED #%s %s (its photo file is left in images/)' % (p['id'], p['name']))
    if [p['id'] for p in gh['products'] if p['id'] in np_] != [p['id'] for p in new['products'] if p['id'] in gp]:
        report.append('REORDERED products (order now follows the live store)')
    for k in sorted(set(new) | set(gh)):
        if k in ('products',) or k in KEEP_TOP:
            continue
        if isinstance(new.get(k), dict) and isinstance(gh.get(k), dict):
            for kk in sorted(set(new[k]) | set(gh[k])):
                if new[k].get(kk) != gh[k].get(kk):
                    report.append('FIELD   %s.%s: %s -> %s' % (k, kk, short(gh[k].get(kk)), short(new[k].get(kk))))
        elif new.get(k) != gh.get(k):
            report.append('FIELD   %s: %s -> %s' % (k, short(gh.get(k)), short(new.get(k))))
    kept = [k for k in KEEP_TOP if live.get(k) != gh.get(k)] + \
           ['store.' + k for k in KEEP_STORE if live.get('store', {}).get(k) != gh.get('store', {}).get(k)]
    nulls = sum(1 for i, p in np_.items() if i in gp for f in set(p) ^ set(gp[i]) if p.get(f) is None and gp[i].get(f) is None)
    if nulls and report:
        notes.append('Note: %d empty field(s) (null vs missing, e.g. "variantOf":null) also follow the live store; the page treats them the same.' % nulls)
    if kept:
        notes.append('Kept GitHub values for: %s (live differs, as expected).' % ', '.join(kept))

    print('Live: %d products, nextId %s | GitHub: %d products, nextId %s' % (
        len(live['products']), live.get('nextId'), len(gh['products']), gh.get('nextId')))
    print('\n'.join(report) if report else 'NO DIFFERENCES: GitHub already matches the live store.')
    for f in sorted(new_files):
        print('NEW FILE %s (%d bytes)' % (f, len(new_files[f])))
    for n in notes:
        print(n)
    for pr in problems:
        print('PROBLEM ' + pr)

    if a.expect_out:
        byid = {p['id']: p for p in new['products']}
        exp = []
        for p in added + [c[0] for c in changed]:
            parent = byid.get(p.get('variantOf')) if p.get('variantOf') is not None else None
            exp.append({'id': p['id'], 'name': p['name'], 'status': p.get('status'), 'img': p.get('img'),
                        'card': parent['name'] if parent and parent.get('variantLabel') and parent.get('status') != 'hidden' else p['name']})
        json.dump({'expect': exp, 'imgs': sorted({p['img'] for p in new['products'] if isinstance(p.get('img'), str) and p['img'].startswith('images/')} |
                                                 ({new['store']['logo']} if str(new['store'].get('logo', '')).startswith('images/') else set()))},
                  open(a.expect_out, 'w', encoding='utf8'), ensure_ascii=False, indent=1)

    if a.write and report:
        os.makedirs(os.path.join(a.repo, 'images'), exist_ok=True)
        for path, raw in new_files.items():
            with open(os.path.join(a.repo, path), 'wb') as fh:
                fh.write(raw)
        out = gtext[:gm.start(2)] + dump(new) + gtext[gm.end(2):]
        with open(index, 'w', encoding='utf8') as fh:
            fh.write(out)
        print('WROTE index.html and %d new image file(s).' % len(new_files))
    elif a.write:
        print('Nothing written.')
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
