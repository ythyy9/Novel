"""Optional authenticated Hub routes; no new permissions, tokens or write APIs."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from fastapi import Depends, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from .dot_transport import DotRegistry
from .engine import EngineError
from .reader import ASSETS, RootSource

PREFIX = "/novel/reader"
WORKSPACE = "novel-shizhi-zhicheng"
HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
           "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY"}


def install_reader(app, authenticated, registry_path):
    """Use the existing Hub web session and exact formal workspace owner."""
    registry = DotRegistry(registry_path)

    def source(session):
        data = json.loads(Path(registry.path).read_text(encoding="utf-8"))
        entry = data.get("workspaces", {}).get(WORKSPACE, {})
        if (data.get("schema_version") != 1 or not entry.get("enabled")
                or entry.get("phase") != "formal" or not session.get("owner_id")
                or entry.get("owner_id") != session["owner_id"]):
            raise PermissionError("Formal reading workspace is not authorized")
        DotRegistry._takeover(entry, WORKSPACE)
        return RootSource(entry["root"], entry["book_id"])

    def failure(exc):
        status = 403 if isinstance(exc, PermissionError) else 409
        message = "你没有这个作品的阅读权限。" if status == 403 else "正式正文暂时无法读取，请刷新重试。"
        return JSONResponse({"error": message}, status_code=status, headers=HEADERS)

    def asset(name, session):
        try:
            source(session)  # Also protect assets and the page; never trust browser owner IDs.
            return FileResponse(ASSETS / name, headers=HEADERS)
        except (PermissionError, EngineError, OSError, ValueError, KeyError) as exc:
            return failure(exc)

    @app.get(PREFIX, include_in_schema=False)
    def canonical_url():
        return RedirectResponse(PREFIX + "/", status_code=307, headers=HEADERS)

    @app.get(PREFIX + "/", include_in_schema=False)
    def reader_page(request: Request):
        try:
            session = authenticated(request)
        except Exception as exc:
            if getattr(exc, "status", getattr(exc, "status_code", None)) == 401:
                return RedirectResponse("/", status_code=303, headers=HEADERS)
            raise
        return asset("index.html", session)

    @app.get(PREFIX + "/reader.css", include_in_schema=False)
    def reader_css(session=Depends(authenticated)):
        return asset("reader.css", session)

    @app.get(PREFIX + "/reader.js", include_in_schema=False)
    def reader_js(session=Depends(authenticated)):
        return asset("reader.js", session)

    @app.get(PREFIX + "/api/book", include_in_schema=False)
    def reader_catalog(session=Depends(authenticated)):
        try:
            return JSONResponse(source(session).catalog(), headers=HEADERS)
        except (PermissionError, EngineError, OSError, ValueError, KeyError, sqlite3.Error) as exc:
            return failure(exc)

    @app.get(PREFIX + "/api/chapter", include_in_schema=False)
    def reader_chapter(request: Request, revision: str, id: str, session=Depends(authenticated)):
        if set(request.query_params) != {"revision", "id"} or len(request.query_params.multi_items()) != 2:
            return JSONResponse({"error": "章节参数无效。"}, status_code=422, headers=HEADERS)
        try:
            return JSONResponse(source(session).chapter(revision, id), headers=HEADERS)
        except (PermissionError, EngineError, OSError, ValueError, KeyError, sqlite3.Error) as exc:
            return failure(exc)
