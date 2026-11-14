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

## Uso rápido (prototipo, requiere Python 3.8+)
1. Azahar: *Emulación → Configurar → Depuración → Activar servidor RPC* (antes de arrancar el juego).
2. Arranca el juego y carga tu partida.
3. `python omega_reader.py` (con `--probe` solo comprueba la conexión).
4. Se abre el panel (`http://localhost:8765/panel`): elige distribución y estilo, pulsa
   **Copiar URL** y pégala en OBS como *Fuente de navegador* con el tamaño que indica.

¿Sin emulador a mano? `python tests/demo_azahar.py` arranca todo con un Azahar simulado.

Más opciones en [LEEME.txt](LEEME.txt).

## Tests
Sin emulador ni partida: los tests usan un Azahar simulado (`tests/fake_azahar.py`)
que cifra Pokémon de ejemplo como el juego y responde al mismo protocolo RPC.

```
python -m unittest discover -s tests -v
```

Se ejecutan solos en GitHub Actions (Windows, Python 3.8 y 3.13) en cada push y PR.

## Recursos gráficos
Las medallas oficiales y los iconos de objetos **no están en este repositorio** (son de
Nintendo / Game Freak). El programa los descarga una vez a `%APPDATA%\OmegaOverlayssets`
desde fuentes públicas fijadas en [data/assets_manifest.json](data/assets_manifest.json)
(URL + SHA-256). Sin ellos usa medallas propias. `--sin-descargas` lo desactiva.
Ver [NOTICE.md](NOTICE.md).

## Licencia
Código bajo licencia [MIT](LICENSE).
