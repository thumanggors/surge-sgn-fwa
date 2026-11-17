"""Pakai: py sync_github.py [--once]

Mengekstrak Excel -> enkripsi AES-256-GCM -> git add/commit/push, hanya bila mtime Excel berubah.
Password dibaca dari password.txt (file lokal, tidak pernah di-commit).
"""
import base64, json, os, subprocess, sys, time
from datetime import datetime

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import server

OUT = server.BASE_DIR / "data.enc.json"
INTERVAL, ITER = 60, 200_000  # ITER harus sama dengan index.html


def read_password():
    pw_file = server.BASE_DIR / "password.txt"
    if not pw_file.is_file():
        raise FileNotFoundError("password.txt belum dibuat (buat file itu, isi password pada satu baris)")
    pw = pw_file.read_text(encoding="utf-8-sig").strip()
    if not pw:
        raise ValueError("password.txt kosong")
    return pw


def encrypt(text, password=None):
    password = read_password() if password is None else password
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(hashes.SHA256(), 32, salt, ITER).derive(password.encode())
    b64 = lambda b: base64.b64encode(b).decode()
    return json.dumps({"salt": b64(salt), "iv": b64(iv),
                       "data": b64(AESGCM(key).encrypt(iv, text.encode(), None))})


def git(*args):
    kw = {"creationflags": 0x08000000} if os.name == "nt" else {}  # tanpa jendela konsol saat via pythonw
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}  # jangan menggantung menunggu prompt kredensial
    return subprocess.run(["git", *args], cwd=server.BASE_DIR, capture_output=True, text=True,
                          env=env, encoding="utf-8", errors="replace", **kw)


def stamp():
    return datetime.now().strftime("%H:%M:%S")


pending_push = False  # True bila ada commit lokal yang belum terkirim (mis. offline)


def push():
    global pending_push
    r = git("push")
    pending_push = r.returncode != 0
    print(stamp(), "push:", "OK" if not pending_push else r.stderr.strip())


def sync(last_mtime):
    src = server.resolve_source()
    mtime = src.stat().st_mtime_ns
    if mtime == last_mtime:
        if pending_push:
            push()  # ulangi push saja, tanpa ekstraksi/commit baru
        return mtime  # Excel belum berubah
    payload = server.extract_dashboard(src)
    payload["meta"].update(source=src.name, stale=False, warning=None)
    OUT.write_text(encrypt(json.dumps(payload, ensure_ascii=False)), encoding="utf-8")
    git("add", OUT.name)
    if git("diff", "--cached", "--quiet").returncode == 0:
        return mtime
    c = git("commit", "-m", f"Update data {datetime.now():%Y-%m-%d %H:%M}")
    if c.returncode != 0:
        raise RuntimeError("commit gagal: " + (c.stderr or c.stdout).strip())
    push()
    return mtime


if __name__ == "__main__":
    if sys.stdout is None:  # dijalankan lewat pythonw: log ke file
        sys.stdout = open(server.BASE_DIR / "sync.log", "a", encoding="utf-8", buffering=1)
    last = None
    while True:
        try:
            last = sync(last)
        except Exception as exc:
            print(stamp(), "gagal:", exc)
        if "--once" in sys.argv:
            break
        time.sleep(INTERVAL)
