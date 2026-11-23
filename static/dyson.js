(() => {
  const DYSON_MS = 10 * 1000;
  const VIEJO_SEG = 300;
  const CALIDAD = ["--", "Buena", "Aceptable", "Mala", "Muy mala"];

  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
  const n = (v, u = "", d = 0) => (v != null ? `${v.toFixed(d)}<small>${u}</small>` : "--");
  const par = (k, v, nivel) => `<div class="par${nivel ? ` n${nivel}` : ""}"><span>${k}</span><b>${v}</b></div>`;

  function modo(r) {
    if (!r.encendido) return "Apagado";
    return [r.auto ? "Auto" : "Encendido", r.calor && "Calor", r.noche && "Noche"].filter(Boolean).join(" · ");
  }

  function tarjeta(e) {
    const r = e.resumen, nv = r.niveles;
    return `<article class="tarjeta bat aire${e.hace_seg > VIEJO_SEG ? " viejo" : ""}">
      <div class="bat-carga">
        <div class="bat-info">
          <span class="t">${esc(e.etiqueta || "Purificador")}</span>
          <span class="calidad n${r.calidad || 0}">${CALIDAD[r.calidad || 0]}</span>
          <span class="s">calidad del aire</span>
          <span class="s">${modo(r)}${r.filtro_hepa != null ? ` · filtro ${Math.round(r.filtro_hepa)}%` : ""}</span>
        </div>
      </div>
      <div>
        <h3>Partículas</h3>
        <div class="lista">${par("PM2.5", n(r.pm2_5, "µg/m³"), nv.pm2_5)}${par("PM10", n(r.pm10, "µg/m³"), nv.pm10)}</div>
      </div>
      <div>
        <h3>Gases</h3>
        <div class="lista">${par("COV", n(r.cov, "", 1), nv.cov)}${par("NO₂", n(r.no2, "", 1), nv.no2)}</div>
      </div>
      <div>
        <h3>Ambiente</h3>
        <div class="lista">${par("Temp.", n(r.temp, "°C", 1))}${par("Humedad", n(r.humedad, "%"))}</div>
      </div>
    </article>`;
  }

  function aviso(e) {
    const nombre = esc(e.etiqueta || e.id), error = esc(e.error);
    if (e.estado === "rechazado") return `Dyson ${nombre}: el equipo rechazó la credencial (repetir dyson_login.py)`;
    if (!e.resumen) return e.estado === "desconectado" ? `Dyson ${nombre}: sin conexión (${error})`
      : `Dyson ${nombre}: ${e.estado === "en_linea" ? "conectado, esperando datos" : "conectando…"}`;
    if (e.hace_seg > VIEJO_SEG) return `Dyson ${nombre}: último dato hace ${Math.round(e.hace_seg / 60)} min (${error || "sin datos"})`;
    return "";
  }

  async function dyson() {
    try {
      const d = await (await fetch("/api/dyson")).json();
      if (!d.configurado) return;
      $("dyson").innerHTML = d.equipos.map((e) => (e.resumen ? tarjeta(e) : "")).join("");
      const avisos = [d.error && esc(d.error), ...d.equipos.map(aviso)].filter(Boolean);
      $("dyson-aviso").hidden = !avisos.length;
      $("dyson-aviso").innerHTML = avisos.join("<br>");
    } catch (e) {
      $("dyson-aviso").hidden = false;
      $("dyson-aviso").textContent = `Dyson: ${e.message}`;
    }
    setTimeout(dyson, DYSON_MS);
  }

  configuracion.finally(dyson);
})();
