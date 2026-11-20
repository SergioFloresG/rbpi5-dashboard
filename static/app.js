const $ = (id) => document.getElementById(id);
const REFRESCO_MS = 5 * 60 * 1000;
const REINTENTO_MS = 30 * 1000;
let zona = undefined;
let modoTema = "AUTO";
let sol = null;
const configuracion = fetch("/api/config").then((r) => r.json()).then((c) => {
  zona = c.zona;
  modoTema = c.tema || "AUTO";
  sol = c.sol;
  aplicarTema();
  return c;
});

function horaLocal() {
  return new Date().toLocaleTimeString("es-MX", { timeZone: zona, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
}

function aplicarTema() {
  let t = modoTema;
  if (t === "AUTO") {
    const hm = horaLocal();
    t = sol && hm >= sol.amanecer && hm < sol.anochecer ? "WHITE" : "BLACK";
  }
  const nombre = t === "WHITE" ? "claro" : "oscuro";
  if (document.documentElement.dataset.tema === nombre) return;
  document.documentElement.dataset.tema = nombre;
  window.dispatchEvent(new CustomEvent("tema", { detail: nombre }));
}

const WMO = {
  0: ["Despejado", "despejado"], 1: ["Mayormente despejado", "despejado"],
  2: ["Parcialmente nublado", "parcial"], 3: ["Nublado", "nublado"],
  45: ["Niebla", "niebla"], 48: ["Niebla con escarcha", "niebla"],
  51: ["Llovizna ligera", "lluvia"], 53: ["Llovizna", "lluvia"], 55: ["Llovizna intensa", "lluvia"],
  56: ["Llovizna helada", "lluvia"], 57: ["Llovizna helada", "lluvia"],
  61: ["Lluvia ligera", "lluvia"], 63: ["Lluvia", "lluvia"], 65: ["Lluvia intensa", "lluvia"],
  66: ["Lluvia helada", "lluvia"], 67: ["Lluvia helada", "lluvia"],
  71: ["Nieve ligera", "nieve"], 73: ["Nieve", "nieve"], 75: ["Nieve intensa", "nieve"], 77: ["Granizo fino", "nieve"],
  80: ["Chubascos", "lluvia"], 81: ["Chubascos", "lluvia"], 82: ["Chubascos fuertes", "tormenta"],
  85: ["Chubascos de nieve", "nieve"], 86: ["Chubascos de nieve", "nieve"],
  95: ["Tormenta", "tormenta"], 96: ["Tormenta con granizo", "tormenta"], 99: ["Tormenta con granizo", "tormenta"],
};

const NUBE = (y = 0, c = "var(--nube)") =>
  `<path transform="translate(0,${y})" style="fill:${c}" d="M-30,22 a16,16 0 0 1 2,-32 a22,22 0 0 1 42,-4 a14,14 0 0 1 16,14 a11,11 0 0 1 -2,22 Z"/>`;
const SOL = (x = 0, y = 0, r = 18) => {
  let rayos = "";
  for (let i = 0; i < 8; i++) {
    const a = (i * Math.PI) / 4;
    rayos += `<line x1="${x + Math.cos(a) * (r + 7)}" y1="${y + Math.sin(a) * (r + 7)}" x2="${x + Math.cos(a) * (r + 15)}" y2="${y + Math.sin(a) * (r + 15)}"/>`;
  }
  return `<g stroke="#fbbf24" stroke-width="5" stroke-linecap="round">${rayos}</g><circle cx="${x}" cy="${y}" r="${r}" fill="#fbbf24"/>`;
};
const LUNA = (x = 0, y = 0, r = 22) =>
  `<path style="fill:var(--luna-luz)" d="M${x + r * 0.3},${y - r} a${r},${r} 0 1 0 ${r * 0.7},${r * 1.55} a${r * 0.85},${r * 0.85} 0 0 1 ${-r * 0.7},${-r * 1.55} Z"/>`;

function iconoSVG(tipo, dia) {
  const astro = (x, y, r) => (dia ? SOL(x, y, r) : LUNA(x, y, r));
  const gotas = (c, forma) => [-16, 0, 16].map((x, i) =>
    forma === "nieve"
      ? `<circle cx="${x}" cy="${36 + (i % 2) * 8}" r="4" style="fill:${c}"/>`
      : `<line x1="${x}" y1="${32 + (i % 2) * 4}" x2="${x - 5}" y2="${44 + (i % 2) * 4}" style="stroke:${c}" stroke-width="5" stroke-linecap="round"/>`).join("");
  const cuerpo = {
    despejado: astro(0, 0, dia ? 24 : 34),
    parcial: astro(14, -14, 16) + NUBE(8),
    nublado: NUBE(0, "var(--nube-oscura)"),
    niebla: [-14, 0, 14, 28].map((y) => `<line x1="-34" x2="34" y1="${y}" y2="${y}" style="stroke:var(--nube-oscura)" stroke-width="6" stroke-linecap="round"/>`).join(""),
    lluvia: NUBE(-8) + gotas("#4ea8ff"),
    nieve: NUBE(-8) + gotas("var(--nube-oscura)", "nieve"),
    tormenta: NUBE(-10, "var(--nube-oscura)") + `<path fill="#facc15" d="M4,14 L-10,36 L0,36 L-6,54 L12,28 L2,28 Z"/>`,
  }[tipo] || NUBE();
  return `<svg viewBox="-50 -50 100 100" width="130" height="130">${cuerpo}</svg>`;
}
const PUNTOS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"];

function nivelUV(uv) {
  if (uv < 3) return [1, "Bajo"];
  if (uv < 6) return [2, "Moderado"];
  if (uv < 8) return [3, "Alto"];
  if (uv < 11) return [4, "Muy alto"];
  return [5, "Extremo"];
}
function nivelAQI(a) {
  if (a <= 50) return [1, "Buena"];
  if (a <= 100) return [2, "Moderada"];
  if (a <= 150) return [3, "Dañina p/ sensibles"];
  if (a <= 200) return [4, "Dañina"];
  if (a <= 300) return [5, "Muy dañina"];
  return [6, "Peligrosa"];
}
function faseLunar(c) {
  const f = [
    [0.033, "Luna nueva"], [0.216, "Creciente"], [0.284, "Cuarto creciente"],
    [0.466, "Gibosa creciente"], [0.534, "Luna llena"], [0.716, "Gibosa menguante"],
    [0.784, "Cuarto menguante"], [0.967, "Menguante"], [1.01, "Luna nueva"],
  ];
  return f.find(([lim]) => c < lim)[1];
}

function dibujarLuna(c) {
  const r = 44;
  const ilum = (1 - Math.cos(2 * Math.PI * c)) / 2;
  const creciente = c < 0.5;
  const rx = Math.abs(1 - 2 * ilum) * r;
  const lado = creciente ? 1 : 0;
  const barrido = ilum > 0.5 ? (creciente ? 0 : 1) : (creciente ? 1 : 0);
  const d = `M0,${-r} A${r},${r} 0 0 ${lado} 0,${r} A${rx},${r} 0 0 ${barrido} 0,${-r} Z`;
  $("luna").innerHTML =
    `<circle r="${r}" style="fill:var(--luna-sombra)"/>` +
    `<path d="${d}" style="fill:var(--luna-luz)"/>` +
    `<circle r="${r}" fill="none" style="stroke:var(--aro)" stroke-width="2"/>`;
  return Math.round(ilum * 100);
}

function setNivel(el, n) {
  el.className = el.className.replace(/\bnivel-\d\b/g, "").trim() + ` nivel-${n}`;
}

function reloj() {
  const ahora = new Date();
  const opt = { timeZone: zona };
  const hm = ahora.toLocaleTimeString("es-MX", { ...opt, hour: "2-digit", minute: "2-digit", hour12: false });
  const s = ahora.toLocaleTimeString("es-MX", { ...opt, second: "2-digit" }).padStart(2, "0");
  $("hora").innerHTML = `${hm}<span class="seg">${s.slice(-2)}</span>`;
  const f = ahora.toLocaleDateString("es-MX", { ...opt, weekday: "long", day: "numeric", month: "long", year: "numeric" });
  $("fecha").textContent = f.charAt(0).toUpperCase() + f.slice(1);
  aplicarTema();
}

let timerClima = null;
async function clima() {
  clearTimeout(timerClima);
  let espera = REFRESCO_MS;
  try {
    const r = await fetch("/api/clima");
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    zona = d.zona;
    const a = d.actual, h = d.hoy;

    const w = WMO[a.codigo] || ["—", "nublado"];
    $("icono").innerHTML = iconoSVG(w[1], a.es_dia);
    $("desc").textContent = `${w[0]} · ${d.ciudad}`;
    $("temp").textContent = `${Math.round(a.temp)}°`;
    $("maxmin").textContent = `Máx ${Math.round(h.max)}° · Mín ${Math.round(h.min)}°`;

    $("sensacion").innerHTML = `${Math.round(a.sensacion)}<small>°C</small>`;
    $("humedad").innerHTML = `${a.humedad}<small>%</small>`;
    $("humedad-barra").style.width = `${a.humedad}%`;

    $("viento").innerHTML = `${Math.round(a.viento)}<small>km/h</small>`;
    $("viento-sub").textContent = `${PUNTOS[Math.round(a.viento_dir / 45) % 8]} · ráfagas ${Math.round(a.rafagas)}`;
    $("flecha").setAttribute("transform", `rotate(${(a.viento_dir + 180) % 360})`);

    const [nu, tu] = nivelUV(a.uv);
    $("uv").textContent = a.uv.toFixed(1);
    setNivel($("uv"), nu);
    $("uv-sub").textContent = `${tu} · máx hoy ${h.uv_max.toFixed(1)}`;

    if (d.aire.aqi != null) {
      const [na, ta] = nivelAQI(d.aire.aqi);
      $("aqi").innerHTML = `${d.aire.aqi}<small>AQI</small>`;
      setNivel($("aqi"), na);
      $("aqi-sub").textContent = `${ta} · PM2.5 ${d.aire.pm2_5} µg/m³`;
    }

    $("visibilidad").innerHTML = `${a.visibilidad_km}<small>km</small>`;
    $("presion").innerHTML = `${Math.round(a.presion)}<small>hPa</small>`;
    $("amanecer").textContent = h.amanecer;
    $("anochecer").textContent = h.anochecer;
    sol = { amanecer: h.amanecer, anochecer: h.anochecer };
    aplicarTema();

    const ilum = dibujarLuna(d.luna.ciclo);
    $("fase").textContent = `${faseLunar(d.luna.ciclo)} · ${ilum}%`;
    const hl = (x) => (x ? x.hora + (x.manana ? "<small>mañana</small>" : "") : "—");
    $("luna-sale").innerHTML = hl(d.luna.salida);
    $("luna-pone").innerHTML = hl(d.luna.puesta);

    $("pie").textContent = `Actualizado ${d.actualizado.slice(11, 16)} · Open-Meteo`;
  } catch (e) {
    $("pie").textContent = `Sin datos, reintentando: ${e.message}`;
    espera = REINTENTO_MS;
  }
  timerClima = setTimeout(clima, espera);
}

configuracion.finally(() => {
  reloj();
  setInterval(reloj, 1000);
  clima();
});
