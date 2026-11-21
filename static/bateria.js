(() => {
  const BAT_MS = 10 * 1000;
  const VIEJO_SEG = 600;
  const R = 52, C = 2 * Math.PI * R;
  const ENTRADAS = [["solar1", "Solar 1"], ["solar2", "Solar 2"], ["ac", "AC"], ["extra", "Extra"]];
  const SALIDAS = [["ac", "AC"], ["usb_c", "USB-C"], ["usb_a", "USB-A"], ["dc12v", "12V"]];
  const ESTADOS = { cargando: "Cargando", descargando: "Descargando", reposo: "En reposo" };
  const AVISOS = {
    conectando: "Batería: conectando con EcoFlow…",
    desconectado: "Batería: sin conexión con EcoFlow, reintentando",
    error_login: "Batería: EcoFlow rechazó el usuario o la contraseña",
    conectado: "Batería: conectado, esperando datos",
  };

  const w = (v) => `${v}<small>W</small>`;
  const lista = (orden, vals) => orden.map(([k, n]) =>
    `<div class="par${vals[k] ? "" : " cero"}"><span>${n}</span><b>${w(vals[k] || 0)}</b></div>`).join("");

  function duracion(min) {
    if (min == null) return "--";
    const d = Math.floor(min / 1440), h = Math.floor((min % 1440) / 60), m = min % 60;
    if (d) return `${d} d ${h} h`;
    return h ? `${h} h ${m} min` : `${m} min`;
  }

  function limite(pct) {
    const a = ((pct * 3.6 - 90) * Math.PI) / 180;
    const p = (r) => [60 + r * Math.cos(a), 60 + r * Math.sin(a)];
    const [x1, y1] = p(R - 9), [x2, y2] = p(R + 9);
    Object.entries({ x1, y1, x2, y2 }).forEach(([k, v]) => $("bat-lim").setAttribute(k, v.toFixed(1)));
  }

  const num = (v, u = "") => (v != null ? `${Math.round(v)}${u}` : "--");

  function saludSimple(r) {
    return `<div class="valor">${r.salud != null ? `${Math.round(r.salud)}<small>%</small>` : "--"}</div>
      <div class="par"><span>Ciclos</span><b>${num(r.ciclos)}</b></div>
      <div class="par"><span>Temp.</span><b>${num(r.temp, "°")}</b></div>`;
  }

  function tablaSalud(packs) {
    const fila = (n, f) => `<span>${n}</span>${packs.map((p) => `<b>${f(p)}</b>`).join("")}`;
    return `<div class="tabla" style="grid-template-columns: auto repeat(${packs.length}, auto)">
      <span></span>${packs.map((p) => `<i>${p.nombre}</i>`).join("")}
      ${fila("Salud", (p) => num(p.salud, "%"))}
      ${fila("Ciclos", (p) => num(p.ciclos))}
      ${fila("Temp.", (p) => num(p.temp, "°"))}</div>`;
  }

  function pintar(r, viejo) {
    const t = $("bat");
    t.className = `tarjeta bat ${r.estado || ""}${r.soc != null && r.soc <= 15 ? " bajo" : ""}${viejo ? " viejo" : ""}`;
    const soc = r.soc ?? 0;
    $("bat-nivel").setAttribute("stroke-dasharray", `${(C * soc / 100).toFixed(1)} ${C.toFixed(1)}`);
    $("bat-pct").innerHTML = r.soc != null ? `${Math.round(r.soc)}<tspan>%</tspan>` : "--";
    $("bat-est").textContent = ESTADOS[r.estado] || "";
    $("bat-lim").style.display = r.min_descarga ? "" : "none";
    if (r.min_descarga) limite(r.min_descarga);

    $("bat-tiempo").textContent = duracion(r.restante_min);
    $("bat-tiempo-sub").textContent = r.restante_min == null ? "" : r.estado === "cargando" ? "para lleno" : "restante";
    $("bat-wh").textContent = r.wh != null ? `≈ ${r.wh} / ${r.capacidad_wh} Wh` : "";

    $("bat-entrada").innerHTML = w(r.entrada_w);
    $("bat-entradas").innerHTML = lista(ENTRADAS, r.entradas);
    $("bat-salida").innerHTML = w(r.salida_w);
    $("bat-salidas").innerHTML = lista(SALIDAS, r.salidas) + (r.salida_max_w
      ? `<div class="par"><span>Carga</span><b>${r.carga_pct}<small>%</small></b></div>
         <div class="par"><span>Máx.</span><b>${w(Math.round(r.salida_max_w))}</b></div>` : "");

    const packs = r.baterias || [];
    $("bat-packs").textContent = packs.length > 1
      ? packs.map((p) => `${p.nombre} ${p.soc != null ? Math.round(p.soc) : "--"}%`).join(" · ") : "";
    $("bat-salud").innerHTML = packs.length > 1 ? tablaSalud(packs) : saludSimple(r);
  }

  async function bateria() {
    try {
      const d = await (await fetch("/api/bateria")).json();
      if (d.estado === "sin_configurar") return;
      const viejo = d.hace_seg != null && d.hace_seg > VIEJO_SEG;
      $("bat").hidden = !d.resumen;
      if (d.resumen) pintar(d.resumen, viejo);
      const aviso = viejo ? `Batería: último dato hace ${Math.round(d.hace_seg / 60)} min` : AVISOS[d.estado];
      $("bat-aviso").hidden = !aviso;
      $("bat-aviso").textContent = aviso || "";
    } catch (e) {
      $("bat-aviso").hidden = false;
      $("bat-aviso").textContent = `Batería: ${e.message}`;
    }
    setTimeout(bateria, BAT_MS);
  }

  configuracion.finally(bateria);
})();
