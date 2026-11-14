/* Omega Overlay — núcleo compartido: opciones de URL, lectura del estado,
   tarjetas del equipo y medallas. Lo usan la escena completa y los widgets. */
(function () {
  "use strict";

  const Q = new URLSearchParams(location.search);
  const opt = (k, ok, def) => { const v = (Q.get(k) || "").toLowerCase(); return ok.includes(v) ? v : def; };

  const OPTIONS = {
    style: ["magma", "dex", "clasico", "cristal"],
    badges: ["placa", "plano", "escudo"],
    item: ["icono", "nombre", "ambos", "no"],
  };

  function applyOptions(body) {
    body.dataset.style = opt("style", OPTIONS.style, "magma");
    body.dataset.badges = opt("badges", OPTIONS.badges, "placa");
    body.dataset.item = opt("item", OPTIONS.item, "icono");
    if (Q.get("labels") === "0") body.classList.add("no-labels");
    // Sin la hoja de iconos (arte de terceros, se descarga aparte) se muestra el nombre del objeto
    const probe = new Image();
    probe.onerror = () => body.classList.add("no-itemsheet");
    probe.src = "/assets/itemicons-sheet.png";
    watchAssets();
  }

  /* Si el lector está descargando medallas e iconos, recarga una vez al terminar
     para que OBS los muestre sin tocar nada. */
  async function watchAssets() {
    if (!location.protocol.startsWith("http") || Q.has("noreload")) return;
    const get = async () => (await fetch("/assets/status.json", { cache: "no-store" })).json();
    try {
      const first = await get();
      if (first.complete) return;
      // Sigue mirando hasta que estén todos (la descarga puede lanzarse luego desde el panel)
      const t = setInterval(async () => {
        try {
          const st = await get();
          if (!st.job.running && st.present > first.present) { clearInterval(t); location.reload(); }
          else if (st.complete) clearInterval(t);
        } catch (e) { /* lector reiniciándose: se reintenta */ }
      }, 5000);
    } catch (e) { /* lector antiguo o sin conexión: nada que vigilar */ }
  }

  /* ---------------- Datos ---------------- */
  const SPRITES = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/";
  const BADGE_NAMES = ["Piedra", "Puño", "Dínamo", "Calor", "Equilibrio", "Pluma", "Mente", "Lluvia"];
  const BADGE_COLORS = ["#b8a07a", "#e0703a", "#f2d23a", "#ff5a2a", "#c9c9d6", "#7ad0ff", "#ff7ad9", "#3a8aff"];

  const DEMO = {
    ok: true, demo: true, game_version: "1.4", count: 6,
    badges: [true, true, true, false, false, false, false, false],
    party: [
      { species: 257, name: "Blaziken", level: 36, hp: 112, max_hp: 120, item_name: "Silk Scarf", item_icon: [288, 648] },
      { species: 277, name: "Swellow", level: 33, hp: 52, max_hp: 98, item_name: "Soft Sand", item_icon: [192, 672] },
      { species: 282, name: "Gardevoir", level: 34, hp: 18, max_hp: 96, status: "PAR" },
      { species: 306, name: "Aggron", level: 35, hp: 0, max_hp: 110, item_name: "Protector", item_icon: [360, 528] },
      { species: 310, name: "Manectric", level: 32, hp: 90, max_hp: 90, shiny: true },
      { species: 319, name: "Sharpedo", level: 31, hp: 70, max_hp: 88, status: "PSN" },
    ],
  };

  const isDemo = () => Q.has("demo") && Q.get("demo") !== "0";
  const BASE = location.protocol.startsWith("http") ? "" : "http://localhost:8765";

  /** Llama a onState(estado) cada segundo. Con ?demo usa un equipo de ejemplo. */
  function start(onState) {
    if (isDemo()) { onState(DEMO); return; }
    const tick = async () => {
      try {
        const r = await fetch(BASE + "/state.json", { cache: "no-store" });
        onState(await r.json());
      } catch (e) {
        onState({ ok: false, party: [], badges: [], error: "lector no disponible" });
      }
    };
    tick(); setInterval(tick, 1000);
  }

  /* ---------------- Equipo ---------------- */
  function makeCard() {
    const c = document.createElement("div");
    c.className = "card empty";
    c.innerHTML = '<div class="spr"><img alt=""><div class="itm"></div></div>' +
      '<div class="info"><div class="nm"></div><div class="lv"></div><div class="bar"><i></i></div>' +
      '<div class="hp"></div><div class="hn"></div></div><div class="st"></div>';
    return c;
  }

  function renderCard(c, p) {
    c.className = "card" + (p ? (p.hp <= 0 ? " ko" : "") : " empty");
    const $ = s => c.querySelector(s);
    const img = $("img"), bar = $(".bar i"), itm = $(".itm"), st = $(".st");
    if (!p) {
      img.removeAttribute("src"); img.dataset.u = "";
      ["nm", "lv", "hp", "hn"].forEach(k => { $("." + k).textContent = ""; });
      bar.style.width = "0"; itm.style.display = "none"; st.style.display = "none";
      return;
    }
    const url = SPRITES + (p.shiny ? "shiny/" : "") + p.species + ".png";
    if (img.dataset.u !== url) { img.dataset.u = url; img.src = url; }
    $(".nm").textContent = p.name || ("#" + p.species);
    $(".lv").textContent = "Nv. " + p.level;
    const pct = p.max_hp ? Math.max(0, Math.min(100, p.hp / p.max_hp * 100)) : 0;
    bar.style.width = pct + "%";
    bar.className = pct > 50 ? "" : pct > 20 ? "mid" : "low";
    $(".hp").textContent = p.hp + " / " + p.max_hp;
    if (p.item_icon) { itm.style.display = ""; itm.style.backgroundPosition = `-${p.item_icon[0]}px -${p.item_icon[1]}px`; }
    else itm.style.display = "none";
    $(".hn").textContent = p.item_name ? "@ " + p.item_name : "";
    st.style.display = p.status ? "block" : "none"; st.textContent = p.status || "";
  }

  /** Crea n tarjetas en `el` con una rejilla cols x rows. Devuelve render(party). */
  function team(el, { cols = 2, rows = 3, vertical = false, slots = null } = {}) {
    el.classList.add("team");
    el.classList.toggle("vert", vertical);
    el.style.gridTemplateColumns = `repeat(${cols},1fr)`;
    el.style.gridTemplateRows = `repeat(${rows},1fr)`;
    const idx = slots || Array.from({ length: cols * rows }, (_, i) => i);
    const cards = idx.map(() => el.appendChild(makeCard()));
    return party => cards.forEach((c, i) => renderCard(c, (party || [])[idx[i]]));
  }

  /* ---------------- Medallas ---------------- */
  function ownBadgeSvg(i) {
    // Medalla propia (sin arte de Nintendo): gema facetada con el número
    const col = BADGE_COLORS[i];
    return `<svg viewBox="0 0 48 48" width="46" height="46" aria-hidden="true">
      <polygon points="24,3 44,17 37,44 11,44 4,17" fill="${col}" stroke="#2a1008" stroke-width="2"/>
      <polygon points="24,3 24,24 44,17" fill="#fff" opacity=".28"/>
      <polygon points="24,24 37,44 11,44" fill="#000" opacity=".18"/>
      <text x="24" y="31" text-anchor="middle" font-size="17" font-weight="800" fill="#fff"
        stroke="#2a1008" stroke-width=".8" font-family="Trebuchet MS,sans-serif">${i + 1}</text></svg>`;
  }

  function badges(el, { cols = 4, rows = 2 } = {}) {
    el.classList.add("badges");
    el.style.gridTemplateColumns = `repeat(${cols},1fr)`;
    el.style.gridTemplateRows = `repeat(${rows},1fr)`;
    const items = BADGE_NAMES.map((name, i) => {
      const b = document.createElement("div");
      b.className = "badge off";
      b.innerHTML = `<div class="pl"><img src="/assets/badges/oras/${i + 1}.png" alt="${name}"></div><span>${name}</span>`;
      b.querySelector("img").onerror = function () { this.outerHTML = ownBadgeSvg(i); };
      return el.appendChild(b);
    });
    return got => items.forEach((b, i) => b.classList.toggle("off", !(got && got[i])));
  }

  /* ---------------- Estado ---------------- */
  function status(el) {
    el.classList.add("status");
    return st => {
      el.className = "status" + (st.ok ? "" : " bad");
      el.textContent = st.ok ? (st.demo ? "datos de ejemplo" : "") : (st.error || "sin conexión con Azahar");
    };
  }

  window.OO = { Q, opt, applyOptions, start, team, badges, status, DEMO, BADGE_NAMES };
})();
