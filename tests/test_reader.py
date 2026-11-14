"""Tests del lector contra un Azahar simulado (sin emulador ni partida real)."""
import json
import os
import sys
import unittest
import urllib.error
import urllib.request
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_azahar as F  # noqa: E402
from fake_azahar import R  # noqa: E402


def team():
    """Equipo de ejemplo: 3 Pokémon con los objetos vistos en la partida real."""
    return [
        F.make_pk6(257, 36, 100, 120, name="Blaziken", item=251, pv=0x00000000),
        F.make_pk6(28, 30, 0, 90, name="Sandslash", item=237, pv=0x0000A000, status=0),
        F.make_pk6(112, 42, 60, 150, name="Rhydon", item=321, pv=0xFFFFFFFF, status=5,
                   gender="F"),
    ]


class TestPk6(unittest.TestCase):
    def test_encrypt_decrypt_roundtrip_all_shuffles(self):
        # 24 órdenes de bloques posibles: todos deben volver al original
        for sv in range(24):
            pv = sv << 13
            plain = F.make_pk6(25, 10, 20, 30, name="Pika", pv=pv)
            self.assertEqual(R.decrypt_pk6(F.encrypt_pk6(plain)), plain, "sv=%d" % sv)

    def test_parse_basic_fields(self):
        p = R.parse_pokemon(F.make_pk6(257, 36, 100, 120, name="Blaziken", item=251,
                                       status=1, gender="F"))
        self.assertEqual((p["species"], p["level"], p["hp"], p["max_hp"]), (257, 36, 100, 120))
        self.assertEqual(p["name"], "Blaziken")
        self.assertEqual(p["status"], "PAR")
        self.assertEqual(p["gender"], "F")
        self.assertEqual(p["item"], 251)
        self.assertEqual(p["item_name"], "Silk Scarf")
        self.assertEqual(p["item_icon"], [288, 648])

    def test_parse_rejects_garbage(self):
        self.assertIsNone(R.parse_pokemon(bytes(F.PK6_SIZE)))                     # vacío
        self.assertIsNone(R.parse_pokemon(F.make_pk6(722, 5, 10, 10)))           # especie > Gen 6
        self.assertIsNone(R.parse_pokemon(F.make_pk6(25, 101, 10, 10)))          # nivel imposible
        self.assertIsNone(R.parse_pokemon(F.make_pk6(25, 5, 20, 10)))            # vida > máxima

    def test_shiny(self):
        # shiny si (tid ^ sid ^ pid_alto ^ pid_bajo) < 16
        p = R.parse_pokemon(F.make_pk6(25, 5, 10, 10, tid=0x1234, sid=0, pid=0x00001234))
        self.assertTrue(p["shiny"])
        p = R.parse_pokemon(F.make_pk6(25, 5, 10, 10, tid=0x1234, sid=0, pid=0x00FF1234))
        self.assertFalse(p["shiny"])


class TestReadState(unittest.TestCase):
    def read(self, mem):
        return R.read_state(F.MemoryRpc(mem), None)

    def test_detects_version_14(self):
        st, ver = self.read(F.oras_memory("1.4", team(), badges=0b111))
        self.assertEqual(ver, "1.4")
        self.assertEqual([p["species"] for p in st["party"]], [257, 28, 112])
        self.assertEqual(st["count"], 3)

    def test_detects_version_10(self):
        st, ver = self.read(F.oras_memory("1.0", team()))
        self.assertEqual(ver, "1.0")
        self.assertEqual(st["count"], 3)

    def test_badges_bits(self):
        st, _ = self.read(F.oras_memory("1.4", team(), badges=0b00000111))
        self.assertEqual(st["badges"], [True, True, True] + [False] * 5)
        st, _ = self.read(F.oras_memory("1.4", team(), badges=0xFF))
        self.assertEqual(sum(st["badges"]), 8)

    def test_items(self):
        st, _ = self.read(F.oras_memory("1.4", team()))
        self.assertEqual([p["item_name"] for p in st["party"]], ["Silk Scarf", "Soft Sand", "Protector"])

    def test_party_order_from_index(self):
        st, _ = self.read(F.oras_memory("1.4", team(), order=[2, 0, 1]))
        self.assertEqual([p["species"] for p in st["party"]], [112, 257, 28])

    def test_full_party_of_six(self):
        party = [F.make_pk6(sp, 50, 100, 100, name="P%d" % sp, pv=sp * 0x1111)
                 for sp in (1, 4, 7, 25, 150, 384)]
        st, ver = self.read(F.oras_memory("1.0", party, order=[5, 4, 3, 2, 1, 0]))
        self.assertEqual(ver, "1.0")
        self.assertEqual([p["species"] for p in st["party"]], [384, 150, 25, 7, 4, 1])

    def test_no_game_loaded(self):
        st, ver = self.read(F.FakeMemory())
        self.assertIsNone(ver)
        self.assertEqual(st["party"], [])
        self.assertTrue(st["ok"])

    def test_keeps_known_version(self):
        mem = F.oras_memory("1.0", team())
        st, ver = R.read_state(F.MemoryRpc(mem), "1.0")
        self.assertEqual(ver, "1.0")


class TestGameDetection(unittest.TestCase):
    def party(self, *games):
        return [R.parse_pokemon(F.make_pk6(25, 5, 10, 10, name="P", game=g)) for g in games]

    def test_species_name_and_origin(self):
        p = R.parse_pokemon(F.make_pk6(282, 34, 18, 96, name="Gardi", game=26))
        self.assertEqual((p["name"], p["species_name"], p["origin_game"]), ("Gardi", "Gardevoir", 26))

    def test_majority(self):
        self.assertEqual(R.detect_game(self.party(27, 27, 26)), 27)
        self.assertEqual(R.detect_game(self.party(26, 26, 24, 27)), 26)

    def test_other_games_do_not_vote(self):
        # X/Y (24/25) y juegos antiguos no cuentan: un Pokémon de ORAS basta
        self.assertEqual(R.detect_game(self.party(24, 25, 25, 26)), 26)

    def test_unknown(self):
        self.assertIsNone(R.detect_game(self.party(24, 25)))
        self.assertIsNone(R.detect_game(self.party(26, 27)))      # empate
        self.assertIsNone(R.detect_game([]))

    def test_state_has_game(self):
        party = [F.make_pk6(257, 36, 100, 120, name="A", game=26, pv=0x1000),
                 F.make_pk6(28, 30, 50, 90, name="B", game=26, pv=0x2000)]
        st, _ = R.read_state(F.MemoryRpc(F.oras_memory("1.4", party)), None)
        self.assertEqual((st["game"], st["game_name"]), ("AS", "Zafiro Alfa"))
        st, _ = R.read_state(F.MemoryRpc(F.FakeMemory()), None)
        self.assertIsNone(st["game"])


class TestShowdown(unittest.TestCase):
    def test_paste(self):
        p = R.parse_pokemon(F.make_pk6(
            257, 50, 150, 150, name="Pollo", item=251, nature=3, ability=66, gender="M",
            moves=(53, 0, 0, 0), evs=(4, 252, 0, 252, 0, 0), ivs=(31, 31, 31, 31, 0, 31),
            nicknamed=True))
        txt = R.showdown_paste([p])
        self.assertEqual(txt, (
            "Pollo (Blaziken) (M) @ Silk Scarf\n"
            "Ability: Blaze\n"
            "Level: 50\n"
            "EVs: 4 HP / 252 Atk / 252 Spe\n"
            "Adamant Nature\n"
            "IVs: 0 SpA\n"
            "- Flamethrower\n"))

    def test_empty(self):
        self.assertEqual(R.showdown_paste([]), "")


class TestRpcProtocol(unittest.TestCase):
    def test_reads_over_udp(self):
        mem = F.oras_memory("1.4", team(), badges=0b11)
        with F.FakeAzaharServer(mem) as srv:
            with R.AzaharRpc(port=srv.port, timeout=0.5) as rpc:
                st, ver = R.read_state(rpc, None)
        self.assertEqual(ver, "1.4")
        self.assertEqual(st["count"], 3)
        self.assertEqual(sum(st["badges"]), 2)

    def test_falls_back_to_citra_protocol(self):
        mem = F.oras_memory("1.4", team())
        with F.FakeAzaharServer(mem, accept_versions=(1,)) as srv:
            with R.AzaharRpc(port=srv.port, timeout=0.3) as rpc:
                rpc.read(0x8000000, 4)
            self.assertEqual(rpc.req_version, 1)

    def test_large_reads_are_chunked(self):
        mem = F.FakeMemory()
        mem.write(0x1000, bytes(range(256)) * 40)  # 10 240 bytes
        with F.FakeAzaharServer(mem, max_chunk=4096) as srv:
            with R.AzaharRpc(port=srv.port, timeout=0.5) as rpc:
                self.assertEqual(rpc.read(0x1000, 10240), bytes(range(256)) * 40)

    def test_no_server_raises(self):
        with F.FakeAzaharServer(F.FakeMemory(), accept_versions=()) as srv:
            with R.AzaharRpc(port=srv.port, timeout=0.2) as rpc:
                with self.assertRaises(R.RpcError):
                    rpc.read(0x8000000, 4)


class TestHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = R.Server(("127.0.0.1", 0), R.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def get(self, path):
        return urllib.request.urlopen("http://127.0.0.1:%d%s" % (self.port, path), timeout=2)

    def test_state_json(self):
        st, _ = R.read_state(F.MemoryRpc(F.oras_memory("1.4", team())), None)
        with R.STATE_LOCK:
            R.STATE.clear()
            R.STATE.update(st)
        with self.get("/state.json") as r:
            data = json.loads(r.read())
            self.assertEqual(r.headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(data["count"], 3)

    def test_overlay_served(self):
        with self.get("/?style=dex") as r:
            self.assertIn(b"escena", r.read().lower())

    def test_pages(self):
        for path, marker in (("/panel", b"Elige la distribuci"), ("/widget?tipo=medallas-fila", b"widget"),
                             ("/overlay/core.js", b"window.OO"), ("/overlay/layouts.js", b"OOLayouts"),
                             ("/overlay/theme.css", b".card")):
            with self.get(path) as r:
                self.assertIn(marker, r.read(), path)

    def test_styles_redirects_to_panel(self):
        with self.get("/styles") as r:
            self.assertTrue(r.geturl().endswith("/panel"))

    def test_source_not_served(self):
        for path in ("/omega_reader.py", "/pokedata.json", "/../LICENSE"):
            with self.assertRaises(urllib.error.HTTPError, msg=path):
                self.get(path)


class TestServices(unittest.TestCase):
    def free_port(self):
        import socket
        with socket.socket() as so:
            so.bind(("127.0.0.1", 0))
            return so.getsockname()[1]

    def test_start_stop_and_port_in_use(self):
        port = self.free_port()
        with F.FakeAzaharServer(F.oras_memory("1.4", team())) as az:
            a = R.Services(port=port, rpc_port=az.port, interval=0.1, download=False)
            a.start()
            try:
                b = R.Services(port=port, rpc_port=az.port, download=False)
                with self.assertRaises(R.PortInUse):
                    b.start()
                for _ in range(50):
                    with urllib.request.urlopen("http://127.0.0.1:%d/state.json" % port, timeout=2) as r:
                        st = json.loads(r.read())
                    if st.get("count"):
                        break
                    threading.Event().wait(0.1)
                self.assertEqual(st["count"], 3)
            finally:
                a.stop()


if __name__ == "__main__":
    unittest.main()
