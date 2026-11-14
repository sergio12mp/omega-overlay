# Plan — Omega Overlay (Azahar → OBS), distribución gratuita

Alcance actual: **Rubí Omega / Zafiro Alfa** (v1.0 y v1.4) en **Azahar**, Windows, español.
Diseño pensado para añadir juegos después sin rehacer el lector (XY, SL, USUM).

## 0. Decisiones que fija este plan

| Tema | Decisión | Motivo |
|---|---|---|
| Licencia del código | **MIT** | Gratuita, compatible con el código de Readek (MIT); permite donaciones |
| Repositorio | `omega-overlay` en GitHub (cuenta `sergio12mp`), **privado hasta la release 0.1**, público después | Evita publicar antes de limpiar recursos con copyright |
| Arte de Nintendo (medallas, iconos de objetos, sprites) | **Nunca en el repo ni en el instalador.** Se descarga en el primer arranque a una caché local (`%APPDATA%\OmegaOverlay\assets`) | Riesgo legal "Alto" del resumen |
| Pokélink | **No se reutiliza nada** (ni temas ni iconos) | Programa cerrado sin licencia; copiar su arte no es redistribuible. Solo lo usamos como referencia de qué ofrece |
| Pokemon Stream Tool (Readek) | Código MIT: se puede reutilizar citando el copyright. Su arte viene de Showdown/Nintendo → se descarga, no se copia | LICENSE comprobado |
| PokeStreamer-Tools (EverOddish) | **Sin licencia → no se copia código.** Direcciones y descifrado se reimplementan desde la especificación PK6 de PKHeX | Todos los derechos reservados por defecto |
| Tema por defecto | Iconos propios (SVG dibujados para el proyecto) + temas "oficiales" opcionales que usan la caché descargada | El overlay funciona aunque falle la descarga |

## 1. Estructura del repositorio

```
omega-overlay/
├─ core/                 # lector sin interfaz (solo lectura)
│  ├─ rpc.py             # cliente UDP del RPC de Azahar
│  ├─ pk6.py             # descifrado y parseo PK6
│  ├─ games/oras.json    # direcciones por versión (1.0, 1.4) → ampliable a XY, SM…
│  ├─ detect.py          # autodetección de juego/versión por validez de datos
│  └─ showdown.py        # paste de Showdown
├─ server/               # HTTP local + /state.json + /showdown + /styles
├─ overlay/              # HTML/CSS/JS de OBS, un archivo por estilo
├─ app/                  # ventana de escritorio (estado RPC/juego/versión, copiar paste)
├─ assets_fetch/         # descargador de recursos de terceros + manifiesto con URLs y hash
├─ data/pokedata.json    # nombres (es/en) de especies, movimientos, objetos
├─ tests/                # RPC simulado + volcados PK6 de ejemplo
├─ build/                # spec de PyInstaller, script del instalador
└─ .github/workflows/    # tests en cada push, .exe en cada tag
```

`assets/badges/*.png` e `itemicons-sheet.png` actuales pasan a `.gitignore` y a la lista de descarga.

## 2. Fases

Cada fase acaba con una prueba concreta; no se pasa a la siguiente sin superarla.

### Fase 0 — Repositorio y base (1-2 días)
✅ Fase 0 completada.

1. `git init`, `.gitignore` (assets de terceros, `equipo_showdown.txt`, `logo.png`, builds), `LICENSE` (MIT), `README.md` y `NOTICE.md` (créditos: Readek MIT, PKHeX como referencia, aviso de marcas de Nintendo).
2. Subir el prototipo tal cual como primer commit (sin arte de Nintendo).
3. Crear el repo en GitHub (privado) y empujar `main`. Ramas por tarea, PR por cada cambio.
4. CI: GitHub Actions con `python -m unittest` en Windows.

**Prueba:** el repo clonado en limpio arranca `python omega_reader.py --probe` sin arte incluido.

### Fase 1 — Validar el prototipo con la partida real (1 semana)
1. Refactor mínimo a la estructura `core/ server/ overlay/` sin cambiar comportamiento.
2. ✅ Tests con RPC simulado: equipo, medallas, objetos, versión 1.0/1.4.
3. ✅ Descargador de recursos (`assets.py`): medallas ORAS e iconos de objetos desde el repositorio público de assets del Stream Tool / Showdown, con manifiesto (URL + SHA-256), reintentos y modo sin conexión.
4. ✅ Cotejar con el juego (14-11-2026, partida real v1.0): objetos (251, 237, 321), paste de Showdown frente a PKHeX, 3 medallas.
5. ✅ Ver el overlay con datos reales en OBS (equipo, objetos, medallas y paste correctos).

**Prueba:** captura de OBS con equipo, objetos y medallas correctos; paste importado en Showdown sin errores.

### Interfaz y distribuciones (hecho en `layouts-panel`)
Mezcla de lo mejor de Pokélink (una fuente de navegador por pieza, un Pokémon por fuente) y del
Stream Tool (escena completa con marco), con un panel que ninguno de los dos tiene:
- Panel web (`/panel`) con galería de distribuciones en miniatura, vista previa en vivo,
  equipo de ejemplo si Azahar no está conectado, botón Copiar URL e instrucciones de OBS con
  el tamaño exacto y la posición de la captura.
- Escena completa: En L, Barra inferior, Columna lateral (definidas en `overlay/layouts.js`).
- Piezas sueltas: 5 de equipo, 3 de medallas y Pokémon individual (n=1..6).
- Medallas propias en SVG cuando no está el arte oficial.
Pendiente: editor de distribución propia (arrastrar y soltar), guardar presets con nombre,
y nombres de especie en español (Fase 3).
Hecho: opción mote / especie / ambos y título automático según el juego detectado.

### Fase 2 — MVP distribuible (1-2 semanas) — en curso
1. ✅ Ventana de escritorio mínima (Tkinter, sin dependencias): semáforo RPC / juego / versión, URL de OBS con botón copiar, selector de estilo con vista previa, botón "Copiar paste de Showdown".
2. ✅ Guía en la ventana mientras Azahar no conecta (en vez de asistente aparte). Asistente de primer arranque: explica cómo activar el RPC en Azahar (Emulación → Configurar → Depuración) y comprueba la conexión.
3. Mensajes de error comprensibles (RPC apagado, juego no soportado, versión de Azahar desconocida).
4. ✅ PyInstaller `--onedir` (menos falsos positivos que `--onefile`) + instalador Inno Setup.
5. ✅ Release [`v0.1.0`](https://github.com/sergio12mp/omega-overlay/releases/tag/v0.1.0) en GitHub con instalador y zip portable generados por CI (14-11-2026). Pendiente: pasar el repo a público (decisión aplazada).

**Prueba:** una persona ajena instala en un PC sin Python y ve su equipo en OBS en menos de 10 minutos.

### Fase 3 — Completar ORAS (2-3 semanas)
1. Formas (Mega, Rotom, Deoxys…) desde el byte de forma del PK6.
2. Nombres en español de objetos, movimientos y especies.
3. Sprites de Pokémon en caché local (descarga única) para no depender de internet en directo.
4. Cajas del PC con dirección verificada.
5. Tabla de direcciones actualizable sin reinstalar (`games/oras.json` descargable).
6. Pruebas con 3 ROMs, incluidas randomizadas.

**Prueba:** equipo de 6 con formas correcto en overlay y paste.

### Fase 4 — Más juegos (cuando ORAS esté cerrado)
XY → Sol/Luna → USUM. Cada juego = un JSON de direcciones + tests; el núcleo no cambia. Nuzlocke (muertes) y temas de la comunidad.

### Fase 5 — Producto definitivo (solo si hay demanda)
Reescritura del núcleo en TypeScript con Tauri, instalador firmado, actualizaciones automáticas.

## 3. Flujo de trabajo con GitHub
- `main` siempre estable; una rama y un PR por tarea; CI obligatoria.
- Issues por fase con etiquetas `fase-1`, `oras`, `bug`, `assets`.
- Tags `vX.Y.Z` generan el `.exe` y la release automáticamente.

## 4. Pendiente de decidir por el autor
- Nombre definitivo del proyecto y del repo.
- Donaciones (Ko-fi / GitHub Sponsors) sí o no.
- Consulta legal antes de hacer público el repo con temas "oficiales".
