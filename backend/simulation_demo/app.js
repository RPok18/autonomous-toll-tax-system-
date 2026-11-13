"use strict";
const $ = (id) => document.getElementById(id);
let source = null;
let stats = { total: 0, correct: 0, wrong: 0, unresolved: 0, exceptions: 0, paid: 0, charged: 0, latency: 0 };

function reset(total) {
  stats = { total: 0, correct: 0, wrong: 0, unresolved: 0, exceptions: 0, paid: 0, charged: 0, latency: 0 };
  $("feed").replaceChildren(); $("summary").classList.add("hidden");
  $("progressText").textContent = `0 / ${total}`; $("progressBar").style.width = "0%";
  ["correct", "exceptions", "paid"].forEach((id) => $(id).textContent = "0");
  $("charged").textContent = "₹0.00"; $("latency").textContent = "0 ms";
  ["correct", "wrong", "unresolved"].forEach((id) => { $(id + "Bar").style.width = "0%"; $(id + "Pct").textContent = "0%"; });
}
function update() {
  const n = stats.total || 1;
  $("correct").textContent = stats.correct; $("exceptions").textContent = stats.exceptions; $("paid").textContent = stats.paid;
  $("charged").textContent = "₹" + stats.charged.toFixed(2);
  $("latency").textContent = (stats.latency / n).toFixed(1) + " ms";
  for (const id of ["correct", "wrong", "unresolved"]) {
    const pct = stats[id] / n * 100;
    $(id + "Bar").style.width = pct + "%"; $(id + "Pct").textContent = pct.toFixed(1) + "%";
  }
  $("progressText").textContent = `${stats.total} / ${$("passes").value}`;
  $("progressBar").style.width = (stats.total / Number($("passes").value) * 100) + "%";
}
function addPass(r) {
  stats.total++; stats[r.outcome]++; stats.latency += Number(r.rfid_latency_ms || 0);
  if (r.fusion_exception) stats.exceptions++;
  if (r.charge_status === "paid") { stats.paid++; stats.charged += Number(r.charged_amount || 0); }
  const status = r.charge_status === "paid" ? "ok" : (r.fusion_exception ? "hold" : "badtext");
  const row = document.createElement("div"); row.className = "event";
  const no = document.createElement("span"); no.className = "event-no"; no.textContent = "#" + r.pass_no;
  const details = document.createElement("span");
  const plate = document.createElement("b"); plate.textContent = r.true_plate;
  const small = document.createElement("small");
  small.textContent = `ANPR: ${r.anpr_plate || "none"} · RFID: ${r.rfid_tag || "none"} · ${r.method}`;
  details.append(plate, small);
  const result = document.createElement("b"); result.className = status; result.textContent = r.charge_status.replaceAll("_", " ");
  row.append(no, details, result); $("feed").prepend(row); update();
}
function start() {
  if (source) source.close();
  const scenario = $("scenario").value, passes = Number($("passes").value), seed = Number($("seed").value);
  reset(passes); $("start").disabled = true; $("status").textContent = "Running…";
  source = new EventSource(`/simulation/stream?scenario=${encodeURIComponent(scenario)}&passes=${passes}&seed=${seed}`);
  source.addEventListener("start", (e) => { const d = JSON.parse(e.data); $("scenarioName").textContent = `${d.scenario} · ${d.name}`; $("scenarioDescription").textContent = d.description; });
  source.addEventListener("pass", (e) => addPass(JSON.parse(e.data)));
  source.addEventListener("complete", (e) => {
    const d = JSON.parse(e.data); $("status").textContent = "Complete";
    $("summary").textContent = `Run complete: ${d.correct_pct.toFixed(1)}% correct identification, ${d.exception_pct.toFixed(1)}% exceptions, ${d.latency_p95_ms.toFixed(1)} ms p95 RFID latency.`;
    $("summary").classList.remove("hidden"); $("start").disabled = false; source.close();
  });
  source.addEventListener("error", (e) => { $("status").textContent = "Simulation error"; $("start").disabled = false; source.close(); });
  source.onerror = () => { if (source.readyState === EventSource.CLOSED) { $("status").textContent = "Connection closed"; $("start").disabled = false; } };
}
$("start").addEventListener("click", start);
