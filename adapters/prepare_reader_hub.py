"""Add reader registration to an explicit Hub source copy, never to a live service."""
import argparse
import ast
import hashlib
from pathlib import Path

ANCHOR = '    dist = ROOT / "frontend" / "dist"\n'
REGISTRATION = ('    import os\n'
                '    if os.environ.get("NOVEL_DOT_REGISTRY"):\n'
                '        from novel.reader_hub import install_reader\n'
                '        install_reader(app, authenticated, os.environ["NOVEL_DOT_REGISTRY"])\n\n')


def prepare(source):
    path = Path(source) / "backend/api.py"
    before = path.read_bytes()
    text = before.decode("utf-8")
    if "from novel.reader_hub import install_reader" in text:
        raise ValueError("Reader already registered; inspect existing implementation")
    anchors = [anchor for anchor in (ANCHOR, ANCHOR.replace("\n", "\r\n")) if text.count(anchor) == 1]
    if len(anchors) != 1 or "def authenticated(request: Request):" not in text:
        raise ValueError("Hub source changed; inspect authenticated route anchor")
    anchor = anchors[0]
    registration = REGISTRATION.replace("\n", "\r\n") if anchor.endswith("\r\n") else REGISTRATION
    patched = text.replace(anchor, registration + anchor)
    ast.parse(patched)
    path.write_bytes(patched.encode("utf-8"))
    return {"before": hashlib.sha256(before).hexdigest(),
            "after": hashlib.sha256(path.read_bytes()).hexdigest(), "deployed": False}


if __name__ == "__main__":
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    print(json.dumps(prepare(parser.parse_args().source), indent=2))
