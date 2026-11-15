"""Recursos gráficos de terceros (medallas oficiales, iconos de objetos).

No se distribuyen con el programa: se descargan desde fuentes públicas a una caché
del usuario la primera vez, según data/assets_manifest.json (URL + SHA-256).
Solo librería estándar.
"""
import hashlib
import json
import os
import struct
import threading
import time
import urllib.request

import sys

FROZEN = bool(getattr(sys, "frozen", False))
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(HERE, "data", "assets_manifest.json")
# copia manual antigua (prototipo); OMEGA_ASSETS_LEGACY=0 la ignora
LEGACY_DIR = (None if FROZEN or os.environ.get("OMEGA_ASSETS_LEGACY") == "0"
              else os.path.join(HERE, "assets"))
USER_AGENT = "OmegaOverlay/0.2"


def default_cache_dir():
    if os.environ.get("OMEGA_ASSETS_DIR"):
        return os.environ["OMEGA_ASSETS_DIR"]
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "OmegaOverlay", "assets")


def load_manifest(path=MANIFEST_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def png_size(data):
    """(ancho, alto) si es un PNG válido; si no, None."""
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def _acceptable(entry, data):
    """Devuelve (ok, motivo). Acepta el hash exacto o, si el manifiesto lo permite,
    una versión más nueva del archivo (p. ej. la hoja de Showdown cuando añade objetos)."""
    if _sha256(data) == entry["sha256"]:
        return True, "ok"
    rule = entry.get("allow_update")
    if rule and rule.get("type") == "png":
        size = png_size(data)
        if size and size[0] >= rule.get("min_width", 0) and size[1] >= rule.get("min_height", 0):
            return True, "actualizado en origen"
    return False, "el archivo descargado no coincide con el esperado"


class AssetStore:
    def __init__(self, cache_dir=None, manifest=None, legacy_dir=LEGACY_DIR, timeout=15):
        self.dir = cache_dir or default_cache_dir()
        self.manifest = manifest if manifest is not None else load_manifest()
        self.legacy_dir = legacy_dir
        self.timeout = timeout
        self.lock = threading.Lock()
        self.job = {"running": False, "done": 0, "total": 0, "errors": [], "finished": 0}

    # ---------------- rutas ----------------
    def _legacy_candidates(self, rel):
        if not self.legacy_dir:
            return []
        out = [os.path.join(self.legacy_dir, *rel.split("/"))]
        parts = rel.split("/")
        if len(parts) == 3 and parts[0] == "badges":   # badges/oras/1.png -> assets/badges/1.png
            out.append(os.path.join(self.legacy_dir, "badges", parts[2]))
        return out

    def resolve(self, rel):
        """Ruta en disco de un recurso (caché primero, después la carpeta assets/ antigua),
        o None. Nunca sale de esas carpetas."""
        rel = rel.replace("\\", "/").lstrip("/")
        if not rel or any(p in ("", ".", "..") for p in rel.split("/")):
            return None
        for root, path in [(self.dir, os.path.join(self.dir, *rel.split("/")))] + \
                          [(self.legacy_dir, p) for p in self._legacy_candidates(rel)]:
            # abspath y no realpath: en el .exe, realpath puede devolver la carpeta y el
            # archivo con formas distintas (p. ej. \\?\ o nombres cortos) y no casar nunca
            real_root = os.path.normcase(os.path.abspath(root))
            real = os.path.abspath(path)
            if os.path.normcase(real).startswith(real_root + os.sep) and os.path.isfile(real):
                return real
        return None

    # ---------------- estado ----------------
    def status(self):
        files = []
        for e in self.manifest["files"]:
            files.append({"path": e["path"], "group": e.get("group"), "source": e.get("source"),
                          "present": self.resolve(e["path"]) is not None})
        missing = [f for f in files if not f["present"]]
        with self.lock:
            job = dict(self.job, errors=list(self.job["errors"]))
        return {"dir": self.dir, "complete": not missing, "present": len(files) - len(missing),
                "total": len(files), "missing": [f["path"] for f in missing],
                "bytes_missing": sum(e.get("size", 0) for e in self.manifest["files"]
                                     if self.resolve(e["path"]) is None),
                "sources": self.manifest.get("sources", {}), "job": job}

    # ---------------- descarga ----------------
    def _fetch(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return r.read()

    def download_one(self, entry):
        data = self._fetch(entry["url"])
        ok, why = _acceptable(entry, data)
        if not ok:
            raise ValueError(why)
        dest = os.path.join(self.dir, *entry["path"].split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
        return why

    def download_missing(self):
        """Descarga lo que falte. Devuelve la lista de errores (vacía si todo fue bien)."""
        todo = [e for e in self.manifest["files"] if self.resolve(e["path"]) is None]
        with self.lock:
            if self.job["running"]:
                return None
            self.job = {"running": True, "done": 0, "total": len(todo), "errors": [], "finished": 0}
        errors = []
        for e in todo:
            try:
                self.download_one(e)
            except Exception as ex:  # red, HTTP, hash… se informa y se sigue
                errors.append("%s: %s" % (e["path"], ex))
            with self.lock:
                self.job["done"] += 1
                self.job["errors"] = list(errors)
        with self.lock:
            self.job["running"] = False
            self.job["finished"] = time.time()
        return errors

    def download_in_background(self):
        with self.lock:
            if self.job["running"]:
                return False
        threading.Thread(target=self.download_missing, daemon=True).start()
        return True
