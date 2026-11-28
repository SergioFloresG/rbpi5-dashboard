(() => {
  const PASO_MS = 600;
  const PAUSA_MS = 2500;
  const PAUSA_REAL_MS = 2000;
  const REFRESCO_MS = 60 * 1000;
  const MARCA_MIN = 20;
  const REINTENTOS = 4;

  function capa(url, opts) {
    const c = L.tileLayer(url, opts);
    c.on("tileerror", ({ tile }) => {
      const n = (tile._reintentos || 0) + 1;
      if (n > REINTENTOS) return;
      tile._reintentos = n;
      const src = tile.src.split("?")[0];
      setTimeout(() => { tile.src = `${src}?r=${n}`; }, 3000 * n);
    });
    return c;
  }

  let mapa = null;
  let capas = [];
  let actual = 0;
  let timer = null;
  let ultimoReal = 0;

  async function iniciar() {
    let d;
    try {
      d = await configuracion;
    } catch (e) {
      return setTimeout(iniciar, 30000);
    }

    mapa = L.map("mapa", {
      center: [d.lat, d.lon], zoom: d.radar_zoom,
      zoomControl: false, dragging: false, scrollWheelZoom: false,
      doubleClickZoom: false, boxZoom: false, keyboard: false, touchZoom: false,
      fadeAnimation: false,
    });
    const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/";
    const estilo = () => (document.documentElement.dataset.tema === "claro" ? "Light" : "Dark");
    const url = (tipo) => `${ESRI}World_${estilo()}_Gray_${tipo}/MapServer/tile/{z}/{y}/{x}`;
    const base = capa(url("Base"), {
      maxZoom: 16, attribution: "Esri, HERE, Garmin, © OpenStreetMap",
    }).addTo(mapa);
    mapa.createPane("etiquetas").style.zIndex = 450;
    const etiquetas = capa(url("Reference"), {
      maxZoom: 16, pane: "etiquetas",
    }).addTo(mapa);

    const centro = [d.lat, d.lon];
    const reajustar = () => {
      mapa.invalidateSize(false);
      mapa.setView(centro, d.radar_zoom, { animate: false });
    };
    window.addEventListener("resize", reajustar);
    window.addEventListener("tema", () => { base.setUrl(url("Base")); etiquetas.setUrl(url("Reference")); });
    [1000, 5000, 15000].forEach((ms) => setTimeout(reajustar, ms));
    setInterval(() => { reajustar(); base.redraw(); etiquetas.redraw(); }, 30 * 60 * 1000);
    L.marker([d.lat, d.lon], {
      icon: L.divIcon({ className: "", html: '<div class="punto"></div>', iconSize: [16, 16] }),
      interactive: false,
    }).addTo(mapa);

    await cargarFrames();
    setInterval(cargarFrames, REFRESCO_MS);
  }

  const ESPERA_CARGA_MS = 20000;
  let carga = 0;

  function cargada(c) {
    return new Promise((ok) => {
      c.once("load", ok);
      setTimeout(ok, ESPERA_CARGA_MS);
    });
  }

  async function cargarFrames() {
    let d;
    try {
      d = await (await fetch("/api/radar")).json();
      if (d.error) throw new Error(d.error);
    } catch (e) {
      if (!capas.length) $("radar-hora").textContent = "sin datos";
      return;
    }
    const fuente = d.host.includes("rainviewer")
      ? '<a href="https://www.rainviewer.com">RainViewer</a>'
      : '<a href="https://librewxr.net">LibreWXR</a>';
    const pasados = d.frames.length;
    const corte = d.frames[pasados - 1].time;
    // El pronóstico se recalcula con cada cuadro nuevo: su clave (y URL) cambia para no reutilizarlo.
    const lista = d.frames.map((f) => ({ time: f.time, clave: `${d.host}${f.path}`, q: "" }))
      .concat((d.nowcast || []).map((f) => ({ time: f.time, clave: `${d.host}${f.path}?g=${corte}`, q: `?g=${corte}` })));
    if (lista.length === capas.length && lista.every((f, i) => f.clave === capas[i].clave)) return;

    const turno = ++carga;
    const previas = new Map(capas.map((c) => [c.clave, c]));
    const esperas = [];
    const nuevas = lista.map((f) => {
      const previa = previas.get(f.clave);
      if (previa) return previa;
      const c = capa(`${f.clave.split("?")[0]}/256/{z}/{x}/{y}/2/1_1.png${f.q}`, {
        opacity: 0, maxNativeZoom: 7, maxZoom: 12, className: "radar-frame", attribution: fuente,
      });
      esperas.push(cargada(c));
      c.addTo(mapa);
      return { time: f.time, clave: f.clave, capa: c };
    });
    if (!capas.length) $("radar-hora").textContent = "cargando…";
    await Promise.all(esperas);
    if (turno !== carga) {
      nuevas.filter((c) => !previas.has(c.clave)).forEach((c) => mapa.removeLayer(c.capa));
      return;
    }

    clearTimeout(timer);
    const visible = capas.length ? capas[actual].time : null;
    capas.filter((c) => !nuevas.includes(c)).forEach((c) => mapa.removeLayer(c.capa));
    capas = nuevas;
    ultimoReal = pasados - 1;
    dibujarLinea(pasados);
    actual = capas.findIndex((c) => c.time === visible);
    if (actual < 0) actual = pasados - 1;
    mostrar(actual);
    timer = setTimeout(avanzar, espera());
  }

  const $ = (id) => document.getElementById(id);
  const hhmm = (seg) => new Date(seg * 1000)
    .toLocaleTimeString("es-MX", { timeZone: zona, hour: "2-digit", minute: "2-digit", hour12: false });
  const pos = (seg) => {
    const ini = capas[0].time, fin = capas[capas.length - 1].time;
    return `${Math.min(1, Math.max(0, (seg - ini) / ((fin - ini) || 1))) * 100}%`;
  };

  function dibujarLinea(pasados) {
    const corte = capas[pasados - 1].time;
    $("lt-pas").style.width = pos(corte);
    $("lt-fut").style.left = pos(corte);
    const marcas = [];
    for (let t = capas[0].time; t <= capas[capas.length - 1].time; t += MARCA_MIN * 60) {
      marcas.push(`<span data-t="${t}" class="${t > corte ? "fut" : ""}" style="left:${pos(t)}">${hhmm(t)}</span>`);
    }
    $("lt-escala").innerHTML = marcas.join("");
    marcarAhora();
    $("linea").hidden = false;
  }

  function marcarAhora() {
    if (!capas.length) return;
    const ahora = Date.now() / 1000;
    $("lt-ahora").style.left = pos(ahora);
    $("lt-ahora-txt").textContent = hhmm(ahora);
  }
  setInterval(marcarAhora, 15000);

  function mostrar(i) {
    capas.forEach((c, j) => c.capa.setOpacity(j === i ? 0.75 : 0));
    const t = capas[i].time;
    $("radar-hora").textContent = hhmm(t);
    $("lt-punto").style.left = pos(t);
    $("lt-escala").querySelectorAll("span").forEach((m) => m.classList.toggle("on", +m.dataset.t === t));
  }

  function espera() {
    if (actual === capas.length - 1) return PAUSA_MS;
    return actual === ultimoReal ? PAUSA_REAL_MS : PASO_MS;
  }

  function avanzar() {
    actual = (actual + 1) % capas.length;
    mostrar(actual);
    timer = setTimeout(avanzar, espera());
  }

  iniciar();
})();
