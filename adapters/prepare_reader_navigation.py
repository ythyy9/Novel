"""Add a same-origin reading link to an explicitly selected live Hub source copy."""
import argparse
import hashlib
import json
from pathlib import Path


def prepare(frontend):
    frontend = Path(frontend)
    main = frontend / 'src/main.tsx'
    css = frontend / 'src/style.css'
    originals = {path: path.read_bytes() for path in (main, css)}
    text = originals[main].decode('utf-8')
    style = originals[css].decode('utf-8')
    anchor = '</button>)}</nav>'
    if text.count(anchor) != 1 or 'reader-nav-link' in text:
        raise ValueError('Navigation source changed or link already present; inspect before updating')
    if style.count('nav button{') != 2:
        raise ValueError('Desktop/mobile navigation styles changed; inspect before updating')
    link = ('<a className="reader-nav-link" href="/novel/reader/">'
            '<span className="nav-icon" aria-hidden="true">▤</span>逐章阅读</a>')
    text = text.replace(anchor, '</button>)}' + link + '</nav>', 1)
    # Reuse both desktop and mobile navigation rules, including focus and spacing.
    style = style.replace('nav button{', 'nav button,nav .reader-nav-link{')
    style = ('nav .reader-nav-link{font-weight:600;border-radius:8px;transition:background .15s;text-decoration:none}'
             'nav .reader-nav-link:hover{background:#eef1fa;text-decoration:none}' + style)
    main.write_bytes(text.encode('utf-8'))
    css.write_bytes(style.encode('utf-8'))
    return {str(path.relative_to(frontend)): {
        'before': hashlib.sha256(originals[path]).hexdigest(),
        'after': hashlib.sha256(path.read_bytes()).hexdigest()} for path in originals}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('frontend', type=Path)
    print(json.dumps(prepare(parser.parse_args().frontend), indent=2))
