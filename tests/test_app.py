"""Tests de la ventana de escritorio (se saltan si no hay pantalla para Tk)."""
import os
import socket
import sys
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_azahar as F  # noqa: E402
from fake_azahar import R  # noqa: E402
import app  # noqa: E402

try:
    import tkinter as tk
    _root = tk.Tk()
    _root.destroy()
    HAS_TK = True
except Exception:
    HAS_TK = False


def free_port():
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]


@unittest.skipUnless(HAS_TK, "sin pantalla para Tk")
class TestApp(unittest.TestCase):
    def test_status_and_close(self):
        port = free_port()
        party = [F.make_pk6(257, 36, 100, 120, name="Pollo", game=27, pv=0x1000)]
        with F.FakeAzaharServer(F.oras_memory("1.0", party, badges=0b11)) as az:
            svc = R.Services(port=port, rpc_port=az.port, interval=0.1, download=False)
            svc.start()
            root = tk.Tk()
            root.withdraw()
            a = app.App(root, svc)
            for _ in range(50):          # espera a que el lector lea el equipo
                root.update()
                with R.STATE_LOCK:
                    if R.STATE.get("count"):
                        break
                threading.Event().wait(0.1)
            a.tick()
            self.assertEqual(a.rows["azahar"].value.cget("text"), "Conectado")
            self.assertIn("Rubí Omega v1.0 · 1 Pokémon · 2 medallas", a.rows["game"].value.cget("text"))
            self.assertFalse(a.help.winfo_ismapped())

            copied = []                  # sin tocar el portapapeles real
            root.clipboard_clear = lambda: None
            root.clipboard_append = copied.append
            a.copy_showdown()
            self.assertIn("Blaziken", copied[0])

            a.quit()                     # cerrar la ventana apaga el servidor
        with self.assertRaises((urllib.error.URLError, ConnectionError)):
            urllib.request.urlopen("http://127.0.0.1:%d/state.json" % port, timeout=1)


if __name__ == "__main__":
    unittest.main()
