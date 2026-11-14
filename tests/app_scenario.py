"""Escenario de la ventana, ejecutado en un proceso aparte por test_app.py.

Tk no tolera que su intérprete se libere desde otro hilo (Python 3.8 aborta con
"Tcl_AsyncDelete"), así que la ventana se prueba aislada. Sale con 77 si no hay Tk.
"""
import os
import socket
import sys
import threading
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_azahar as F  # noqa: E402
from fake_azahar import R  # noqa: E402

try:
    import tkinter as tk
    probe = tk.Tk()
    probe.destroy()
except Exception:
    sys.exit(77)
import app  # noqa: E402


def check(cond, msg):
    if not cond:
        print("FALLO:", msg)
        sys.exit(1)


def main():
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        port = so.getsockname()[1]
    party = [F.make_pk6(257, 36, 100, 120, name="Pollo", game=27, pv=0x1000)]
    with F.FakeAzaharServer(F.oras_memory("1.0", party, badges=0b11)) as az:
        svc = R.Services(port=port, rpc_port=az.port, interval=0.1, download=False)
        svc.start()
        root = tk.Tk()
        root.withdraw()
        a = app.App(root, svc)
        for _ in range(50):
            root.update()
            with R.STATE_LOCK:
                if R.STATE.get("count"):
                    break
            threading.Event().wait(0.1)
        a.tick()
        check(a.rows["azahar"].value.cget("text") == "Conectado", "Azahar no aparece conectado")
        game = a.rows["game"].value.cget("text")
        check("Rubí Omega v1.0 · 1 Pokémon · 2 medallas" in game, "partida: %r" % game)
        check(not a.help.winfo_ismapped(), "la guía del RPC sigue visible")

        copied = []                       # sin tocar el portapapeles real
        root.clipboard_clear = lambda: None
        root.clipboard_append = copied.append
        a.copy_showdown()
        check(copied and "Blaziken" in copied[0], "paste de Showdown: %r" % copied)

        a.quit()                          # cerrar la ventana apaga el servidor
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/state.json" % port, timeout=1)
        check(False, "el servidor sigue respondiendo tras cerrar")
    except (urllib.error.URLError, ConnectionError):
        pass
    print("OK")
    sys.stdout.flush()
    os._exit(0)                           # sin recolectar Tk desde otro hilo al salir


if __name__ == "__main__":
    main()
