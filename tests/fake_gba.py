"""Un juego de GBA (hack de pokeemerald-expansion) y un mGBA simulados para los tests.

- gba_rom(): ROM mínima con la cabecera GF, la marca RHHEXP y tablas de especies,
  objetos y movimientos con nombres en texto de GBA.
- make_pk3(): Pokémon de equipo de 100 bytes, cifrado como en el juego.
- gba_memory(): EWRAM/IWRAM con el equipo en vivo, gSaveBlock1Ptr y las medallas.
- FakeMgbaServer: servidor TCP con el mismo protocolo que mgba/omega_overlay.lua.
"""
import os
import socket
import struct
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import gen3 as G  # noqa: E402
from fake_azahar import FakeMemory  # noqa: E402

INV = {v: k for k, v in G.CHARS.items()}


def enc(text, n=None):
    b = bytes(INV[c] for c in text) + b"\xff"
    if n is not None:
        b = (b + b"\xff" * n)[:n]
    return b


# --------------------------------------------------------------------------
# ROM
# --------------------------------------------------------------------------
SPECIES = {1: (1, "Bulbasaur", (65, 0, 34)), 2: (24, "Arbok", (22, 61, 127)),
           3: (110, "Weezing", (26, 106, 165)), 4: (903, "Sneasler", (46, 53, 142))}
ITEMS = {1: "Poké Ball", 7: "Restos", 9: "Lodo Negro"}
MOVES = {1: "Destructor", 40: "Picotazo Veneno", 44: "Mordisco", 51: "Ácido", 900: "Movimiento Nuevo"}
MOVE_STRIDE = 24
SB1_SIZE, PARTY_COUNT_OFF, PARTY_OFF, FLAGS_OFF = 0x3000, 0x234, 0x238, 0x1DB0

SPECIES_AT, ITEMS_AT, MOVES_AT, TEXT_AT = 0x10000, 0x20000, 0x30000, 0x60000


def gba_rom():
    rom = bytearray(0x80000)
    rom[0xA0:0xAC] = b"POKEMON EMER"
    rom[0xAC:0xB0] = b"BPEE"
    gf = bytearray(0x110)
    struct.pack_into("<II", gf, 0, 3, 7)
    gf[8:8 + 23] = b"pokemon emerald version"
    struct.pack_into("<9I", gf, 0x50, FLAGS_OFF, 0x217E, 0x18, 0x3740, 0x3740, 0x46, 0x5F4, 0x5BD, 1025)
    o = (0x50 + 36 + 17 + 3) & ~3
    struct.pack_into("<4I", gf, o, 0x9CC, SB1_SIZE, PARTY_COUNT_OFF, PARTY_OFF)
    o += 13 * 4
    struct.pack_into("<5I", gf, o, G.ROM + SPECIES_AT, 0, 0, G.ROM + ITEMS_AT, G.ROM + MOVES_AT)
    rom[0x100:0x210] = gf
    rom[0x1FC:0x208] = b"RHHEXP" + bytes([1, 14, 4, 1]) + b"\0\0"
    for sid, (dex, name, abil) in SPECIES.items():
        base = SPECIES_AT + sid * 0xA8
        struct.pack_into("<3H", rom, base + 0x18, *abil)
        rom[base + 0x2C:base + 0x39] = enc(name, 13)
        struct.pack_into("<H", rom, base + 0x3C, dex)
    text = TEXT_AT

    def put_text(s):
        nonlocal text
        b = enc(s)
        rom[text:text + len(b)] = b
        text += len(b) + 1
        return G.ROM + text - len(b) - 1

    for iid, name in ITEMS.items():
        struct.pack_into("<I", rom, ITEMS_AT + iid * 0x2C + 0x14, put_text(name))
    for mid in range(0, 6):     # los primeros, para que se pueda deducir el tamaño de MoveInfo
        nm = MOVES.get(mid, "Mov %d" % mid)
        struct.pack_into("<II", rom, MOVES_AT + mid * MOVE_STRIDE, put_text(nm), put_text("desc"))
    for mid, nm in MOVES.items():
        struct.pack_into("<II", rom, MOVES_AT + mid * MOVE_STRIDE, put_text(nm), put_text("desc"))
    return bytes(rom)


# --------------------------------------------------------------------------
# Pokémon
# --------------------------------------------------------------------------
def make_pk3(sid, level, hp, max_hp, nick="", item=0, moves=(1, 0, 0, 0), pid=0x12345678, otid=0x0BADF00D,
             ability_num=0, evs=(0,) * 6, ivs=(31,) * 6, status=0, egg=False):
    g = bytearray(12)
    struct.pack_into("<HH", g, 0, sid & 0x7FF, item & 0x3FF)
    nk = enc(nick, 12) if nick else b"\xff" * 12
    struct.pack_into("<I", g, 4, 1000 | (nk[10] << 21))
    struct.pack_into("<H", g, 10, 4 | (nk[11] << 6))
    a = bytearray(12)
    struct.pack_into("<4H", a, 0, *moves)
    e = bytearray(12)
    e[:6] = bytes(evs)
    m = bytearray(12)
    iv = 0
    for i, v in enumerate(ivs):
        iv |= v << (5 * i)
    if egg:
        iv |= 1 << 30
    struct.pack_into("<I", m, 4, iv)
    struct.pack_into("<I", m, 8, ability_num << 29)
    blocks = {"G": bytes(g), "A": bytes(a), "E": bytes(e), "M": bytes(m)}
    order = G.ORDERS[pid % 24]
    plain = b"".join(blocks[c] for c in order)
    checksum = sum(struct.unpack("<24H", plain)) & 0xFFFF
    key = pid ^ otid
    secure = struct.pack("<12I", *[w ^ key for w in struct.unpack("<12I", plain)])
    mon = bytearray(100)
    struct.pack_into("<II", mon, 0, pid, otid)
    mon[8:18] = nk[:10]
    mon[19] = 0x02 | (0x04 if egg else 0)
    mon[20:27] = enc("ROCKET", 7)
    struct.pack_into("<H", mon, 28, checksum)
    mon[32:80] = secure
    struct.pack_into("<IBBHH", mon, 80, status, level, 0, hp, max_hp)
    return bytes(mon)


def gba_memory(party, badges=0, live_at=0x0244EC, sb1_at=0x025A00, sb1_ptr_at=0x5D8C, count_gap=3,
               saved_party=None):
    """Memoria con el equipo en vivo en EWRAM+live_at (contador justo antes) y SaveBlock1
    en EWRAM+sb1_at con su copia del equipo (saved_party, por defecto el mismo)."""
    mem = FakeMemory()
    mem.write(G.ROM, gba_rom())
    mem.write(G.EWRAM + live_at - count_gap, bytes([len(party)]))
    mem.write(G.EWRAM + live_at, b"".join(party))
    saved = party if saved_party is None else saved_party
    sb1 = bytearray(SB1_SIZE)
    sb1[PARTY_COUNT_OFF] = len(saved)
    sb1[PARTY_OFF:PARTY_OFF + 100 * len(saved)] = b"".join(saved)
    flags = badges << (G.BADGE_FLAG % 8)
    struct.pack_into("<H", sb1, FLAGS_OFF + G.BADGE_FLAG // 8, flags & 0xFFFF)
    mem.write(G.EWRAM + sb1_at, bytes(sb1))
    mem.write(G.IWRAM + sb1_ptr_at, struct.pack("<I", G.EWRAM + sb1_at))
    return mem


# --------------------------------------------------------------------------
# mGBA simulado (mismo protocolo que el script de Lua)
# --------------------------------------------------------------------------
class FakeMgbaServer:
    def __init__(self, mem):
        self.mem = mem
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(4)
        self.srv.settimeout(0.1)
        self.port = self.srv.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(1)
        self.srv.close()

    def _run(self):
        while not self._stop.is_set():
            try:
                c, _ = self.srv.accept()
            except (socket.timeout, OSError):
                continue
            threading.Thread(target=self._serve, args=(c,), daemon=True).start()

    def _serve(self, c):
        buf = b""
        with c:
            c.settimeout(0.2)
            while not self._stop.is_set():
                try:
                    data = c.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    return
                if not data:
                    return
                buf += data
                while len(buf) >= 8:
                    addr, n = struct.unpack_from("<II", buf)
                    buf = buf[8:]
                    out = self.mem.read(addr, n) if 0 < n <= 65536 else b""
                    c.sendall(struct.pack("<I", len(out)) + out)
