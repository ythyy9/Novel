"""Private Novel release API. No caller-supplied commands, paths, or credentials.

Run independently of the book API. Candidate code is tested in a disposable,
network-isolated systemd service before a blue/green proxy switch. This service
never writes the book root; rollback changes code routing only.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import sqlite3
import subprocess
import threading
import time
import traceback
import urllib.error
import urllib.request
import zipfile

LIMIT = 8_000_000
VALIDATION_SECONDS = 600
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def save(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".new")
    with temporary.open("wb") as f:
        f.write(encoded(value))
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)


def inventory(root):
    return {p.relative_to(root).as_posix(): sha(p.read_bytes())
            for folder in ("novel", "schemas", "tests", "adapters", "policies", "methods", "ops")
            for p in (root / folder).rglob("*")
            if p.is_file() and not p.is_symlink() and "__pycache__" not in p.parts
            and p.suffix in {".py", ".json", ".md", ".yaml", ".toml", ".html", ".css", ".js", ".svg", ".png"}}


def allowed_path(value):
    if not isinstance(value, str):
        raise ValueError("Invalid source path")
    p = PurePosixPath(value)
    if (str(p) != value or len(p.parts) != 2 or "\\" in value
            or not re.fullmatch(r"[a-zA-Z0-9_]+\.py", p.name)
            or p.parts[0] not in {"novel", "tests"}
            or (p.parts[0] == "tests" and not p.name.startswith("test_"))):
        raise ValueError("Only novel/*.py and tests/test_*.py changes are allowed")
    return value


def check_manifest(data):
    if not isinstance(data, dict) or set(data) != {"request_id", "base_sha256", "reason", "files"}:
        raise ValueError("Invalid release manifest")
    if not isinstance(data["request_id"], str) or not NAME.fullmatch(data["request_id"]):
        raise ValueError("Invalid request_id")
    if not isinstance(data["reason"], str) or not 1 <= len(data["reason"].strip()) <= 4000:
        raise ValueError("Reason required")
    if not isinstance(data["base_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", data["base_sha256"]):
        raise ValueError("Invalid base hash")
    if not isinstance(data["files"], dict) or not 1 <= len(data["files"]) <= 100:
        raise ValueError("Provide 1..100 source files; deletions are unsupported")
    output = {}
    for path, text in data["files"].items():
        allowed_path(path)
        if not isinstance(text, str):
            raise ValueError("Source content must be UTF-8 text")
        raw = text.encode("utf-8")
        if not 0 < len(raw) <= 500_000:
            raise ValueError("Source file size invalid")
        compile(text, path, "exec")  # Syntax only; never execute candidate code as root.
        output[path] = raw
    if len({p.casefold() for p in output}) != len(output):
        raise ValueError("Case collision")
    return output


class Maintenance:
    def __init__(self, config):
        self.config = config
        self.base = Path(config["base"])
        self.state_path = self.base / "current.json"
        self.lock = threading.Lock()
        # A crash must not cause an automatic second deployment.
        for path in (self.base / "releases").glob("*/receipt.json"):
            receipt = json.loads(path.read_text())
            if receipt["state"] in {"validating", "deploying"}:
                receipt.update(state="interrupted", detail="Inspect runtime before issuing a new release")
                save(path, receipt)

    def current(self):
        return json.loads(self.state_path.read_text())

    def status(self):
        current = self.current()
        files = inventory(Path(current["source"]))
        raw = self.run(["systemctl", "show", current["unit"], "--property=MainPID,ActiveState"]).stdout
        runtime = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
        pid = runtime["MainPID"]
        if pid != "0":
            runtime["cwd"] = os.readlink("/proc/" + pid + "/cwd")
            env = dict(v.split("=", 1) for v in Path("/proc/" + pid + "/environ").read_bytes().decode().split("\0") if "=" in v)
            runtime["pythonpath"] = env.get("PYTHONPATH")
        # SQLite may need writable WAL sidecars even for a read-only connection.
        # Business status stays on the existing authenticated Novel interface.
        return {"source_sha256": sha(encoded(files)), "files": files, "active": current,
                "runtime": runtime, "active_tasks": {"read_via": "novel_work_status"},
                "allowed_changes": ["novel/*.py", "tests/test_*.py"],
                "business_writes": False, "arbitrary_commands": False}

    def source_archive(self):
        root = Path(self.current()["source"])
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
            for path in inventory(root):
                z.write(root / path, path)
            z.write(self.base / "OPS-CONTRACT.md", "OPS-CONTRACT.md")
        return stream.getvalue()

    def release(self, request_id):
        if not NAME.fullmatch(request_id):
            raise ValueError("Invalid release id")
        path = self.base / "releases" / request_id / "receipt.json"
        if not path.exists():
            raise ValueError("Unknown release")
        return json.loads(path.read_text())

    def stage(self, data):
        files = check_manifest(data)
        request_id = data["request_id"]
        digest = sha(encoded(data))
        folder = self.base / "releases" / request_id
        with self.lock:
            if folder.exists():
                receipt = self.release(request_id)
                if receipt["manifest_sha256"] != digest:
                    raise ValueError("Request ID already used with different arguments")
                return receipt
            status = self.status()
            if data["base_sha256"] != status["source_sha256"]:
                raise ValueError("Stale production source; fetch the current source")
            current_source = Path(status["active"]["source"])
            case_names = {p.casefold(): p for p in status["files"]}
            for path in files:
                if path.casefold() in case_names and case_names[path.casefold()] != path:
                    raise ValueError("Case collision with existing source")
            if all((current_source / p).is_file() and (current_source / p).read_bytes() == raw for p, raw in files.items()):
                raise ValueError("No effective source change")
            folder.mkdir(mode=0o755)
            target = folder / "source"
            target.mkdir(mode=0o755)
            for path in status["files"]:
                dest = target / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(current_source / path, dest)
            for path, raw in files.items():
                dest = target / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw)
            # These are operator-owned running components, not caller changes.
            # Keep the release's auxiliary snapshot aligned with the real service
            # instead of copying a stale copy from a previous API release.
            managed = {}
            for name in ("maintenance.py", "api_runner.py"):
                actual = self.base / name
                if actual.is_file() and not actual.is_symlink():
                    relative = "ops/" + name
                    (target / "ops").mkdir(exist_ok=True)
                    shutil.copyfile(actual, target / relative)
                    managed[relative] = sha(actual.read_bytes())
            receipt = {"id": request_id, "state": "staged", "manifest_sha256": digest,
                       "base_sha256": data["base_sha256"], "source_sha256": sha(encoded(inventory(target))),
                       "changes": {p: sha(raw) for p, raw in files.items()}, "reason": data["reason"],
                       "source": str(target), "created_at": time.time(), "managed_source_snapshots": managed}
            save(folder / "receipt.json", receipt)
            return receipt

    def run(self, args, **kw):
        return subprocess.run(args, check=True, timeout=60, capture_output=True, text=True, **kw)

    def validate(self, request_id):
        with self.lock:
            receipt = self.release(request_id)
            if receipt["state"] in {"validated", "deployed", "failed"}:
                return receipt
            if receipt["state"] != "staged":
                raise ValueError("Release is busy or interrupted; inspect its receipt")
            receipt["state"] = "validating"
            path = self.base / "releases" / request_id / "receipt.json"
            save(path, receipt)
        check = self.base / "checks" / request_id
        try:
            shutil.copytree(receipt["source"], check)
            self.run(["chown", "-R", "novel-check:novel-check", str(check)])
            args = ["systemd-run", "--quiet", "--wait", "--pipe", "--collect",
                    "--unit=novel-check-" + request_id, "--working-directory=" + str(check)]
            for prop in ("User=novel-check", "Group=novel-check", "PrivateNetwork=yes",
                         "ProtectSystem=strict", "ProtectHome=yes", "NoNewPrivileges=yes",
                         "PrivateTmp=yes", "MemoryMax=256M", "CPUQuota=50%", "TasksMax=128", f"RuntimeMaxSec={VALIDATION_SECONDS}",
                         "ReadWritePaths=" + str(check),
                         "InaccessiblePaths=" + self.config["book_root"] + " /etc/agent-hub /var/lib/agent-hub /etc/novel-ops"):
                args += ["--property=" + prop]
            args += ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE=1",
                     self.config["python"], "-B", "-m", "unittest", "discover", "-s", "tests", "-v"]
            result = subprocess.run(args, timeout=VALIDATION_SECONDS + 30, capture_output=True, text=True)
            (path.parent / "tests.log").write_text(result.stdout + result.stderr)
            # Tests run on a copy. Recheck the root-owned deploy artifact.
            if sha(encoded(inventory(Path(receipt["source"])))) != receipt["source_sha256"]:
                raise ValueError("Release artifact changed during validation")
            receipt.update(state="validated" if result.returncode == 0 else "failed",
                           test_exit_code=result.returncode, test_log_tail=(result.stdout + result.stderr)[-4000:])
        except Exception as exc:
            receipt.update(state="failed", detail=type(exc).__name__ + ": " + str(exc)[:1000])
        save(path, receipt)
        return receipt

    def probe(self, url, expected=200):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(url, timeout=5) as r:
                code, release = r.status, r.headers.get("X-Novel-Release")
        except urllib.error.HTTPError as exc:
            code, release = exc.code, exc.headers.get("X-Novel-Release")
        if code != expected:
            raise ValueError("Unexpected health response: " + str(code))
        return release

    def activate(self, source, digest):
        previous = self.current()
        slot = "green" if previous["slot"] == "blue" else "blue"
        port = 8775 if slot == "blue" else 8776
        unit = "novel-api-" + slot + ".service"
        sockets = self.run(["ss", "-Hnt", "state", "established", "sport", "=", ":" + str(port)]).stdout
        if sockets.strip():
            raise ValueError("Previous API requests are still draining; retry after readback")
        cfg = Path("/etc/novel-ops")
        (cfg / (slot + ".env")).write_text("PYTHONPATH=" + source + ":" + self.config["hub_source"] +
                                         "\nNOVEL_RELEASE=" + digest + "\nNOVEL_PORT=" + str(port) + "\n")
        self.run(["systemctl", "restart", unit])
        deadline = time.monotonic() + 30
        while True:
            try:
                if self.probe("http://127.0.0.1:" + str(port) + "/healthz") != digest:
                    raise ValueError("Candidate runtime identity mismatch")
                self.probe("http://127.0.0.1:" + str(port) + "/mcp", 401)
                break
            except (OSError, ValueError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.5)
        caddy = Path(self.config["caddyfile"])
        before = caddy.read_text()
        old = "reverse_proxy 127.0.0.1:" + str(previous["port"])
        if before.count(old) != 2:
            raise ValueError("Proxy configuration changed; inspect before deployment")
        after = before.replace(old, "reverse_proxy 127.0.0.1:" + str(port))
        testfile = caddy.with_name("novel-ops-candidate.Caddyfile")
        testfile.write_text(after)
        self.run([self.config["caddy"], "validate", "--config", str(testfile), "--adapter", "caddyfile"])
        try:
            os.replace(testfile, caddy)
            self.run(["systemctl", "kill", "--kill-who=main", "--signal=USR1", self.config["proxy_unit"]])
            deadline = time.monotonic() + 20
            while self.probe(self.config["public_url"] + "/healthz") != digest:
                if time.monotonic() >= deadline:
                    raise ValueError("Public proxy did not switch")
                time.sleep(.5)
            self.probe(self.config["public_url"] + "/mcp", 401)
        except Exception:
            caddy.write_text(before)
            self.run(["systemctl", "kill", "--kill-who=main", "--signal=USR1", self.config["proxy_unit"]])
            raise
        active = {"source": source, "source_sha256": digest, "slot": slot, "port": port, "unit": unit,
                  "previous": {k: v for k, v in previous.items() if k != "previous"}}
        save(self.state_path, active)
        self.run(["systemctl", "enable", unit])
        # Existing requests retain the old upstream on a graceful Caddy reload.
        # Leave the previous API alive: a separate bounded drain checks sockets.
        threading.Thread(target=self.drain, args=(previous,), daemon=True).start()
        return active

    def drain(self, previous):
        if previous["unit"] not in {"novel-api-blue.service", "novel-api-green.service", "agent-hub-api.service"}:
            return
        for _ in range(120):
            try:
                with self.lock:
                    current = self.current()
                    if current["unit"] == previous["unit"]:
                        return
                    dependencies = self.run(["systemctl", "show", self.config["proxy_unit"],
                                             "--property=Requires,BindsTo,PartOf"]).stdout
                    if any(previous["unit"] in line.split("=", 1)[-1].split()
                           for line in dependencies.splitlines()):
                        return  # Never stop an API that still owns the live proxy.
                    sockets = self.run(["ss", "-Hnt", "state", "established", "sport", "=", ":" + str(previous["port"])]).stdout
                    if not sockets.strip():
                        self.run(["systemctl", "stop", previous["unit"]])
                        self.run(["systemctl", "disable", previous["unit"]])
                        return
            except Exception:
                return  # Preserve the old process if drain cannot be confirmed.
            time.sleep(1)

    def deploy(self, request_id):
        if not self.lock.acquire(blocking=False):
            raise ValueError("Another release operation is active")
        try:
            receipt = self.release(request_id)
            if receipt["state"] == "deployed":
                return receipt
            if receipt["state"] != "validated":
                raise ValueError("A successful isolated validation is required")
            if self.status()["source_sha256"] != receipt["base_sha256"]:
                raise ValueError("Stale production source")
            if sha(encoded(inventory(Path(receipt["source"])))) != receipt["source_sha256"]:
                raise ValueError("Validated release artifact changed")
            path = self.base / "releases" / request_id / "receipt.json"
            receipt["state"] = "deploying"
            save(path, receipt)
            try:
                receipt["active"] = self.activate(receipt["source"], receipt["source_sha256"])
                receipt.update(state="deployed", deployed_at=time.time(), business_writes=False)
            except Exception as exc:
                receipt.update(state="failed", detail=type(exc).__name__ + ": " + str(exc)[:1000])
            save(path, receipt)
            return receipt
        finally:
            self.lock.release()

    def rollback(self, expected):
        with self.lock:
            current = self.current()
            if current["source_sha256"] != expected or "previous" not in current:
                raise ValueError("Rollback target changed or absent")
            previous = current["previous"]
            if sha(encoded(inventory(Path(previous["source"])))) != previous["source_sha256"]:
                raise ValueError("Retained rollback source changed")
            active = self.activate(previous["source"], previous["source_sha256"])
            receipt = {"state": "rolled_back", "active": active, "business_writes": False, "time": time.time()}
            save(self.base / ("rollback-" + str(time.time_ns()) + ".json"), receipt)
            return receipt


class Handler(BaseHTTPRequestHandler):
    server_version = "NovelMaintenance/1"

    def log_message(self, *_):
        pass  # Never log authorization headers or uploaded source.

    def respond(self, code, value, binary=False):
        data = value if binary else encoded(value)
        self.send_response(code)
        self.send_header("Content-Type", "application/zip" if binary else "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        header = self.headers.get("Authorization", "")
        return header.startswith("Bearer ") and secrets.compare_digest(
            sha(header[7:].encode()), Path(self.server.ops.config["auth_hash_file"]).read_text().strip())

    def dispatch(self):
        self.connection.settimeout(20)
        if not self.authorized():
            return self.respond(401, {"error": "Unauthorized"})
        ops = self.server.ops
        path = self.path.removeprefix("/novel-ops")
        try:
            if self.command == "GET":
                if path == "/v1/status":
                    return self.respond(200, ops.status())
                if path == "/v1/source.zip":
                    return self.respond(200, ops.source_archive(), True)
                match = re.fullmatch(r"/v1/releases/([a-z0-9-]+)", path)
                if match:
                    return self.respond(200, ops.release(match[1]))
            if self.command == "POST":
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= LIMIT or self.headers.get("Transfer-Encoding"):
                    raise ValueError("Invalid request length")
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ValueError("Incomplete request")
                data = json.loads(body)
                if path == "/v1/releases":
                    return self.respond(200, ops.stage(data))
                if path == "/v1/rollback" and set(data) == {"expected_sha256"}:
                    return self.respond(200, ops.rollback(data["expected_sha256"]))
                match = re.fullmatch(r"/v1/releases/([a-z0-9-]+)/(validate|deploy)", path)
                if match and data == {}:
                    # Long validation uses a background job and durable readback.
                    name, action = match.groups()
                    if action == "validate":
                        receipt = ops.release(name)
                        if receipt["state"] == "staged":
                            threading.Thread(target=ops.validate, args=(name,), daemon=True).start()
                        return self.respond(202, ops.release(name))
                    return self.respond(200, ops.deploy(name))
            return self.respond(404, {"error": "Unknown operation"})
        except (ValueError, TypeError, KeyError, SyntaxError) as exc:
            return self.respond(409, {"error": str(exc)})
        except Exception:
            traceback.print_exc()
            return self.respond(500, {"error": "Operation failed; inspect persisted receipt"})

    do_GET = dispatch
    do_POST = dispatch


def main():
    config = json.loads(Path("/etc/novel-ops/config.json").read_text())
    server = ThreadingHTTPServer(("127.0.0.1", 8777), Handler)
    server.ops = Maintenance(config)
    server.serve_forever()


if __name__ == "__main__":
    main()
