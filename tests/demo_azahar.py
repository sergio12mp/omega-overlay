"""Arranca el lector contra un Azahar simulado, para probar el panel y el overlay sin emulador.

    python tests/demo_azahar.py            -> panel en http://localhost:8765/panel
    python tests/demo_azahar.py --port 8770 --no-browser

El equipo simulado pierde y recupera vida cada pocos segundos para ver las animaciones.
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_azahar as F  # noqa: E402
from fake_azahar import R  # noqa: E402

TEAM = [  # especie, nivel, vida, máx, nombre, objeto, estado
    (257, 36, 112, 120, "Pollo", 251, 0),
    (277, 33, 52, 98, "Swellow", 237, 0),
    (282, 34, 18, 96, "Gardi", 0, 1),
    (306, 35, 0, 110, "Aggron", 321, 0),
    (310, 32, 90, 90, "Manectric", 0, 0),
    (319, 31, 70, 88, "Sharpedo", 0, 5),
]


def memory(tick):
    party = []
    for i, (sp, lv, hp, mx, nm, it, stt) in enumerate(TEAM):
        if i == 0:
            hp = max(1, mx - (tick * 17) % mx)  # el primero va perdiendo vida
        party.append(F.make_pk6(sp, lv, hp, mx, name=nm, item=it, status=stt, pv=0x1000 * (i + 1) + i))
    return F.oras_memory("1.4", party, badges=0b111)


def main():
    srv = F.FakeAzaharServer(memory(0))
    srv.__enter__()

    def animate():
        t = 0
        while True:
            time.sleep(3)
            t += 1
            srv.mem = memory(t)

    threading.Thread(target=animate, daemon=True).start()
    print("Azahar simulado en UDP %d" % srv.port)
    sys.argv = [sys.argv[0], "--rpc-port", str(srv.port)] + sys.argv[1:]
    R.main()


if __name__ == "__main__":
    main()
