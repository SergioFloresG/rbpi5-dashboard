(() => {
  const UPS_MS = 5 * 1000;
  const VIEJO_SEG = 60;
  const R = 52, C = 2 * Math.PI * R;
  const PRUEBAS = { "no test initiated": "--", "done and passed": "OK", "in progress": "En curso" };
  const ALARMA = { enabled: "Activa", disabled: "Apagada", muted: "Silenciada" };

  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
  const n = (v, u = "", d = 0) => (v != null ? `${v.toFixed(d)}<small>${u}</small>` : "--");
  const par = (k, v, cls = "") => `<div class="par ${cls}"><span>${k}</span><b>${v}</b></div>`;

  function duracion(min) {
    if (min == null) return "--";
    const h = Math.floor(min / 60), m = min % 60;
    return h ? `${h} h ${m} min` : `${m} min`;
  }

  function red(r) {
    const b = r.banderas;
    if (r.estado === "bateria") return ["Sin red", "malo"];
    if (b.includes("avr_eleva")) return ["AVR ↑", "aviso"];
    if (b.includes("avr_reduce")) return ["AVR ↓", "aviso"];
    if (b.includes("bypass")) return ["Bypass", "aviso"];
    return [r.estado === "red" ? "Normal" : "--", ""];
  }

  function tarjeta(u) {
    const r = u.resumen, b = r.banderas;
    const bajo = b.includes("baja") || (r.soc != null && r.soc_bajo != null && r.soc <= r.soc_bajo);
    const clase = `${r.estado === "bateria" ? "descargando" : "cargando"}${bajo ? " bajo" : ""}${u.hace_seg > VIEJO_SEG ? " viejo" : ""}`;
    const soc = r.soc ?? 0;
    const est = r.estado === "bateria" ? "En batería" : r.estado === "red" ? (b.includes("cargando") ? "Cargando" : "En red") : "";
    const [txtRed, clsRed] = red(r);
    const prueba = r.prueba ? PRUEBAS[r.prueba.toLowerCase()] || esc(r.prueba) : "--";
    const extra = [b.includes("reemplazar") && "Cambiar batería", b.includes("sobrecarga") && "Sobrecarga"].filter(Boolean);
    return `<article class="tarjeta bat ups ${clase}">
      <div class="bat-carga">
        <svg class="rueda" viewBox="0 0 120 120">
          <circle class="fondo" cx="60" cy="60" r="52"/>
          <circle class="nivel" cx="60" cy="60" r="52" stroke-dasharray="${(C * soc / 100).toFixed(1)} ${C.toFixed(1)}"/>
          <text x="60" y="64" class="pct">${r.soc != null ? `${Math.round(r.soc)}<tspan>%</tspan>` : "--"}</text>
          <text x="60" y="82" class="est">${est}</text>
        </svg>
        <div class="bat-info">
          <span class="t">${esc(u.etiqueta || "UPS")}</span>
          <span class="v">${duracion(r.restante_min)}</span>
          <span class="s">${r.restante_min != null ? "autonomía" : ""}</span>
          <span class="s">${esc(r.modelo)}</span>
        </div>
      </div>
      <div class="bat-ent">
        <div class="cab"><h3>Entrada</h3><div class="valor">${n(r.v_entrada, "V")}</div></div>
        <div class="lista">${par("Red", txtRed, clsRed)}${par("Nominal", n(r.v_nominal, "V"))}</div>
      </div>
      <div class="bat-sal">
        <div class="cab"><h3>Salida</h3><div class="valor">${n(r.potencia_w, "W")}</div></div>
        <div class="lista">${par("Voltaje", n(r.v_salida, "V"))}${par("Carga", n(r.carga_pct, "%"))}${par("Máx.", n(r.nominal_w, "W"))}</div>
      </div>
      <div class="bat-salud">
        <h3>Estado</h3>
        ${extra.length ? par("Aviso", extra.join(", "), "malo") : par("Batería", n(r.v_bateria, "V", 1))}
        ${par("Prueba", prueba)}
        ${par("Alarma", ALARMA[r.alarma] || esc(r.alarma) || "--")}
      </div>
    </article>`;
  }

  function aviso(u) {
    const nombre = esc(u.etiqueta || u.id), error = esc(u.error);
    if (!u.resumen) return u.estado === "desconectado" ? `UPS ${nombre}: sin conexión con NUT (${error})` : `UPS ${nombre}: conectando…`;
    if (u.hace_seg > VIEJO_SEG) return `UPS ${nombre}: último dato hace ${Math.round(u.hace_seg / 60)} min (${error || "sin datos"})`;
    return "";
  }

  async function ups() {
    try {
      const d = await (await fetch("/api/ups")).json();
      if (!d.configurado) return;
      $("ups").innerHTML = d.ups.map((u) => (u.resumen ? tarjeta(u) : "")).join("");
      const avisos = d.ups.map(aviso).filter(Boolean);
      $("ups-aviso").hidden = !avisos.length;
      $("ups-aviso").innerHTML = avisos.join("<br>");
    } catch (e) {
      $("ups-aviso").hidden = false;
      $("ups-aviso").textContent = `UPS: ${e.message}`;
    }
    setTimeout(ups, UPS_MS);
  }

  configuracion.finally(ups);
})();
