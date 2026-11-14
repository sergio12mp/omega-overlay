/* Omega Overlay — distribuciones (layouts) de la escena completa y de los widgets.
   Lo usan scene.html (para dibujar) y panel.html (para la galería y las medidas de OBS). */
(function () {
  "use strict";

  /* Geometría de la captura de Azahar (px de la captura ya recortada).
     Por defecto: la del autor (pantallas en "Grande" con la pequeña arriba a la derecha). */
  const CAPTURE = {
    capture: { w: 2558, h: 1281 },
    top:     { x: 0,    y: 161, w: 1866, h: 1120 },
    bottom:  { x: 1866, y: 0,   w: 692,  h: 520  },
  };

  /* ---------- Escena completa (1920 x 1080) ---------- */
  const SCENES = {
    ele: {
      name: "En L",
      desc: "El juego ocupa casi todo; equipo y medallas en el hueco bajo la pantalla pequeña.",
      place: { x: 30, y: 60, w: 1860 },
      zone: "ele", dir: "col", split: 0.62,
      team: { cols: 2, rows: 3 }, badges: { cols: 4, rows: 2 },
    },
    barra: {
      name: "Barra inferior",
      desc: "Juego arriba y una franja abajo con los 6 Pokémon en fila y las medallas.",
      area: { x: 20, y: 14, w: 1880, h: 836 },
      zone: { x: 20, y: 866, w: 1880, h: 198 }, dir: "row", split: 0.74,
      team: { cols: 6, rows: 1, vertical: true }, badges: { cols: 4, rows: 2 },
    },
    columna: {
      name: "Columna lateral",
      desc: "Juego a la izquierda y una columna a la derecha con el equipo en vertical.",
      area: { x: 16, y: 20, w: 1440, h: 1040 },
      zone: { x: 1476, y: 20, w: 428, h: 1040 }, dir: "col", split: 0.7,
      team: { cols: 1, rows: 6 }, badges: { cols: 4, rows: 2 },
    },
  };

  /** Dónde va la captura en el lienzo: {x, y, w, h, s}. */
  function placement(sceneKey, cap = CAPTURE) {
    const L = SCENES[sceneKey] || SCENES.ele;
    const C = cap.capture;
    let x, y, w;
    if (L.place) ({ x, y, w } = L.place);
    else {
      const s = Math.min(L.area.w / C.w, L.area.h / C.h);
      w = C.w * s; x = L.area.x + (L.area.w - w) / 2; y = L.area.y + (L.area.h - C.h * s) / 2;
    }
    const s = w / C.w;
    const r = v => Math.round(v);
    return { x: r(x), y: r(y), w: r(w), h: r(C.h * s), s };
  }

  /* ---------- Widgets sueltos (cada uno es una fuente de navegador) ---------- */
  const CARD_W = 300, CARD_H = 96, GAP = 6;
  const BADGE_W = 72, BADGE_H = 80;
  const WIDGETS = {
    "equipo-fila":    { w: "team", name: "Equipo en fila",     desc: "6 tarjetas en horizontal.",   cols: 6, rows: 1 },
    "equipo-columna": { w: "team", name: "Equipo en columna",  desc: "6 tarjetas en vertical.",     cols: 1, rows: 6 },
    "equipo-2x3":     { w: "team", name: "Equipo 2 × 3",       desc: "Dos columnas de tres.",       cols: 2, rows: 3 },
    "equipo-3x2":     { w: "team", name: "Equipo 3 × 2",       desc: "Tres columnas de dos.",       cols: 3, rows: 2 },
    "equipo-mini":    { w: "team", name: "Equipo compacto",    desc: "Tarjetas verticales en fila.", cols: 6, rows: 1, vertical: true },
    "medallas-fila":  { w: "badges", name: "Medallas en fila", desc: "Las 8 en una línea.",          cols: 8, rows: 1 },
    "medallas-4x2":   { w: "badges", name: "Medallas 4 × 2",   desc: "Dos filas de cuatro.",         cols: 4, rows: 2 },
    "medallas-columna": { w: "badges", name: "Medallas en columna", desc: "Las 8 en vertical.",      cols: 1, rows: 8 },
    "pokemon":        { w: "slot", name: "Un Pokémon",         desc: "Una sola tarjeta (elige 1-6). Ideal para colocar cada uno donde quieras.", cols: 1, rows: 1 },
  };

  /** Tamaño recomendado de la fuente de navegador en OBS para un widget. */
  function widgetSize(key) {
    const W = WIDGETS[key];
    if (!W) return { w: 0, h: 0 };
    if (W.w === "badges") return { w: W.cols * BADGE_W + (W.cols - 1) * 4, h: W.rows * BADGE_H + (W.rows - 1) * 4 };
    const cw = W.vertical ? 170 : CARD_W, ch = W.vertical ? 170 : CARD_H;
    return { w: W.cols * cw + (W.cols - 1) * GAP, h: W.rows * ch + (W.rows - 1) * GAP };
  }

  window.OOLayouts = { CAPTURE, SCENES, placement, WIDGETS, widgetSize };
})();
