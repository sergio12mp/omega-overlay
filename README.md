# Omega Overlay

Overlay automático para OBS que lee el **equipo, los objetos y las medallas** de
**Pokémon Rubí Omega / Zafiro Alfa** mientras juegas en el emulador **Azahar**.
Solo lee la memoria del juego; nunca escribe en ella.

> Estado: prototipo. Plan de desarrollo en [PLAN.md](PLAN.md).

## Qué hace
- Equipo de 6 con nivel, vida, estado y objeto equipado.
- Medallas conseguidas.
- **Panel de configuración** con vista previa en vivo: eliges, copias la URL y la pegas en OBS.
- **Escena completa** con 3 distribuciones (En L, Barra inferior, Columna lateral) o
  **piezas sueltas** (equipo en fila/columna/rejilla, medallas, un Pokémon por fuente).
- 4 estilos (`magma`, `dex`, `clasico`, `cristal`) y 3 fondos de medallas.
- Exporta el equipo en formato Pokémon Showdown con un clic.
- Detecta solo la versión del juego (1.0 o 1.4), también en ROMs randomizadas.

## Instalar (Windows)
1. Descarga `OmegaOverlay-X.Y.Z-instalador.exe` de la página de *Releases* (o el `.zip` portable).
2. Ejecútalo. No pide permisos de administrador.
   Windows puede avisar con SmartScreen porque el programa aún no está firmado:
   *Más información → Ejecutar de todas formas*.
3. Abre **Omega Overlay**. Todo se configura en su propia ventana: te dice si Azahar
   está conectado, te guía para activar el RPC y te da la URL para OBS.
   (Usa WebView2, que ya viene con Windows 10 y 11.)

Tus datos (recursos descargados, `equipo_showdown.txt`, `logo.png`, registro) van en
`%APPDATA%\OmegaOverlay` (botón «Carpeta de datos»).

## Desde el código (requiere Python 3.8+)
1. Azahar: *Emulación → Configurar → Depuración → Activar servidor RPC* (antes de arrancar el juego).
2. Arranca el juego y carga tu partida.
3. `pip install pywebview` y `python app.py` (la app con su ventana), o
   `python omega_reader.py` (solo consola; abre el panel en el navegador; `--probe` solo comprueba la conexión).
4. En el panel: elige distribución y estilo, pulsa **Copiar URL** y pégala en OBS como
   *Fuente de navegador* con el tamaño que indica.

¿Sin emulador a mano? `python tests/demo_azahar.py --app` abre la app con un Azahar simulado
(sin `--app`, solo el panel en el navegador).

Más opciones en [LEEME.txt](LEEME.txt).

## Compilar el .exe y el instalador
```
powershell -ExecutionPolicy Bypass -File builduild.ps1
```
Crea `dist\OmegaOverlay\OmegaOverlay.exe` y, si tienes Inno Setup 6, el instalador.
Al subir una etiqueta `vX.Y.Z` (igual a `VERSION` en `app.py`), GitHub Actions compila y
publica el instalador y el zip en *Releases*.

## Tests
Sin emulador ni partida: los tests usan un Azahar simulado (`tests/fake_azahar.py`)
que cifra Pokémon de ejemplo como el juego y responde al mismo protocolo RPC.

```
python -m unittest discover -s tests -v
```

Se ejecutan solos en GitHub Actions (Windows, Python 3.8 y 3.13) en cada push y PR.

## Recursos gráficos
Las medallas oficiales y los iconos de objetos **no están en este repositorio** (son de
Nintendo / Game Freak). El programa los descarga una vez a `%APPDATA%\OmegaOverlay\assets`
desde fuentes públicas fijadas en [data/assets_manifest.json](data/assets_manifest.json)
(URL + SHA-256). Sin ellos usa medallas propias. `--sin-descargas` lo desactiva.
Ver [NOTICE.md](NOTICE.md).

## Licencia
Código bajo licencia [MIT](LICENSE).
