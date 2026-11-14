"""Genera build/icon.ico (icono propio: cuadrado redondeado naranja con un anillo y una
barra de vida). Solo librería estándar; se ejecuta una vez y el .ico se guarda en el repo."""
import math
import os
import struct
import zlib


def pixel(x, y, n):
    s = n / 256.0
    cx = cy = n / 2
    r = 52 * s                                   # radio de las esquinas
    # dentro del cuadrado redondeado
    dx = max(abs(x - cx) - (n / 2 - r), 0)
    dy = max(abs(y - cy) - (n / 2 - r), 0)
    if math.hypot(dx, dy) > r:
        return (0, 0, 0, 0)
    t = y / n                                    # degradado vertical naranja -> granate
    bg = (int(255 - 120 * t), int(122 - 90 * t), int(42 - 10 * t), 255)
    d = math.hypot(x - cx, y - 104 * s)
    if 44 * s <= d <= 70 * s:                    # anillo blanco
        return (255, 244, 230, 255)
    if 192 * s <= y <= 212 * s and 60 * s <= x <= 196 * s:   # barra de vida
        return (55, 214, 122, 255) if x <= 150 * s else (40, 20, 20, 255)
    return bg


def png(n):
    raw = b"".join(b"\x00" + b"".join(bytes(pixel(x + .5, y + .5, n)) for x in range(n)) for y in range(n))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


sizes = [16, 32, 48, 256]
imgs = [png(n) for n in sizes]
out = struct.pack("<HHH", 0, 1, len(sizes))
off = 6 + 16 * len(sizes)
for n, im in zip(sizes, imgs):
    out += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(im), off)
    off += len(im)
here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "icon.ico"), "wb") as f:
    f.write(out + b"".join(imgs))
with open(os.path.join(here, "icon.png"), "wb") as f:
    f.write(imgs[-1])
print("icon.ico", off, "bytes")
