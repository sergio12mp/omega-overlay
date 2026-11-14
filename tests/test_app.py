"""Test de la ventana de escritorio. Corre app_scenario.py en un proceso aparte
(Tk no se lleva bien con los hilos del servidor al liberarse)."""
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class TestApp(unittest.TestCase):
    def test_status_copy_and_close(self):
        r = subprocess.run([sys.executable, os.path.join(HERE, "app_scenario.py")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if r.returncode == 77:
            self.skipTest("sin pantalla para Tk")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
