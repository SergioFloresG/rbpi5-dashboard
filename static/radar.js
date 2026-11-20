(() => {
  const PASO_MS = 600;
  const PAUSA_MS = 2500;
  const REFRESCO_MS = 5 * 60 * 1000;
  const MAX_FRAMES = 8;
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
      maxZoom: 16, attribution: "Esri, HERE, Garmin, © OpenStreetMap · RainViewer",
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

  async function cargarFrames() {
    let d;
    try {
      d = await (await fetch("/api/radar")).json();
      if (d.error) throw new Error(d.error);
    } catch (e) {
      document.getElementById("radar-hora").textContent = "sin datos";
      return;
    }
    clearTimeout(timer);
    capas.forEach((c) => mapa.removeLayer(c.capa));
    capas = d.frames.slice(-MAX_FRAMES).map((f) => ({
      time: f.time,
      capa: capa(`${d.host}${f.path}/256/{z}/{x}/{y}/2/1_1.png`, {
        opacity: 0, maxNativeZoom: 7, maxZoom: 12, className: "radar-frame",
      }).addTo(mapa),
    }));
    actual = capas.length - 1;
    mostrar(actual);
    timer = setTimeout(avanzar, PAUSA_MS);
  }

  function mostrar(i) {
    capas.forEach((c, j) => c.capa.setOpacity(j === i ? 0.75 : 0));
    const t = new Date(capas[i].time * 1000);
    document.getElementById("radar-hora").textContent =
      t.toLocaleTimeString("es-MX", { timeZone: zona, hour: "2-digit", minute: "2-digit", hour12: false });
  }

  function avanzar() {
    actual = (actual + 1) % capas.length;
    mostrar(actual);
    timer = setTimeout(avanzar, actual === capas.length - 1 ? PAUSA_MS : PASO_MS);
  }

  iniciar();
})();
