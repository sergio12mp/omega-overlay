#!/usr/bin/env python3
"""
omega_reader.py — lee el equipo y las medallas de Pokémon Rubí Omega / Zafiro Alfa
desde Azahar (servidor RPC, UDP 45987) y los sirve a un overlay de OBS.

  1) Azahar: Emulación > Configurar > Depuración > "Activar servidor RPC"
     (actívalo ANTES de arrancar el juego).
  2) Arranca el juego en Azahar.
  3) python omega_reader.py
  4) Se abre el panel (http://localhost:8765/panel): elige distribución y estilo,
     copia la URL y pégala en OBS como fuente de navegador.

Paste de Showdown:  http://localhost:8765/showdown   (página con botón Copiar)
                    http://localhost:8765/showdown.txt
                    python omega_reader.py --showdown   (lo imprime y lo copia al portapapeles)
                    Además se guarda solo en  equipo_showdown.txt  cuando cambia el equipo.

Diagnóstico:  python omega_reader.py --probe
Solo librería estándar de Python 3.8+. Solo lectura: nunca escribe en la memoria del juego.

Direcciones y descifrado tomados del Pokémon Stream Tool de Readek (Gen 6, ORAS).
"""
import argparse
import http.server
import json
import os
import socket
import socketserver
import struct
import sys
import threading
import time
import urllib.parse

import assets as assetstore

# --------------------------------------------------------------------------
# Direcciones de memoria (ORAS). "1.4" = con el parche de día 1 (lo habitual).
# --------------------------------------------------------------------------
GAME_VERSIONS = {
    "1.4": {"party": 0x8CFB26C, "index": 0x8CFB1E0, "badges": 0x8C71DC4,
            "order": {178: 0, 180: 1, 181: 2, 183: 3, 185: 4, 187: 5}},
    "1.0": {"party": 0x8CF727C, "index": 0x8CF71F0, "badges": 0x8C6DDD4,
            "order": {114: 0, 116: 1, 118: 2, 119: 3, 121: 4, 123: 5}},
}
SLOT_STRIDE = 484      # separación entre Pokémon del equipo en memoria
SLOT_DATA = 232        # parte cifrada
STAT_OFFSET = 112      # los 22 bytes de stats están en slot + 232 + 112
STAT_SIZE = 22
MAX_DEX = 721          # Gen 6

STATUS = {1: "PAR", 2: "SLP", 3: "FRZ", 4: "BRN", 5: "PSN"}

# Juego de origen en el PK6 (byte 0xDF) -> juego que se está jugando
GAMES = {26: ("AS", "Zafiro Alfa"), 27: ("OR", "Rubí Omega")}


def detect_game(party):
    """Rubí Omega o Zafiro Alfa según el juego de origen de la mayoría del equipo
    (lo capturado o recibido en la partida lleva el juego actual). None si no se sabe."""
    votes = {}
    for p in party:
        if p.get("origin_game") in GAMES:
            votes[p["origin_game"]] = votes.get(p["origin_game"], 0) + 1
    if not votes:
        return None
    best = max(votes.values())
    winners = [g for g, n in votes.items() if n == best]
    return winners[0] if len(winners) == 1 else None

# --------------------------------------------------------------------------
# Cliente RPC de Azahar / Citra
# --------------------------------------------------------------------------
class RpcError(Exception):
    pass


class AzaharRpc:
    def __init__(self, host="127.0.0.1", port=45987, timeout=1.0):
        self.addr = (host, port)
        self.timeout = timeout
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(timeout)
        self.req_version = 2   # Azahar usa 2; se prueba también 1 (Citra clásico)
        self.req_id = 0
        self.negotiated = False

    def _roundtrip(self, version, addr, size):
        self.req_id = (self.req_id + 1) & 0xFFFFFFFF
        rid = self.req_id
        self.sock.sendto(struct.pack("<6I", version, rid, 1, 8, addr, size), self.addr)
        deadline = time.time() + self.timeout
        while True:
            left = deadline - time.time()
            if left <= 0:
                raise RpcError("timeout")
            self.sock.settimeout(left)
            try:
                msg, _ = self.sock.recvfrom(65535)
            except socket.timeout:
                raise RpcError("timeout")
            except ConnectionResetError:
                raise RpcError("Azahar no escucha en el puerto RPC")
            if len(msg) < 16:
                continue
            _v, mid, mtype, msize = struct.unpack_from("<4I", msg, 0)
            if mid != rid:          # respuesta atrasada de una petición anterior
                continue
            if mtype != 1:
                raise RpcError("respuesta inesperada (tipo %d)" % mtype)
            return msg[16:16 + msize]

    def read(self, addr, size):
        out = b""
        while len(out) < size:
            chunk = min(size - len(out), 4096)
            if not self.negotiated:
                err = None
                for ver in (self.req_version, 3 - self.req_version):
                    try:
                        data = self._roundtrip(ver, addr + len(out), chunk)
                        self.req_version = ver
                        self.negotiated = True
                        break
                    except RpcError as e:
                        err = e
                else:
                    raise err
            else:
                data = self._roundtrip(self.req_version, addr + len(out), chunk)
            if not data:
                raise RpcError("lectura vacía en 0x%X" % (addr + len(out)))
            out += data
        return out[:size]

    def reset(self):
        self.negotiated = False

    def close(self):
        self.sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# --------------------------------------------------------------------------
# Descifrado PK6 (idéntico al del Stream Tool / PokeStreamer-Tools)
# --------------------------------------------------------------------------
BLOCK = 56
BLOCK_POS = [
    [0, 0, 0, 0, 0, 0, 1, 1, 2, 3, 2, 3, 1, 1, 2, 3, 2, 3, 1, 1, 2, 3, 2, 3],
    [1, 1, 2, 3, 2, 3, 0, 0, 0, 0, 0, 0, 2, 3, 1, 1, 3, 2, 2, 3, 1, 1, 3, 2],
    [2, 3, 1, 1, 3, 2, 2, 3, 1, 1, 3, 2, 0, 0, 0, 0, 0, 0, 3, 2, 3, 2, 1, 1],
    [3, 2, 3, 2, 1, 1, 3, 2, 3, 2, 1, 1, 3, 2, 3, 2, 1, 1, 0, 0, 0, 0, 0, 0],
]


def _crypt(buf, seed, start, end):
    out = bytearray()
    for i in range(start, end, 2):
        seed = (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
        out.append(buf[i] ^ ((seed >> 16) & 0xFF))
        out.append(buf[i + 1] ^ ((seed >> 24) & 0xFF))
    return bytes(out)


def decrypt_pk6(raw):
    """raw = 232 bytes cifrados + 22 de stats. Devuelve el PK6 descifrado."""
    pv = struct.unpack_from("<I", raw, 0)[0]
    sv = ((pv >> 13) & 31) % 24
    blocks = _crypt(raw, pv, 8, 8 + 4 * BLOCK)
    stats = _crypt(raw, pv, 8 + 4 * BLOCK, len(raw))
    shuffled = b"".join(
        blocks[BLOCK * BLOCK_POS[i][sv]: BLOCK * BLOCK_POS[i][sv] + BLOCK] for i in range(4))
    return raw[:8] + shuffled + stats


def _load_data():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pokedata.json")
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return {k: {int(n): v for n, v in raw[k].items()} for k in raw}
    except Exception as e:
        print("AVISO: no se pudo leer pokedata.json (%s); el paste saldrá sin nombres." % e)
        return {"species": {}, "abilities": {}, "items": {}, "moves": {}, "itemicons": {}}


DATA = _load_data()
NATURES = ["Hardy", "Lonely", "Brave", "Adamant", "Naughty", "Bold", "Docile", "Relaxed", "Impish",
           "Lax", "Timid", "Hasty", "Serious", "Jolly", "Naive", "Modest", "Mild", "Quiet", "Bashful",
           "Rash", "Calm", "Gentle", "Sassy", "Careful", "Quirky"]


def parse_pokemon(d):
    """Devuelve un dict con los datos del Pokémon, o None si no es válido."""
    u16 = lambda o: struct.unpack_from("<H", d, o)[0]
    species = u16(0x08)
    level = d[0xEC]
    hp, max_hp = u16(0xF0), u16(0xF2)
    if not (1 <= species <= MAX_DEX and 1 <= level <= 100 and 0 < max_hp <= 999 and hp <= max_hp):
        return None
    raw_name = d[0x40:0x58]
    chars = [struct.unpack_from("<H", raw_name, i)[0] for i in range(0, 24, 2)]
    if 0 in chars:
        chars = chars[:chars.index(0)]
    try:
        name = "".join(chr(c) for c in chars)
    except ValueError:
        return None
    if not name.isprintable():
        return None
    tid, sid = u16(0x0C), u16(0x0E)
    pers = struct.unpack_from("<I", d, 0x18)[0]
    shiny = ((tid ^ sid ^ (pers >> 16) ^ (pers & 0xFFFF)) >> 4) == 0
    iv32 = struct.unpack_from("<I", d, 0x74)[0]
    g = d[0x1D]
    nature = d[0x1C]
    return {
        "species": species, "name": name, "level": level,
        "species_name": DATA["species"].get(species),
        "origin_game": d[0xDF],   # juego de origen (24 X, 25 Y, 26 Zafiro Alfa, 27 Rubí Omega)
        "hp": hp, "max_hp": max_hp, "shiny": shiny,
        "item": u16(0x0A), "status": STATUS.get(d[0xE8]),
        "item_name": DATA["items"].get(u16(0x0A)),
        "item_icon": DATA["itemicons"].get(u16(0x0A)),   # [x, y] en itemicons-sheet.png
        "form": (g & 248) >> 3,
        # --- extra para el paste de Showdown ---
        "ability": d[0x14],
        "nature": NATURES[nature] if nature < len(NATURES) else None,
        "gender": "F" if g & 2 else (None if g & 4 else "M"),
        "nicknamed": bool(iv32 >> 31),
        "moves": [u16(0x5A + 2 * i) for i in range(4)],
        # orden PK6: HP, Atk, Def, Spe, SpA, SpD
        "evs": {"HP": d[0x1E], "Atk": d[0x1F], "Def": d[0x20], "SpA": d[0x22], "SpD": d[0x23], "Spe": d[0x21]},
        "ivs": {"HP": iv32 & 31, "Atk": (iv32 >> 5) & 31, "Def": (iv32 >> 10) & 31,
                "Spe": (iv32 >> 15) & 31, "SpA": (iv32 >> 20) & 31, "SpD": (iv32 >> 25) & 31},
    }


def showdown_paste(party):
    """Texto en formato Pokémon Showdown para importar el equipo."""
    blocks = []
    for p in party:
        sp = DATA["species"].get(p["species"], "Pokemon-%d" % p["species"])
        head = sp
        if p["nicknamed"] and p["name"] and p["name"].lower() != sp.lower():
            head = "%s (%s)" % (p["name"], sp)
        if p["gender"]:
            head += " (%s)" % p["gender"]
        item = DATA["items"].get(p["item"])
        if item:
            head += " @ " + item
        lines = [head]
        ab = DATA["abilities"].get(p["ability"])
        if ab:
            lines.append("Ability: " + ab)
        if p["level"] != 100:
            lines.append("Level: %d" % p["level"])
        if p["shiny"]:
            lines.append("Shiny: Yes")
        order = ["HP", "Atk", "Def", "SpA", "SpD", "Spe"]
        evs = ["%d %s" % (p["evs"][k], k) for k in order if p["evs"][k]]
        if evs:
            lines.append("EVs: " + " / ".join(evs))
        if p["nature"]:
            lines.append(p["nature"] + " Nature")
        ivs = ["%d %s" % (p["ivs"][k], k) for k in order if p["ivs"][k] != 31]
        if ivs:
            lines.append("IVs: " + " / ".join(ivs))
        for m in p["moves"]:
            mv = DATA["moves"].get(m)
            if mv:
                lines.append("- " + mv)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + ("\n" if blocks else "")


# --------------------------------------------------------------------------
# Lectura del juego
# --------------------------------------------------------------------------
def read_slots(rpc, ver):
    base = GAME_VERSIONS[ver]["party"]
    buf = rpc.read(base, SLOT_STRIDE * 6)
    slots = []
    for i in range(6):
        s = buf[i * SLOT_STRIDE:(i + 1) * SLOT_STRIDE]
        raw = s[:SLOT_DATA] + s[SLOT_DATA + STAT_OFFSET: SLOT_DATA + STAT_OFFSET + STAT_SIZE]
        try:
            slots.append(parse_pokemon(decrypt_pk6(raw)))
        except Exception:
            slots.append(None)
    return slots


def read_state(rpc, state_ver):
    """Devuelve (estado, versión_detectada)."""
    candidates = [state_ver] if state_ver else list(GAME_VERSIONS)
    best, best_ver = None, None
    for ver in candidates:
        slots = read_slots(rpc, ver)
        n = sum(1 for s in slots if s)
        if best is None or n > sum(1 for s in best if s):
            best, best_ver = slots, ver
        if n:
            break
    ver = best_ver
    cfg = GAME_VERSIONS[ver]
    # orden real del equipo
    try:
        idx = rpc.read(cfg["index"], 24)
        order = [cfg["order"].get(idx[i * 4 + 1]) for i in range(6)]
    except RpcError:
        order = [None] * 6
    ordered = [best[o] for o in order if o is not None and best[o]]
    party = ordered if ordered else [s for s in best if s]
    badge_byte = rpc.read(cfg["badges"], 1)[0]
    badges = [bool(badge_byte & (1 << i)) for i in range(8)]
    n_valid = sum(1 for s in best if s)
    game = detect_game(party)
    return {"ok": True, "game_version": ver, "party": party, "badges": badges,
            "game": GAMES[game][0] if game else None, "game_name": GAMES[game][1] if game else None,
            "count": len(party), "valid_slots": n_valid, "updated": time.time()}, \
           (ver if n_valid else None)


# --------------------------------------------------------------------------
# Hilo lector + servidor HTTP
# --------------------------------------------------------------------------
STATE = {"ok": False, "party": [], "badges": [False] * 8, "error": "arrancando…", "updated": 0}
STATE_LOCK = threading.Lock()
PASTE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "equipo_showdown.txt")


def reader_loop(rpc, interval, verbose):
    ver = None
    last_msg = None
    last_paste = [None]
    while True:
        try:
            st, ver = read_state(rpc, ver)
            if not st["party"]:
                st["error"] = "conectado, esperando un equipo válido (¿partida cargada?)"
            msg = "OK  v%s  equipo=%d  medallas=%d" % (
                st["game_version"], st["count"], sum(st["badges"]))
        except RpcError as e:
            rpc.reset()
            ver = None
            st = {"ok": False, "party": [], "badges": [False] * 8, "updated": time.time(),
                  "error": "sin respuesta de Azahar (%s). ¿RPC activado y juego en marcha?" % e}
            msg = "SIN CONEXIÓN: " + st["error"]
        except Exception as e:  # nunca matar el hilo
            st = {"ok": False, "party": [], "badges": [False] * 8, "updated": time.time(),
                  "error": "error interno: %r" % (e,)}
            msg = st["error"]
        paste = showdown_paste(st["party"]) if st.get("ok") else None
        with STATE_LOCK:
            STATE.clear()
            STATE.update(st)
            if paste:
                STATE["showdown"] = paste
        if paste and paste != last_paste[0]:
            last_paste[0] = paste
            try:
                with open(PASTE_FILE, "w", encoding="utf-8") as f:
                    f.write(paste)
            except OSError:
                pass
        if msg != last_msg or verbose:
            print(time.strftime("%H:%M:%S"), msg, flush=True)
            if st.get("ok") and st["party"] and msg != last_msg:
                for p in st["party"]:
                    print("     #%03d %-12s Nv.%-3d %d/%d%s" % (
                        p["species"], p["name"], p["level"], p["hp"], p["max_hp"],
                        "  (shiny)" if p["shiny"] else ""))
            last_msg = msg
        time.sleep(interval)


SHOWDOWN_PAGE = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<title>Paste de Showdown</title><style>
body{background:#1a0509;color:#fff;font-family:system-ui,sans-serif;margin:24px}
textarea{width:100%%;height:70vh;background:#0e0206;color:#ffe3a6;border:1px solid #ffc86b;
border-radius:8px;padding:12px;font:15px/1.4 Consolas,monospace}
button{background:#ff7a2a;border:0;border-radius:6px;padding:10px 18px;font-weight:700;cursor:pointer}
</style></head><body><p><button onclick="navigator.clipboard.writeText(document.getElementById('t').value);
this.textContent='¡Copiado!'">Copiar</button>
&nbsp;Recarga la página para actualizar. También se guarda en equipo_showdown.txt.</p>
<textarea id="t" readonly>%s</textarea></body></html>"""

ASSETS = assetstore.AssetStore()   # medallas e iconos descargados (caché del usuario)

PAGES = {
    "/": "/overlay/scene.html",          # escena completa (URL histórica de OBS)
    "/index.html": "/overlay/scene.html",
    "/panel": "/overlay/panel.html",     # panel de configuración con vista previa
    "/widget": "/overlay/widget.html",   # piezas sueltas
}
ALLOWED_EXT = {".html", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".css", ".js", ".woff2", ".ttf"}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=os.path.dirname(os.path.abspath(__file__)), **k)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")

    def _send(self, body, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8", code)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/assets/download":
            started = ASSETS.download_in_background()
            self._json({"started": started, "status": ASSETS.status()})
            return
        self.send_error(404)

    def _serve_asset(self, rel):
        if rel == "status.json":
            self._json(ASSETS.status())
            return
        real = ASSETS.resolve(rel)
        if not real or os.path.splitext(real)[1].lower() not in ALLOWED_EXT:
            self.send_error(404)
            return
        with open(real, "rb") as f:
            body = f.read()
        self._send(body, self.guess_type(real))

    def do_GET(self):
        path = urllib.parse.unquote(self.path.split("?", 1)[0])
        if path.startswith("/assets/"):
            self._serve_asset(path[len("/assets/"):])
            return
        if path == "/state.json":
            with STATE_LOCK:
                body = json.dumps(STATE).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return
        if path in ("/showdown", "/showdown.txt"):
            with STATE_LOCK:
                txt = STATE.get("showdown", "")
            if path == "/showdown.txt":
                body, ctype = txt.encode("utf-8"), "text/plain; charset=utf-8"
            else:
                import html as _h
                body = (SHOWDOWN_PAGE % _h.escape(txt or "(aún no hay equipo leído)")).encode("utf-8")
                ctype = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return
        query = ("?" + self.path.split("?", 1)[1]) if "?" in self.path else ""
        if path in ("/styles", "/panel/"):
            self.send_response(302)
            self.send_header("Location", "/panel")
            self.end_headers()
            return
        if path in PAGES:
            self.path = PAGES[path] + query
        elif os.path.splitext(path)[1].lower() not in ALLOWED_EXT or path.endswith(".py"):
            self.send_error(404)
            return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def probe(rpc):
    print("Probando RPC de Azahar en %s:%d …" % rpc.addr)
    try:
        rpc.read(0x8000000, 4)
        print("  [OK] Azahar responde (versión de petición %d)." % rpc.req_version)
    except RpcError as e:
        print("  [FALLO] %s" % e)
        print("  -> Comprueba: Emulación > Configurar > Depuración > 'Activar servidor RPC', "
              "activado ANTES de arrancar el juego, y que hay un juego en marcha.")
        return 1
    for ver in GAME_VERSIONS:
        try:
            slots = read_slots(rpc, ver)
        except RpcError as e:
            print("  v%s: %s" % (ver, e))
            continue
        valid = [s for s in slots if s]
        print("  v%s: %d Pokémon válidos" % (ver, len(valid)))
        for s in valid:
            print("       #%03d %-12s Nv.%d %d/%d" % (s["species"], s["name"], s["level"], s["hp"], s["max_hp"]))
        try:
            b = rpc.read(GAME_VERSIONS[ver]["badges"], 1)[0]
            print("       byte de medallas: 0x%02X" % b)
        except RpcError:
            pass
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true", help="solo comprobar la conexión y salir")
    ap.add_argument("--showdown", action="store_true",
                    help="leer el equipo una vez, imprimir el paste de Showdown y copiarlo al portapapeles")
    ap.add_argument("--port", type=int, default=8765, help="puerto HTTP del overlay (8765)")
    ap.add_argument("--rpc-port", type=int, default=45987, help="puerto RPC de Azahar (45987)")
    ap.add_argument("--interval", type=float, default=1.0, help="segundos entre lecturas (1.0)")
    ap.add_argument("--no-browser", action="store_true", help="no abrir el panel en el navegador al arrancar")
    ap.add_argument("--sin-descargas", action="store_true",
                    help="no descargar medallas ni iconos oficiales (se usan los propios)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    rpc = AzaharRpc(port=a.rpc_port)
    if a.probe:
        sys.exit(probe(rpc))
    if a.showdown:
        try:
            st, _ = read_state(rpc, None)
        except RpcError as e:
            print("No se pudo leer de Azahar: %s" % e)
            sys.exit(1)
        paste = showdown_paste(st["party"])
        print(paste or "(no hay equipo válido todavía)")
        if paste:
            with open(PASTE_FILE, "w", encoding="utf-8") as f:
                f.write(paste)
            try:
                import subprocess
                subprocess.run(["clip"], input=paste.encode("utf-16"), check=True)
                print("-> copiado al portapapeles y guardado en equipo_showdown.txt")
            except Exception:
                print("-> guardado en equipo_showdown.txt (no se pudo usar el portapapeles)")
        sys.exit(0)

    st = ASSETS.status()
    if not st["complete"] and not a.sin_descargas:
        print("Descargando medallas e iconos oficiales (%d archivos, %d KB) a %s …" % (
            len(st["missing"]), st["bytes_missing"] // 1024, st["dir"]))
        ASSETS.download_in_background()
    threading.Thread(target=reader_loop, args=(rpc, a.interval, a.verbose), daemon=True).start()
    srv = Server(("127.0.0.1", a.port), Handler)
    panel = "http://localhost:%d/panel" % a.port
    print("Panel (elige el diseño y copia la URL para OBS): " + panel)
    print("Escena completa por defecto: http://localhost:%d/   (estado: /state.json)" % a.port)
    print("Ctrl+C para salir.")
    if not a.no_browser:
        import webbrowser
        threading.Timer(0.5, webbrowser.open, args=(panel,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
