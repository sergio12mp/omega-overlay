# Omega Overlay

Overlay automático para OBS que lee el **equipo, los objetos y las medallas** de
**Pokémon Rubí Omega / Zafiro Alfa** mientras juegas en el emulador **Azahar**.
Solo lee la memoria del juego; nunca escribe en ella.

> Estado: prototipo. Plan de desarrollo en [PLAN.md](PLAN.md).

## Qué hace
- Equipo de 6 con nivel, vida, estado y objeto equipado.
- Medallas conseguidas.
- 4 estilos de overlay (`magma`, `dex`, `clasico`, `cristal`).
- Exporta el equipo en formato Pokémon Showdown con un clic.
- Detecta solo la versión del juego (1.0 o 1.4), también en ROMs randomizadas.

## Uso rápido (prototipo, requiere Python 3.8+)
1. Azahar: *Emulación → Configurar → Depuración → Activar servidor RPC* (antes de arrancar el juego).
2. Arranca el juego y carga tu partida.
3. `python omega_reader.py --probe` para comprobar la conexión; `python omega_reader.py` para dejarlo funcionando.
4. OBS: *Fuente de navegador* → `http://localhost:8765/` → 1920 × 1080.

Más opciones en [LEEME.txt](LEEME.txt).

## Recursos gráficos
Las medallas oficiales y los iconos de objetos **no están en este repositorio** (son de
Nintendo / Game Freak). Ver [NOTICE.md](NOTICE.md).

## Licencia
Código bajo licencia [MIT](LICENSE).
