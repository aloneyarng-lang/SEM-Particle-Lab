#!/usr/bin/env python3
"""SEM Particle Lab local-only server. Standard-library only, no cloud upload."""
from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
INPUT = ROOT / "input"
OUTPUT = ROOT / "output"
IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}
EXPORT_EXTENSIONS = {".csv", ".png", ".svg", ".pdf"}
MAX_BYTES = 160 * 1024 * 1024


def valid_filename(raw: str, allowed: set[str]) -> str:
    name = unquote(raw)
    if (not name or name in {".", ".."} or "/" in name or "\\" in name
            or any(ord(c) < 32 or ord(c) == 127 for c in name)
            or len(name) > 210 or Path(name).suffix.lower() not in allowed):
        raise ValueError("无效文件名或文件类型")
    return name


def unique_file(folder: Path, name: str) -> Path:
    path = folder / name
    if not path.exists():
        return path
    stem, ext = path.stem, path.suffix
    for i in range(2, 10000):
        candidate = folder / f"{stem}_{i}{ext}"
        if not candidate.exists():
            return candidate
    raise ValueError("同名文件过多")


class Handler(BaseHTTPRequestHandler):
    server_version = "SEM-Particle-Lab/4.0"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}", flush=True)

    def reply(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def json_reply(self, code: int, obj) -> None:
        self.reply(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def file_reply(self, path: Path, content_type: str) -> None:
        if not path.is_file() or path.is_symlink():
            self.json_reply(404, {"error": "文件不存在"})
            return
        size = path.stat().st_size
        if size > MAX_BYTES:
            self.json_reply(413, {"error": "文件过大"})
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            with path.open("rb") as f:
                while chunk := f.read(1024 * 1024):
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in {"/", "/index.html", "/trial.html"}:
            self.file_reply(APP / "index.html", "text/html; charset=utf-8")
        elif path == "/api/inputs":
            names = sorted((p.name for p in INPUT.iterdir()
                            if p.is_file() and not p.is_symlink()
                            and p.suffix.lower() in IMAGE_EXTENSIONS), key=str.casefold)
            self.json_reply(200, names)
        elif path.startswith("/input/"):
            try:
                name = valid_filename(path.removeprefix("/input/"), IMAGE_EXTENSIONS)
            except ValueError as e:
                self.json_reply(400, {"error": str(e)})
                return
            content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
            self.file_reply(INPUT / name, content_type)
        else:
            self.json_reply(404, {"error": "路径不存在"})

    def do_POST(self) -> None:
        # Prevent unwanted requests coming from another website targeting localhost.
        origin = self.headers.get("Origin")
        if origin and not (origin.startswith("http://127.0.0.1:") or origin.startswith("http://localhost:")):
            self.json_reply(403, {"error": "请求来源不允许"})
            return
        path = urlsplit(self.path).path
        if path == "/api/open-output":
            try:
                if sys.platform == "darwin":
                    subprocess.Popen(["open", str(OUTPUT)])
                elif os.name == "nt":
                    os.startfile(str(OUTPUT))  # type: ignore[attr-defined]
                else:
                    subprocess.Popen(["xdg-open", str(OUTPUT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.json_reply(200, {"ok": True})
            except Exception as e:
                self.json_reply(500, {"error": str(e)})
            return

        if path.startswith("/api/import/"):
            folder, allowed, rawname = INPUT, IMAGE_EXTENSIONS, path.removeprefix("/api/import/")
        elif path.startswith("/api/output/"):
            folder, allowed, rawname = OUTPUT, EXPORT_EXTENSIONS, path.removeprefix("/api/output/")
        else:
            self.json_reply(404, {"error": "路径不存在"})
            return
        try:
            name = valid_filename(rawname, allowed)
            size = int(self.headers.get("Content-Length", "-1"))
            if not 0 < size <= MAX_BYTES:
                raise ValueError("文件大小不符合要求（最大 160 MB）")
            data = self.rfile.read(size)
            if len(data) != size:
                raise ValueError("文件内容传输不完整")
            dest = unique_file(folder, name)
            # Exclusive-create mode prevents overwriting previously saved lab results.
            with dest.open("xb") as stream:
                stream.write(data)
            self.json_reply(200, {"ok": True, "name": dest.name})
        except (ValueError, OSError) as e:
            self.json_reply(400, {"error": str(e)})


def main():
    for directory in (INPUT, OUTPUT):
        directory.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    print("\nSEM Particle Lab 4.0 已启动", flush=True)
    print(f"界面地址：{url}", flush=True)
    print(f"原图目录：{INPUT}", flush=True)
    print(f"导出目录：{OUTPUT}", flush=True)
    print("关闭本终端窗口或按 Ctrl+C 结束程序。\n", flush=True)
    threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n程序已结束。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
