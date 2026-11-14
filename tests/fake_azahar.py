"""Azahar simulado para los tests: memoria falsa de ORAS y servidor RPC por UDP.

Construye Pokémon PK6 en claro, los cifra igual que el juego y los coloca en las
direcciones de la versión elegida (1.0 o 1.4). No usa datos de ninguna partida real.
"""
import os
import socket
import struct
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import omega_reader as R  # noqa: E402

PK6_SIZE = R.SLOT_DATA + R.STAT_SIZE  # 232 cifrados + 22 de stats


# --------------------------------------------------------------------------
# Construcción de Pokémon
# --------------------------------------------------------------------------
def make_pk6(species, level, hp, max_hp, name="", item=0, status=0, pv=0x12345678,
             nature=3, ability=66, gender="M", moves=(53, 0, 0, 0),
             evs=(0, 0, 0, 0, 0, 0), ivs=(31, 31, 31, 31, 31, 31), nicknamed=False,
             tid=12345, sid=54321, pid=0xDEADBEEF, form=0, game=27):
    """PK6 descifrado (254 bytes). evs/ivs en orden PK6: HP, Atk, Def, Spe, SpA, SpD."""
    d = bytearray(PK6_SIZE)
    struct.pack_into("<I", d, 0x00, pv)
    struct.pack_into("<H", d, 0x08, species)
    struct.pack_into("<H", d, 0x0A, item)
    struct.pack_into("<H", d, 0x0C, tid)
    struct.pack_into("<H", d, 0x0E, sid)
    d[0x14] = ability
    struct.pack_into("<I", d, 0x18, pid)
    d[0x1C] = nature
    g = {"M": 0, "F": 2, None: 4}[gender]
    d[0x1D] = g | (form << 3)
    d[0x1E:0x24] = bytes(evs)
    name = name or "POKEMON"
    for i, ch in enumerate(name[:12]):
        struct.pack_into("<H", d, 0x40 + 2 * i, ord(ch))
    for i, m in enumerate(moves):
        struct.pack_into("<H", d, 0x5A + 2 * i, m)
    iv32 = 0
    for shift, v in zip((0, 5, 10, 15, 20, 25), ivs):
        iv32 |= (v & 31) << shift
    if nicknamed:
        iv32 |= 1 << 31
    struct.pack_into("<I", d, 0x74, iv32)
    d[0xDF] = game
    d[0xE8] = status
    d[0xEC] = level
    struct.pack_into("<H", d, 0xF0, hp)
    struct.pack_into("<H", d, 0xF2, max_hp)
    return bytes(d)


def encrypt_pk6(plain):
    """Inverso de omega_reader.decrypt_pk6."""
    pv = struct.unpack_from("<I", plain, 0)[0]
    sv = ((pv >> 13) & 31) % 24
    blk = R.BLOCK
    body = plain[8:8 + 4 * blk]
    shuffled = [b""] * 4
    for i in range(4):
        shuffled[R.BLOCK_POS[i][sv]] = body[blk * i: blk * i + blk]
    blocks = b"".join(shuffled)
    tail = plain[8 + 4 * blk:]
    enc_blocks = R._crypt(plain[:8] + blocks, pv, 8, 8 + 4 * blk)  # el XOR es simétrico
    enc_stats = R._crypt(plain[:8 + 4 * blk] + tail, pv, 8 + 4 * blk, len(plain))
    return plain[:8] + enc_blocks + enc_stats


def party_slot_bytes(plain):
    """Un hueco de equipo en memoria (484 bytes) a partir de un PK6 en claro."""
    enc = encrypt_pk6(plain)
    slot = bytearray(R.SLOT_STRIDE)
    slot[:R.SLOT_DATA] = enc[:R.SLOT_DATA]
    off = R.SLOT_DATA + R.STAT_OFFSET
    slot[off:off + R.STAT_SIZE] = enc[R.SLOT_DATA:]
    return bytes(slot)


# --------------------------------------------------------------------------
# Memoria simulada
# --------------------------------------------------------------------------
class FakeMemory:
    """Memoria dispersa: lo no escrito se lee como ceros."""

    def __init__(self):
        self.regions = {}  # dirección -> bytes

    def write(self, addr, data):
        self.regions[addr] = bytes(data)

    def read(self, addr, size):
        out = bytearray(size)
        for base, data in self.regions.items():
            lo, hi = max(addr, base), min(addr + size, base + len(data))
            if lo < hi:
                out[lo - addr:hi - addr] = data[lo - base:hi - base]
        return bytes(out)


def oras_memory(version, party, badges=0, order=None):
    """Memoria de ORAS con `party` (lista de PK6 en claro) en los huecos 0..n.

    order: slots de memoria en el orden real del equipo (por defecto 0..n-1).
    """
    cfg = R.GAME_VERSIONS[version]
    mem = FakeMemory()
    buf = bytearray(R.SLOT_STRIDE * 6)
    for i, p in enumerate(party):
        buf[i * R.SLOT_STRIDE:(i + 1) * R.SLOT_STRIDE] = party_slot_bytes(p)
    mem.write(cfg["party"], buf)
    slot_to_code = {v: k for k, v in cfg["order"].items()}
    idx = bytearray(24)
    for pos, slot in enumerate(order if order is not None else range(len(party))):
        idx[pos * 4 + 1] = slot_to_code[slot]
    mem.write(cfg["index"], idx)
    mem.write(cfg["badges"], bytes([badges]))
    return mem


class MemoryRpc:
    """Sustituto directo de AzaharRpc para tests sin red."""

    def __init__(self, mem):
        self.mem = mem

    def read(self, addr, size):
        return self.mem.read(addr, size)

    def reset(self):
        pass


# --------------------------------------------------------------------------
# Servidor RPC por UDP (mismo protocolo que Azahar)
# --------------------------------------------------------------------------
class FakeAzaharServer:
    """Responde peticiones de lectura de memoria como el servidor RPC de Azahar.

    accept_versions: versiones de petición que contesta (Azahar = 2, Citra = 1).
    """

    def __init__(self, mem, accept_versions=(2,), max_chunk=4096):
        self.mem = mem
        self.accept = set(accept_versions)
        self.max_chunk = max_chunk
        self.requests = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.1)
        self.port = self.sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(1)
        self.sock.close()

    def _run(self):
        while not self._stop.is_set():
            try:
                msg, peer = self.sock.recvfrom(65535)
            except (socket.timeout, OSError):
                continue
            if len(msg) < 24:
                continue
            ver, rid, rtype, _psize, addr, size = struct.unpack_from("<6I", msg, 0)
            self.requests.append((ver, addr, size))
            if ver not in self.accept or rtype != 1:
                continue  # Azahar ignora versiones que no entiende
            data = self.mem.read(addr, min(size, self.max_chunk))
            self.sock.sendto(struct.pack("<4I", ver, rid, 1, len(data)) + data, peer)
