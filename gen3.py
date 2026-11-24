"""Lectura de juegos de GBA de 3.ª generación hechos con pokeemerald-expansion
(p. ej. Pokémon Team Rocket Edition) desde mGBA.

mGBA no tiene servidor de memoria propio: el script mgba/omega_overlay.lua abre uno
(TCP, 127.0.0.1:45988) que solo permite leer. Aquí está el cliente, la lectura de la
cabecera "GF" de la ROM (tablas de especies, objetos, movimientos y offsets de la
partida), el descifrado de los Pokémon (formato PK3 ampliado) y las medallas.

Solo librería estándar.
"""
import hashlib
import socket
import struct
import time

EWRAM, EWRAM_SIZE = 0x02000000, 0x40000
IWRAM, IWRAM_SIZE = 0x03000000, 0x8000
ROM = 0x08000000
MON_SIZE = 100
BADGE_FLAG = 0x867          # FLAG_BADGE01_GET (8 seguidas)

# Hacks conocidos: huella de la cabecera GF de la ROM (sha1 de 0x100-0x210) -> (corto, nombre)
KNOWN_HACKS = {
    "755b3246cf8fbf35": ("TRE", "Team Rocket Edition"),   # Pokémon TRE 2026 (Dragonsden)
}
# Juegos sin medallas de gimnasio (TRE va por misiones): el overlay no las muestra
NO_BADGES = {"TRE"}


class RpcError(Exception):
    pass


# --------------------------------------------------------------------------
# Cliente del puente de mGBA
# --------------------------------------------------------------------------
class MgbaRpc:
    """Mismo interfaz que AzaharRpc: read(addr, size) y reset()."""

    def __init__(self, host="127.0.0.1", port=45988, timeout=1.0):
        self.addr = (host, port)
        self.timeout = timeout
        self.sock = None

    def _connect(self):
        # En Windows, conectar a un puerto cerrado de localhost tarda ~2 s en fallar:
        # con un tiempo corto no se frena la lectura cuando mGBA no está abierto.
        try:
            s = socket.create_connection(self.addr, timeout=min(self.timeout, 0.5))
        except (ConnectionRefusedError, socket.timeout):
            raise RpcError("mGBA no está abierto o no tiene cargado el script de Omega Overlay")
        s.settimeout(self.timeout)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock = s

    def _recv(self, n):
        out = b""
        while len(out) < n:
            part = self.sock.recv(n - len(out))
            if not part:
                raise RpcError("mGBA cerró la conexión")
            out += part
        return out

    def read(self, addr, size):
        try:
            if self.sock is None:
                self._connect()
            out = b""
            while len(out) < size:
                chunk = min(size - len(out), 0x8000)
                self.sock.sendall(struct.pack("<II", addr + len(out), chunk))
                n = struct.unpack("<I", self._recv(4))[0]
                data = self._recv(n) if n else b""
                if len(data) < chunk:
                    raise RpcError("lectura incompleta en 0x%X" % (addr + len(out)))
                out += data
            return out
        except RpcError:
            self.reset()
            raise
        except (OSError, socket.timeout) as e:
            self.reset()
            raise RpcError("mGBA no responde (%s)" % e)

    def reset(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None

    def close(self):
        self.reset()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# --------------------------------------------------------------------------
# Texto de GBA (tabla occidental de pokeemerald, charmap.txt; vale para el español)
# --------------------------------------------------------------------------
CHARS = dict(zip(
    [0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
     0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x20,
     0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x2B, 0x2D, 0x2E, 0x35, 0x36,
     0x51, 0x52, 0x5A, 0x5B, 0x5C, 0x5D, 0x68, 0x6F, 0x85, 0x86,
     0xAB, 0xAC, 0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xB9,
     0xBA, 0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6],
    " ÀÁÂÇÈÉÊËÌÎÏÒÓÔŒÙÚÛÑßàáçèéêëìîïòóôœùúûñºª&+=;¿¡Í%()âí<>!?.-·…“”‘’♂♀$,×/:ÄÖÜäöü"))
for _i, _c in enumerate("0123456789"):
    CHARS[0xA1 + _i] = _c
for _i in range(26):
    CHARS[0xBB + _i] = chr(65 + _i)
    CHARS[0xD5 + _i] = chr(97 + _i)


def decode_text(b):
    out = []
    for x in b:
        if x == 0xFF:
            break
        out.append(CHARS.get(x, ""))
    return "".join(out).strip()


# --------------------------------------------------------------------------
# Datos de la ROM (cabecera GF de pokeemerald-expansion)
# --------------------------------------------------------------------------
SPECIES_STRIDE = 0xA8   # sizeof(SpeciesInfo) en expansion 1.14 (se comprueba al cargar)
ITEM_STRIDE = 0x2C      # sizeof(struct Item)
MOVE_STRIDE = None      # se deduce


class RomInfo:
    """Lo que hace falta de la ROM, leído una vez a través del emulador."""

    def __init__(self, rpc):
        self.rpc = rpc
        head = rpc.read(ROM + 0xA0, 0x20)
        self.title = head[:12].rstrip(b"\0").decode("latin-1")
        self.code = head[12:16].decode("latin-1")
        rom_head = rpc.read(ROM + 0x100, 0x110)
        gf = rom_head
        self.expansion = None
        exp = rpc.read(ROM + 0x1FC, 12)
        if exp[:6] == b"RHHEXP":
            self.expansion = "%d.%d.%d" % (exp[6], exp[7], exp[8])
        u32 = lambda o: struct.unpack_from("<I", gf, o)[0]
        self.language = u32(0x04)
        # posiciones según struct GFRomHeader (src/rom_header_gf.c)
        o = 0x50
        (self.flags_off, self.vars_off, _dex, _s1, _s2, _pv, _pf, _mf, self.dex_count) = struct.unpack_from("<9I", gf, o)
        o += 36 + 17
        o = (o + 3) & ~3
        (self.sb2_size, self.sb1_size, self.party_count_off, self.party_off) = struct.unpack_from("<4I", gf, o)
        o += 13 * 4
        (self.species_ptr, _an, _ad, self.items_ptr, self.moves_ptr) = struct.unpack_from("<5I", gf, o)
        if not (self.expansion and self.species_ptr and self.items_ptr and self.moves_ptr):
            raise RpcError("juego de GBA no compatible (de momento, solo hacks de pokeemerald-expansion)")
        self.fingerprint = hashlib.sha1(rom_head).hexdigest()[:16]
        self._species, self._items, self._moves = {}, {}, {}
        self._check_species_stride()

    def _check_species_stride(self):
        global SPECIES_STRIDE
        for stride in (0xA8, 0xC4, 0xB0, 0xB8, 0xC0, 0xAC):
            nm = decode_text(self.rpc.read(self.species_ptr + stride + 0x2C, 13))
            if nm.lower() == "bulbasaur":
                SPECIES_STRIDE = stride
                return
        raise RpcError("no se reconoce la tabla de especies de esta ROM")

    def species(self, sid):
        """(número de la Pokédex nacional, nombre, habilidades) de una especie interna."""
        if sid not in self._species:
            b = self.rpc.read(self.species_ptr + sid * SPECIES_STRIDE, 0x40)
            abil = struct.unpack_from("<3H", b, 0x18)
            self._species[sid] = (struct.unpack_from("<H", b, 0x3C)[0], decode_text(b[0x2C:0x39]), abil,
                                  (b[6], b[7]))
        return self._species[sid]

    def _ptr_text(self, ptr, n=24):
        if not (ROM <= ptr < ROM + 0x2000000):
            return ""
        return decode_text(self.rpc.read(ptr, n))

    def item_name(self, iid):
        if not iid:
            return None
        if iid not in self._items:
            ptr = struct.unpack("<I", self.rpc.read(self.items_ptr + iid * ITEM_STRIDE + 0x14, 4))[0]
            self._items[iid] = self._ptr_text(ptr) or None
        return self._items[iid]

    def move_name(self, mid):
        if not mid:
            return None
        if mid not in self._moves:
            stride = self._move_stride()
            ptr = struct.unpack("<I", self.rpc.read(self.moves_ptr + mid * stride, 4))[0]
            self._moves[mid] = self._ptr_text(ptr) or None
        return self._moves[mid]

    def _move_stride(self):
        global MOVE_STRIDE
        if MOVE_STRIDE is None:
            # MoveInfo empieza con el puntero al nombre: el tamaño es la distancia entre
            # dos punteros a texto seguidos (se prueba con los primeros movimientos)
            blob = self.rpc.read(self.moves_ptr, 0x400)
            for stride in range(12, 0x80, 4):
                ptrs = [struct.unpack_from("<I", blob, i * stride)[0] for i in range(1, 6)]
                if all(ROM <= p < ROM + 0x2000000 for p in ptrs) and len(set(ptrs)) == 5:
                    descs = [struct.unpack_from("<I", blob, i * stride + 4)[0] for i in range(1, 6)]
                    if all(ROM <= p < ROM + 0x2000000 for p in descs):
                        MOVE_STRIDE = stride
                        break
            else:
                raise RpcError("no se reconoce la tabla de movimientos de esta ROM")
        return MOVE_STRIDE


# --------------------------------------------------------------------------
# Pokémon (formato PK3 de expansion 1.14)
# --------------------------------------------------------------------------
ORDERS = ["GAEM", "GAME", "GEAM", "GEMA", "GMAE", "GMEA", "AGEM", "AGME", "AEGM", "AEMG", "AMGE", "AMEG",
          "EGAM", "EGMA", "EAGM", "EAMG", "EMGA", "EMAG", "MGAE", "MGEA", "MAGE", "MAEG", "MEGA", "MEAG"]
STATUS = {0: None}
NATURES = ["Hardy", "Lonely", "Brave", "Adamant", "Naughty", "Bold", "Docile", "Relaxed", "Impish", "Lax",
           "Timid", "Hasty", "Serious", "Jolly", "Naive", "Modest", "Mild", "Quiet", "Bashful", "Rash",
           "Calm", "Gentle", "Sassy", "Careful", "Quirky"]


def status_name(s):
    if s & 0x7:
        return "SLP"
    if s & 0x8 or s & 0x80:
        return "PSN"
    if s & 0x10:
        return "BRN"
    if s & 0x20:
        return "FRZ"
    if s & 0x40:
        return "PAR"
    return None


def decrypt(mon):
    """Devuelve los 4 bloques (G, A, E, M) descifrados o None si el checksum falla."""
    pid, otid = struct.unpack_from("<II", mon, 0)
    key = pid ^ otid
    raw = struct.unpack_from("<12I", mon, 32)
    plain = struct.pack("<12I", *[w ^ key for w in raw])
    if sum(struct.unpack("<24H", plain)) & 0xFFFF != struct.unpack_from("<H", mon, 28)[0]:
        return None
    order = ORDERS[pid % 24]
    blocks = {order[i]: plain[i * 12:(i + 1) * 12] for i in range(4)}
    return blocks


def raw_valid(mon):
    """Comprobación rápida (sin la ROM) de que 100 bytes son un Pokémon de equipo válido."""
    if len(mon) < MON_SIZE or mon[:8] == b"\0" * 8:
        return False
    flags = mon[19]
    if not flags & 0x02:            # hasSpecies
        return False
    level, hp, max_hp = mon[84], *struct.unpack_from("<HH", mon, 86)
    if not (1 <= level <= 100 and 0 < max_hp <= 999 and hp <= max_hp):
        return False
    b = decrypt(mon)
    if not b:
        return False
    species = struct.unpack_from("<H", b["G"], 0)[0] & 0x7FF
    return 0 < species


def parse_mon(mon, rom):
    if not raw_valid(mon):
        return None
    b = decrypt(mon)
    g, a, e, m = b["G"], b["A"], b["E"], b["M"]
    pid, otid = struct.unpack_from("<II", mon, 0)
    w0, w1 = struct.unpack_from("<HH", g, 0)
    sid, item = w0 & 0x7FF, w1 & 0x3FF
    exp_word = struct.unpack_from("<I", g, 4)[0]
    pokeball_word = struct.unpack_from("<H", g, 10)[0]
    nick = bytes(mon[8:18]) + bytes([(exp_word >> 21) & 0xFF, (pokeball_word >> 6) & 0xFF])
    moves = [x & 0x7FF for x in struct.unpack_from("<4H", a, 0)]
    evs = e[:6]
    ivw = struct.unpack_from("<I", m, 4)[0]
    misc = struct.unpack_from("<I", m, 8)[0]
    is_egg = bool(mon[19] & 0x04) or bool((ivw >> 30) & 1)
    dex, sp_name, abilities, _types = rom.species(sid)
    ability = abilities[(misc >> 29) & 3] if ((misc >> 29) & 3) < 3 else abilities[0]
    shiny_mod = struct.unpack_from("<H", mon, 30)[0] >> 14 & 1
    shiny = bool(shiny_mod) or ((otid & 0xFFFF) ^ (otid >> 16) ^ (pid & 0xFFFF) ^ (pid >> 16)) < 8
    nature = ((pid % 25) ^ (mon[18] >> 3)) % 25
    level, = struct.unpack_from("<B", mon, 84)
    hp, max_hp = struct.unpack_from("<HH", mon, 86)
    name = decode_text(nick) or sp_name
    return {
        "species": dex or sid,        # número nacional: lo usa el overlay para el sprite
        "species_id": sid,            # número interno de la ROM
        "species_name": sp_name,
        "name": "Huevo" if is_egg else name,
        "level": level, "hp": hp, "max_hp": max_hp, "shiny": shiny,
        "status": status_name(struct.unpack_from("<I", mon, 80)[0]),
        "item": item, "item_name": rom.item_name(item), "item_icon": None,
        "form": 0, "origin_game": None, "egg": is_egg,
        "ability_id": ability, "nature": NATURES[nature],
        "gender": None, "nicknamed": bool(name) and name.lower() != sp_name.lower(),
        "move_ids": moves, "move_names": [rom.move_name(x) for x in moves if x],
        "evs": {"HP": evs[0], "Atk": evs[1], "Def": evs[2], "Spe": evs[3], "SpA": evs[4], "SpD": evs[5]},
        "ivs": {"HP": ivw & 31, "Atk": (ivw >> 5) & 31, "Def": (ivw >> 10) & 31,
                "Spe": (ivw >> 15) & 31, "SpA": (ivw >> 20) & 31, "SpD": (ivw >> 25) & 31},
    }


# --------------------------------------------------------------------------
# Dónde está cada cosa en la RAM
# --------------------------------------------------------------------------
def find_parties(ewram):
    """Posiciones (en EWRAM) donde empieza un bloque de hasta 6 Pokémon válidos."""
    found = []
    i = 0
    while i + MON_SIZE <= len(ewram):
        if ewram[i + 19] & 0x02 and raw_valid(ewram[i:i + MON_SIZE]):
            # retroceder hasta el primero del bloque
            start = i
            while start - MON_SIZE >= 0 and raw_valid(ewram[start - MON_SIZE:start]):
                start -= MON_SIZE
            n = 0
            while n < 6 and raw_valid(ewram[start + n * MON_SIZE:start + (n + 1) * MON_SIZE]):
                n += 1
            found.append((start, n))
            i = start + max(n, 1) * MON_SIZE
            continue
        i += 4
    return found


class Gen3Reader:
    """Lee equipo y medallas. Guarda las posiciones encontradas y las revalida en cada lectura."""

    def __init__(self, rpc):
        self.rpc = rpc
        self.rom = None
        self.party_addr = None
        self.sb1_ptr_addr = None
        self.last_scan = 0

    def reset(self):
        self.rpc.reset()
        self.rom = None
        self.party_addr = self.sb1_ptr_addr = None

    def _find_sb1(self, iwram, ewram):
        """gSaveBlock1Ptr: el puntero de IWRAM a un bloque con contador de equipo y un Pokémon válido.
        Esmeralda cambia SaveBlock1 de sitio al cambiar de mapa: se lee el puntero cada vez."""
        rom = self.rom
        for off in range(0, IWRAM_SIZE - 4, 4):
            p = struct.unpack_from("<I", iwram, off)[0]
            if EWRAM <= p < EWRAM + EWRAM_SIZE - rom.sb1_size:
                base = p - EWRAM
                cnt = ewram[base + rom.party_count_off]
                if 1 <= cnt <= 6 and raw_valid(ewram[base + rom.party_off:base + rom.party_off + MON_SIZE]):
                    return IWRAM + off, base
        return None, None

    def _scan(self):
        rom = self.rom
        for _ in range(3):    # si SaveBlock1 se mueve entre lecturas, se repite
            iwram = self.rpc.read(IWRAM, IWRAM_SIZE)
            ewram = self.rpc.read(EWRAM, EWRAM_SIZE)
            ptr_addr, sb1 = self._find_sb1(iwram, ewram)
            if ptr_addr is None or self.rpc.read(ptr_addr, 4) == iwram[ptr_addr - IWRAM:ptr_addr - IWRAM + 4]:
                break
        self.sb1_ptr_addr = ptr_addr
        parties = find_parties(ewram)
        # El equipo en vivo (gPlayerParty) es un bloque que no está dentro de SaveBlock1 (allí solo
        # hay la copia de la última partida guardada). El equipo rival (gEnemyParty) va justo
        # 6 Pokémon antes y se queda en memoria después del combate: se descarta.
        live = {s for s, n in parties if sb1 is None or not (sb1 <= s < sb1 + rom.sb1_size)}
        live -= {s for s in live if s + 6 * MON_SIZE in live}
        if live:
            best = min(live)
        elif sb1 is not None:
            best = sb1 + rom.party_off       # sin equipo en vivo localizado: el último guardado
        else:
            best = None
        self.party_addr = EWRAM + best if best is not None else None
        self.last_scan = time.time()

    def read_state(self):
        if self.rom is None:
            self.rom = RomInfo(self.rpc)
        rom = self.rom
        if self.party_addr is None or time.time() - self.last_scan > 30:
            self._scan()
        party = []
        if self.party_addr:
            buf = self.rpc.read(self.party_addr, MON_SIZE * 6)
            for i in range(6):
                p = parse_mon(buf[i * MON_SIZE:(i + 1) * MON_SIZE], rom)
                if p:
                    party.append(p)
            if not party:
                self.party_addr = None          # cambió de sitio: se busca de nuevo
        badges = [False] * 8
        if self.sb1_ptr_addr:
            sb1 = struct.unpack("<I", self.rpc.read(self.sb1_ptr_addr, 4))[0]
            if EWRAM <= sb1 < EWRAM + EWRAM_SIZE:
                fl = self.rpc.read(sb1 + rom.flags_off + BADGE_FLAG // 8, 2)
                bits = fl[0] | fl[1] << 8
                badges = [bool(bits >> (BADGE_FLAG % 8 + i) & 1) for i in range(8)]
        name = detect_title(rom)
        return {"ok": True, "platform": "gba", "game_version": rom.expansion and "exp " + rom.expansion,
                "party": party, "badges": badges, "has_badges": name[0] not in NO_BADGES, "game": name[0], "game_name": name[1],
                "count": len(party), "valid_slots": len(party), "updated": time.time()}


def detect_title(rom):
    """(código corto, nombre) del juego: hacks conocidos por su huella, si no genérico."""
    if rom.fingerprint in KNOWN_HACKS:
        return KNOWN_HACKS[rom.fingerprint]
    return ("GBA", "Pokémon Esmeralda (hack)" if rom.code == "BPEE" else "Pokémon (GBA)")
