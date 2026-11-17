from __future__ import annotations

import json, shutil, tempfile, threading, warnings, webbrowser
from datetime import date, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from openpyxl import load_workbook

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

BASE_DIR = Path(__file__).resolve().parent
SOURCE_GLOB = "*DASHBOARD FWA SURGE*.xlsx"
KNOWN_SOURCES = ()  # opsional: tambah Path(...) lain; default cukup file .xlsx di folder ini
SHEET = "TRACKER PROJECT"
FIRST_ROW = 5  # header ada di baris 4
HOST, START_PORT = "127.0.0.1", 8765

# Urutan milestone = kolom 22..34 di sheet (indeks 0-based)
MILESTONES = ["SURVEY", "PERMIT", "DRM", "MOS", "INSTAL POLE", "GALIAN", "INSTAL HDPE",
              "PULLING CABLE", "INSTAL OTB", "INSTAL ODC", "INSTAL ODP", "ON AIR / RFS", "ATP"]
MS_COL = 22


def json_value(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v if v is None or isinstance(v, (str, int, float, bool)) else str(v)


def number(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def text(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def milestone(v):
    """True / False / None (None = N/A atau kosong, tidak dihitung)."""
    if isinstance(v, bool):
        return v
    return None


def resolve_source() -> Path:
    local = [p for p in BASE_DIR.glob(SOURCE_GLOB) if not p.name.startswith("~$")]
    if local:
        return max(local, key=lambda p: p.stat().st_mtime_ns)
    for p in KNOWN_SOURCES:
        if p.is_file():
            return p
    raise FileNotFoundError("File Excel tidak ditemukan")


def _open(source: Path):
    try:
        return load_workbook(source, read_only=True, data_only=True, keep_links=False), None
    except PermissionError:
        # Excel sedang membuka file: baca salinan sementara
        tmp = Path(tempfile.mkdtemp()) / source.name
        shutil.copy2(source, tmp)
        return load_workbook(tmp, read_only=True, data_only=True, keep_links=False), tmp


def extract_dashboard(source: Path) -> dict:
    wb, tmp = _open(source)
    try:
        ws = wb[SHEET]
        rows = []
        for r in ws.iter_rows(min_row=FIRST_ROW, max_col=67, values_only=True):
            if not r[0]:  # baris tanpa NO = baris kosong / checkbox sisa
                continue
            rows.append({
                "no": number(r[0]),
                "spk": text(r[1]),
                "project": text(r[2]),
                "provinsi": text(r[3]),
                "area": text(r[4]),
                "ring": text(r[5]),
                "link": text(r[6]),
                "origin_id": text(r[7]),
                "origin_surge": text(r[9]),
                "origin_name": text(r[10]),
                "dest_id": text(r[11]),
                "dest_surge": text(r[13]),
                "dest_name": text(r[14]),
                "material": text(r[15]),
                "po_status": text(r[16]),
                "po_number": text(r[17]),
                "pic": text(r[20]),
                "jointer": text(r[21]),
                "ms": [milestone(r[MS_COL + i]) for i in range(len(MILESTONES))],
                "plan_start": json_value(r[35]),
                "plan_end": json_value(r[36]),
                "actual_start": json_value(r[38]),
                "actual_end": json_value(r[39]),
                "aging": number(r[40]),
                "deviasi": number(r[41]),
                "gap": text(r[42]),
                "validation": text(r[43]),
                "target_oa": json_value(r[56]),
                "target_atp": json_value(r[57]),
                "progress": number(r[59]),
                "status_progres": text(r[60]),
                "sisa_hari": number(r[61]),
                "status_jadwal": text(r[62]),
                "bulan_target": text(r[63]),
            })
        return {
            "meta": {  # hanya nama file, tanpa path lokal
                "source": source.name,
                "file_modified": datetime.fromtimestamp(source.stat().st_mtime).astimezone().isoformat(),
                "served_at": datetime.now().astimezone().isoformat(),
                "stale": False, "warning": None,
            },
            "milestones": MILESTONES,
            "rows": rows,
        }
    finally:
        wb.close()
        if tmp:
            shutil.rmtree(tmp.parent, ignore_errors=True)


_cache = {"key": None, "body": None}
_lock = threading.Lock()


def cached_json() -> bytes:
    """Hasil ekstraksi disimpan berdasarkan st_mtime_ns agar tidak membaca ulang tiap 60 detik."""
    src = resolve_source()
    key = (str(src), src.stat().st_mtime_ns)
    with _lock:
        if _cache["key"] != key:
            _cache["body"] = json.dumps(extract_dashboard(src), ensure_ascii=False).encode("utf-8")
            _cache["key"] = key
        return _cache["body"]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(BASE_DIR), **k)

    def _host_ok(self) -> bool:  # tolak Host asing (DNS rebinding)
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in ("127.0.0.1", "localhost")

    def do_GET(self):
        path = self.path.split("?")[0]
        if not self._host_ok():
            self.send_error(403)
            return
        if path == "/api/dashboard":
            try:
                body, code = cached_json(), 200
            except Exception as e:
                body, code = json.dumps({"error": str(e)}).encode(), 500
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in ("/", "/index.html", "/data.enc.json"):  # whitelist: bukan password.txt dll
            if path == "/":
                self.path = "/index.html"
            return super().do_GET()
        self.send_error(404)


if __name__ == "__main__":
    for port in range(START_PORT, START_PORT + 11):
        try:
            srv = ThreadingHTTPServer((HOST, port), Handler)
            break
        except OSError:
            continue
    url = f"http://{HOST}:{srv.server_port}/"
    print("Dashboard aktif:", url)
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    srv.serve_forever()
