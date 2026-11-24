"""Juegos de GBA (pokeemerald-expansion) a través de mGBA, con memoria simulada."""
import os
import sys
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fake_gba as FG  # noqa: E402
from fake_azahar import MemoryRpc, R  # noqa: E402

G = FG.G


def team():
    return [FG.make_pk3(2, 31, 88, 92, nick="Cobra", item=7, moves=(40, 44, 0, 0), pid=0x0000_1001, ability_num=1,
                        evs=(4, 252, 0, 252, 0, 0)),
            FG.make_pk3(3, 30, 0, 90, item=9, moves=(51, 900, 0, 0), pid=0x0000_2002, status=0x40),
            FG.make_pk3(4, 29, 70, 70, nick="Garra", pid=0x0000_3003, ivs=(31, 31, 31, 31, 0, 31))]


class TestText(unittest.TestCase):
    def test_spanish_characters(self):
        self.assertEqual(G.decode_text(FG.enc("Máster Ball ¡ñ!")), "Máster Ball ¡ñ!")

    def test_stops_at_terminator(self):
        self.assertEqual(G.decode_text(FG.enc("Arbok") + b"\xbb\xbb"), "Arbok")


class TestRomInfo(unittest.TestCase):
    def setUp(self):
        self.rom = G.RomInfo(MemoryRpc(FG.gba_memory(team())))

    def test_header(self):
        self.assertEqual((self.rom.code, self.rom.expansion), ("BPEE", "1.14.4"))
        self.assertEqual((self.rom.flags_off, self.rom.party_off), (FG.FLAGS_OFF, FG.PARTY_OFF))

    def test_tables(self):
        self.assertEqual(self.rom.species(2)[:2], (24, "Arbok"))
        self.assertEqual(self.rom.item_name(7), "Restos")
        self.assertEqual(self.rom.move_name(40), "Picotazo Veneno")
        self.assertIsNone(self.rom.item_name(0))

    def test_rejects_vanilla_rom(self):
        mem = FG.gba_memory(team())
        mem.write(G.ROM + 0x1FC, b"\0" * 12)
        with self.assertRaises(G.RpcError):
            G.RomInfo(MemoryRpc(mem))


class TestPk3(unittest.TestCase):
    def test_decrypt_and_parse(self):
        rom = G.RomInfo(MemoryRpc(FG.gba_memory(team())))
        p = G.parse_mon(team()[0], rom)
        self.assertEqual((p["species"], p["species_id"], p["species_name"], p["name"]), (24, 2, "Arbok", "Cobra"))
        self.assertEqual((p["level"], p["hp"], p["max_hp"]), (31, 88, 92))
        self.assertEqual(p["item_name"], "Restos")
        self.assertEqual(p["move_names"], ["Picotazo Veneno", "Mordisco"])
        self.assertEqual(p["ability_id"], 61)      # habilidad 1 de la especie
        self.assertEqual(p["evs"]["Atk"], 252)

    def test_bad_checksum_is_rejected(self):
        mon = bytearray(team()[0])
        mon[40] ^= 0xFF
        self.assertFalse(G.raw_valid(bytes(mon)))

    def test_twelve_letter_nickname(self):
        rom = G.RomInfo(MemoryRpc(FG.gba_memory(team())))
        mon = FG.make_pk3(1, 5, 20, 20, nick="Bulbasaurito")
        self.assertEqual(G.parse_mon(mon, rom)["name"], "Bulbasaurito")


class TestReader(unittest.TestCase):
    def test_reads_party_and_badges(self):
        r = G.Gen3Reader(MemoryRpc(FG.gba_memory(team(), badges=0b101)))
        st = r.read_state()
        self.assertEqual(st["platform"], "gba")
        self.assertEqual([p["name"] for p in st["party"]], ["Cobra", "Weezing", "Garra"])
        self.assertEqual(st["party"][1]["status"], "PAR")
        self.assertEqual(st["badges"][:4], [True, False, True, False])
        self.assertEqual(st["game_name"], "Pokémon Esmeralda (hack)")

    def test_prefers_live_party_over_saved_copy(self):
        # la copia de SaveBlock1 es la de la última vez que se guardó: el equipo en vivo manda
        live = team()
        saved = [FG.make_pk3(1, 5, 20, 20, nick="Viejo", pid=0x9009)]
        r = G.Gen3Reader(MemoryRpc(FG.gba_memory(live, saved_party=saved)))
        self.assertEqual(r.read_state()["party"][0]["name"], "Cobra")

    def test_follows_party_changes(self):
        mem = FG.gba_memory(team())
        r = G.Gen3Reader(MemoryRpc(mem))
        r.read_state()
        hurt = FG.make_pk3(2, 31, 10, 92, nick="Cobra", item=7, moves=(40, 44, 0, 0), pid=0x0000_1001, ability_num=1)
        mem.write(G.EWRAM + 0x0244EC, hurt)
        self.assertEqual(r.read_state()["party"][0]["hp"], 10)

    def test_showdown_paste(self):
        st = G.Gen3Reader(MemoryRpc(FG.gba_memory(team()))).read_state()
        txt = R.showdown_paste(st["party"])
        self.assertIn("Cobra (Arbok) @ Restos", txt)
        self.assertIn("- Poison Sting", txt)          # movimiento con número oficial -> inglés
        self.assertIn("- Movimiento Nuevo", txt)      # sin traducción: el nombre de la ROM
        self.assertIn("EVs: 4 HP / 252 Atk / 252 Spe", txt)
        self.assertIn("Garra (Sneasler)", txt)        # especie sin traducción: el nombre de la ROM


class TestMgbaBridge(unittest.TestCase):
    def test_reads_over_tcp(self):
        with FG.FakeMgbaServer(FG.gba_memory(team())) as srv:
            with G.MgbaRpc(port=srv.port, timeout=1) as rpc:
                self.assertEqual(rpc.read(G.ROM + 0xAC, 4), b"BPEE")
                self.assertEqual(len(rpc.read(G.EWRAM, G.EWRAM_SIZE)), G.EWRAM_SIZE)   # en trozos

    def test_no_script_loaded(self):
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        with G.MgbaRpc(port=port, timeout=0.3) as rpc:
            with self.assertRaises(G.RpcError):
                rpc.read(G.ROM, 4)

    def test_reader_loop_switches_to_mgba(self):
        stop = threading.Event()
        az_port = 1   # nadie escucha: Azahar no está
        with FG.FakeMgbaServer(FG.gba_memory(team(), badges=1)) as srv:
            sources = [R.OrasSource(R.AzaharRpc(port=az_port, timeout=0.1)),
                       R.Gen3Source(G.MgbaRpc(port=srv.port, timeout=1))]
            t = threading.Thread(target=R.reader_loop, args=(sources, 0.05, False, stop), daemon=True)
            t.start()
            try:
                for _ in range(100):
                    with R.STATE_LOCK:
                        if R.STATE.get("count"):
                            break
                    threading.Event().wait(0.05)
                with R.STATE_LOCK:
                    st = dict(R.STATE)
            finally:
                stop.set()
                t.join(3)
        self.assertEqual((st["platform"], st["count"], sum(st["badges"])), ("gba", 3, 1))
        self.assertIn("Arbok", st["showdown"])


if __name__ == "__main__":
    unittest.main()
