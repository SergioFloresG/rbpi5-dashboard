(() => {
  const DYSON_MS = 10 * 1000;
  const VIEJO_SEG = 300;
  const CALIDAD = ["--", "Buena", "Aceptable", "Mala", "Muy mala", "Extrem. mala", "Grave"];

  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
  const n = (v, d = 0) => (v != null ? v.toFixed(d) : "--");

  // Cada nivel ocupa un tramo igual de la barra; la marca avanza en proporción dentro de su tramo.
  // El último nivel no tiene tope: se le da el ancho del nivel anterior.
  function posicion(v, nivel, lim) {
    const i = nivel - 1, desde = i ? lim[i - 1] : 0;
    const hasta = i < lim.length ? lim[i] : desde + (desde - (lim[i - 2] ?? 0));
    return (100 * (i + Math.min(1, Math.max(0, (v - desde) / (hasta - desde))))) / (lim.length + 1);
  }

  function barra(k, v, u, d, nivel, lim) {
    const tramos = [...lim, 0].map((_, i) => `<i${i + 1 === nivel ? ' class="on"' : ""}></i>`).join("");
    return `<div class="med n${nivel || 0}">
      <div class="par"><span>${k}</span><b>${n(v, d)}<small>${u}</small></b></div>
      <div class="escala">${tramos}${nivel ? `<u style="left:${posicion(v, nivel, lim).toFixed(1)}%"></u>` : ""}</div>
      <div class="topes"><span>0</span>${lim.map((t) => `<span>${t}</span>`).join("")}<span></span></div>
    </div>`;
  }

  function modo(r) {
    if (!r.encendido) return "Apagado";
    return [r.auto ? "Auto" : "Encendido", r.calor && "Calor", r.noche && "Noche"].filter(Boolean).join(" · ");
  }

  function tarjeta(e) {
    const r = e.resumen, nv = r.niveles, lim = r.limites;
    return `<article class="tarjeta aire${e.hace_seg > VIEJO_SEG ? " viejo" : ""}">
      <div class="cab">
        <div class="bat-info">
          <span class="t">${esc(e.etiqueta || "Purificador")}</span>
          <span class="calidad n${r.calidad || 0}">${CALIDAD[r.calidad || 0]}</span>
        </div>
        <div class="amb"><b>${n(r.temp, 1)}<small>°C</small></b><b>${n(r.humedad)}<small>%</small></b></div>
      </div>
      <span class="s">${modo(r)}${r.filtro_hepa != null ? ` · filtro ${Math.round(r.filtro_hepa)}%` : ""}</span>
      <div class="barras">
        ${barra("PM2.5", r.pm2_5, "µg/m³", 0, nv.pm2_5, lim.pm2_5)}
        ${barra("PM10", r.pm10, "µg/m³", 0, nv.pm10, lim.pm10)}
        ${barra("COV", r.cov, "", 1, nv.cov, lim.cov)}
        ${barra("NO₂", r.no2, "", 1, nv.no2, lim.no2)}
      </div>
    </article>`;
  }

  function aviso(e) {
    const nombre = esc(e.etiqueta || e.id), error = esc(e.error);
    if (e.estado === "rechazado") return `Dyson ${nombre}: el equipo rechazó la credencial (repetir dyson_login.py)`;
    if (!e.resumen) return e.estado === "desconectado" ? `Dyson ${nombre}: sin conexión (${error})`
      : `Dyson ${nombre}: ${e.estado === "en_linea" ? "conectado, esperando datos" : "conectando…"}`;
    if (e.estado === "desconectado" && e.hace_seg <= VIEJO_SEG) return `Dyson ${nombre}: sin conexión, se muestra el último dato (${error})`;
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
