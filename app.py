"""Omega Overlay — aplicación de escritorio.

Arranca el lector y el servidor local y abre el panel en una ventana propia
(WebView2 de Windows, mediante pywebview): estado de Azahar, elección del diseño,
URL para OBS y equipo para Showdown, todo dentro de la app. Si WebView2 o pywebview
no están disponibles, se usa una ventana sencilla de Tkinter que abre el panel en
el navegador. Cerrar la ventana apaga el overlay.

    python app.py            (o el .exe empaquetado)
    OMEGA_UI=tk python app.py   fuerza la ventana sencilla
"""
import os
import sys
import tkinter as tk
import webbrowser

import omega_reader as R

VERSION = "0.2.1"

C = {  # colores
    "bg": "#15151c", "card": "#1f1f2a", "line": "#2f2f3d", "txt": "#ececf2", "dim": "#9a9aae",
    "acc": "#ff7a2a", "acc_dark": "#d9601a", "ok": "#37d67a", "warn": "#ffc23a", "bad": "#ff5a5a",
}
FONT = "Segoe UI"


def redirect_output_when_frozen():
    """En el .exe sin consola, guarda lo que el lector imprime en un archivo de registro."""
    if not R.FROZEN:
        return None
    os.makedirs(R.USER_DIR, exist_ok=True)
    path = os.path.join(R.USER_DIR, "omega_overlay.log")
    log = open(path, "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    return path


class StatusRow(tk.Frame):
    def __init__(self, master, label):
        super().__init__(master, bg=C["card"])
        self.dot = tk.Canvas(self, width=14, height=14, bg=C["card"], highlightthickness=0)
        self.oval = self.dot.create_oval(2, 2, 12, 12, fill=C["dim"], outline="")
        self.dot.pack(side="left", padx=(0, 10))
        tk.Label(self, text=label, bg=C["card"], fg=C["dim"], font=(FONT, 10), width=17,
                 anchor="w").pack(side="left")
        self.value = tk.Label(self, text="…", bg=C["card"], fg=C["txt"], font=(FONT, 10, "bold"),
                              anchor="w", justify="left", wraplength=290)
        self.value.pack(side="left", fill="x", expand=True)

    def set(self, color, text):
        self.dot.itemconfig(self.oval, fill=C[color])
        self.value.config(text=text)


class App:
    def __init__(self, root, svc):
        self.root, self.svc = root, svc
        self.connected_once = False
        root.title("Omega Overlay")
        ico = find_icon()
        if ico:
            try:
                root.iconbitmap(ico)
            except tk.TclError:
                pass
        root.configure(bg=C["bg"])
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.quit)

        head = tk.Frame(root, bg=C["bg"])
        head.pack(fill="x", padx=22, pady=(18, 4))
        tk.Label(head, text="Omega ", bg=C["bg"], fg=C["txt"], font=(FONT, 20, "bold")).pack(side="left")
        tk.Label(head, text="Overlay", bg=C["bg"], fg=C["acc"], font=(FONT, 20, "bold")).pack(side="left")
        tk.Label(root, text="Rubí Omega · Zafiro Alfa  ·  Azahar → OBS", bg=C["bg"], fg=C["dim"],
                 font=(FONT, 10)).pack(anchor="w", padx=22)

        card = tk.Frame(root, bg=C["card"], highlightbackground=C["line"], highlightthickness=1)
        card.pack(fill="x", padx=20, pady=14)
        inner = tk.Frame(card, bg=C["card"])
        inner.pack(fill="x", padx=16, pady=12)
        self.rows = {}
        for key, label in (("app", "Programa"), ("azahar", "Azahar"), ("game", "Partida"),
                           ("assets", "Medallas e iconos")):
            r = StatusRow(inner, label)
            r.pack(fill="x", pady=4)
            self.rows[key] = r

        # Guía para activar el RPC: visible mientras Azahar no conecte
        self.help = tk.Frame(root, bg="#2a1f10", highlightbackground="#5a4318", highlightthickness=1)
        tk.Label(self.help, text="Activa el servidor RPC de Azahar", bg="#2a1f10", fg=C["warn"],
                 font=(FONT, 11, "bold")).pack(anchor="w", padx=14, pady=(10, 4))
        steps = ("1.  En Azahar: Emulación → Configurar → Depuración.",
                 "2.  Marca «Activar servidor RPC» y acepta.",
                 "3.  Si el juego ya estaba abierto, ciérralo y vuelve a arrancarlo.",
                 "4.  Carga tu partida. Esta ventana se pondrá en verde sola.")
        for s in steps:
            tk.Label(self.help, text=s, bg="#2a1f10", fg=C["txt"], font=(FONT, 10), anchor="w",
                     justify="left").pack(anchor="w", padx=14)
        tk.Label(self.help, text="", bg="#2a1f10").pack(pady=2)

        btns = tk.Frame(root, bg=C["bg"])
        btns.pack(fill="x", padx=20, pady=(4, 6))
        self.btn_panel = self.button(btns, "Abrir panel para OBS", self.open_panel, primary=True)
        self.btn_panel.pack(fill="x", pady=4)
        row = tk.Frame(btns, bg=C["bg"])
        row.pack(fill="x")
        self.button(row, "Copiar equipo para Showdown", self.copy_showdown).pack(side="left", expand=True,
                                                                                   fill="x", padx=(0, 4))
        self.button(row, "Abrir carpeta de datos", self.open_folder).pack(side="left", expand=True,
                                                                           fill="x", padx=(4, 0))
        self.toast = tk.Label(root, text="", bg=C["bg"], fg=C["ok"], font=(FONT, 10, "bold"))
        self.toast.pack(pady=(2, 0))
        tk.Label(root, text="v%s · Cerrar esta ventana apaga el overlay" % VERSION, bg=C["bg"], fg=C["dim"],
                 font=(FONT, 9)).pack(pady=(2, 12))

        self.rows["app"].set("ok", "Funcionando en localhost:%d" % svc.port)
        self.tick()

    def button(self, parent, text, cmd, primary=False):
        bg = C["acc"] if primary else C["card"]
        fg = "#1b0b04" if primary else C["txt"]
        b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=C["acc_dark"] if primary
                      else C["line"], activeforeground=fg, relief="flat", bd=0, cursor="hand2",
                      font=(FONT, 11 if primary else 10, "bold" if primary else "normal"), pady=9 if primary else 7)
        return b

    # ---------------- acciones ----------------
    def open_panel(self):
        self.svc.open_panel()

    def open_folder(self):
        os.makedirs(R.USER_DIR, exist_ok=True)
        os.startfile(R.USER_DIR)  # noqa: S606 (Windows)

    def copy_showdown(self):
        with R.STATE_LOCK:
            txt = R.STATE.get("showdown", "")
        if not txt:
            self.flash("Aún no hay equipo leído de Azahar", bad=True)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(txt)
        self.flash("Equipo copiado. Impórtalo en Showdown.")

    def flash(self, msg, bad=False):
        self.toast.config(text=msg, fg=C["bad"] if bad else C["ok"])
        self.root.after(3000, lambda: self.toast.config(text=""))

    def quit(self):
        self.svc.stop()
        self.root.destroy()

    # ---------------- estado ----------------
    def tick(self):
        with R.STATE_LOCK:
            st = dict(R.STATE)
        party = st.get("party") or []
        if st.get("ok") and party:
            self.rows["azahar"].set("ok", "Conectado")
            game = st.get("game_name") or "Rubí Omega / Zafiro Alfa"
            self.rows["game"].set("ok", "%s v%s · %d Pokémon · %d medallas" % (
                game, st.get("game_version"), len(party), sum(st.get("badges") or [])))
            self.help.pack_forget()
            if not self.connected_once:
                self.connected_once = True
        elif st.get("ok"):
            self.rows["azahar"].set("ok", "Conectado")
            self.rows["game"].set("warn", "Carga tu partida en el juego")
            self.help.pack_forget()
        else:
            err = st.get("error") or "arrancando…"
            self.rows["azahar"].set("bad" if "sin respuesta" in err else "warn",
                                    "Sin conexión" if "sin respuesta" in err else err)
            self.rows["game"].set("warn", "Esperando a Azahar")
            if not self.help.winfo_ismapped():
                self.help.pack(fill="x", padx=20, pady=(0, 10), before=self.btn_panel.master)

        a = R.ASSETS.status()
        if a["complete"]:
            self.rows["assets"].set("ok", "Listos")
        elif a["job"]["running"]:
            self.rows["assets"].set("warn", "Descargando… %d de %d" % (a["job"]["done"], a["job"]["total"]))
        elif a["job"]["errors"]:
            self.rows["assets"].set("warn", "Sin conexión: se usan los propios (reintenta desde el panel)")
        else:
            self.rows["assets"].set("warn", "Faltan %d (se usan los propios)" % len(a["missing"]))
        self.root.after(1000, self.tick)


class AppApi:
    """Lo que el panel puede pedir a la app (window.pywebview.api.*).

    Solo atributos privados: pywebview expone al JavaScript todo lo público."""

    def __init__(self, svc):
        self._svc = svc

    def info(self):
        return {"version": VERSION, "port": self._svc.port, "data_dir": R.USER_DIR}

    def open_folder(self):
        os.makedirs(R.USER_DIR, exist_ok=True)
        os.startfile(R.USER_DIR)  # noqa: S606 (Windows)

    def open_browser(self):
        webbrowser.open(self._svc.panel_url)


def dark_title_bar(window):
    """Barra de título oscura en Windows 10/11 (si no se puede, se queda la normal)."""
    try:
        import ctypes
        hwnd = window.native.Handle.ToInt32()
        on = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (nuevo y antiguo)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
    except Exception:
        pass


def run_webview(svc):
    """Abre el panel en una ventana propia. Devuelve False si no hay WebView2/pywebview."""
    if os.environ.get("OMEGA_UI") == "tk":
        return False
    try:
        import webview
    except ImportError:
        print("pywebview no está instalado: se usa la ventana sencilla.")
        return False
    try:
        win = webview.create_window(
            "Omega Overlay", svc.panel_url + "?app=1", js_api=AppApi(svc), width=1340, height=900,
            min_size=(960, 640), background_color="#121218")
        win.events.shown += lambda: dark_title_bar(win)
        storage = os.path.join(R.USER_DIR, "webview")
        os.makedirs(storage, exist_ok=True)
        webview.start(gui="edgechromium" if os.name == "nt" else None, private_mode=False,
                      storage_path=storage, icon=find_icon())
        return True
    except Exception as e:  # sin el runtime de WebView2, por ejemplo
        print("No se pudo abrir la ventana integrada (%s): se usa la ventana sencilla." % e)
        return False


def find_icon():
    for ico in (os.path.join(R.RES_DIR, "icon.ico"), os.path.join(R.RES_DIR, "build", "icon.ico")):
        if os.path.isfile(ico):
            return ico
    return None


def already_open(port):
    msg = ("Omega Overlay ya está abierto (o hay otro programa usando el puerto %d).\n\n"
           "Busca su ventana en la barra de tareas." % port)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "Omega Overlay", 0x40)
    except Exception:
        print(msg)


def run_tk(svc):
    root = tk.Tk()
    App(root, svc)
    if not os.environ.get("OMEGA_NO_BROWSER"):
        svc.open_panel(delay=1.0)
    root.mainloop()


def main():
    redirect_output_when_frozen()
    port = int(os.environ.get("OMEGA_PORT", "8765"))
    svc = R.Services(port=port, rpc_port=int(os.environ.get("OMEGA_RPC_PORT", "45987")))
    try:
        svc.start()
    except R.PortInUse:
        already_open(port)
        return
    try:
        if not run_webview(svc):
            run_tk(svc)
    finally:
        svc.stop()


if __name__ == "__main__":
    main()
