"use strict";
const $ = (id) => document.getElementById(id);
let source = null, rows = [], totalEpochs = 0;
const colors = { map50: "#36d399", map5095: "#49a6ff", precision: "#f6c453", recall: "#ff6b7a" };
function value(v) { return (Number(v) * 100).toFixed(1) + "%"; }
function draw() {
  const c = $("chart"), ctx = c.getContext("2d"), w = c.width, h = c.height;
  ctx.clearRect(0, 0, w, h); ctx.strokeStyle = "#263752"; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) { const y = 16 + (h - 32) * i / 4; ctx.beginPath(); ctx.moveTo(38, y); ctx.lineTo(w - 12, y); ctx.stroke(); ctx.fillStyle = "#91a1b8"; ctx.fillText((100 - i * 25) + "%", 4, y + 4); }
  if (!rows.length) return;
  for (const [key, color] of Object.entries(colors)) {
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
    rows.forEach((r, i) => { const x = 40 + (w - 55) * i / Math.max(1, rows.length - 1); const y = 16 + (h - 32) * (1 - Number(r[key])) ; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke();
  }
}
function reset() { rows = []; totalEpochs = 0; $("feed").replaceChildren(); $("summary").classList.add("hidden"); $("precision").textContent = $("recall").textContent = $("map50").textContent = $("map5095").textContent = "—"; $("progressBar").style.width = "0%"; $("epochText").textContent = "Epoch 0 / 0"; draw(); }
function addEpoch(row, total) {
  rows.push({ map50: row["metrics/mAP50(B)"], map5095: row["metrics/mAP50-95(B)"], precision: row["metrics/precision(B)"], recall: row["metrics/recall(B)"] });
  $("precision").textContent = value(row["metrics/precision(B)"]); $("recall").textContent = value(row["metrics/recall(B)"]); $("map50").textContent = value(row["metrics/mAP50(B)"]); $("map5095").textContent = value(row["metrics/mAP50-95(B)"]);
  $("epochText").textContent = `Epoch ${row.epoch} / ${total}`; $("progressBar").style.width = (Number(row.epoch) / total * 100) + "%"; draw();
  const item = document.createElement("div"); item.className = "epoch"; item.innerHTML = `<b>Epoch ${row.epoch}</b><span>mAP50 ${value(row["metrics/mAP50(B)"])} · mAP50-95 ${value(row["metrics/mAP50-95(B)"])}<small>loss: box ${Number(row["train/box_loss"]).toFixed(3)} · cls ${Number(row["train/cls_loss"]).toFixed(3)}</small></span>`; $("feed").prepend(item);
}
async function start() {
  if (source) source.close(); reset(); $("start").disabled = true; $("status").textContent = "Starting real training…";
  const started = await fetch(`/training/start?epochs=${$("epochs").value}`, { method: "POST" });
  if (!started.ok) { const message = await started.text(); $("status").textContent = `Cannot start: ${message}`; $("summary").textContent = message; $("summary").classList.remove("hidden"); $("start").disabled = false; return; }
  source = new EventSource("/training/stream");
  totalEpochs = Number($("epochs").value);
  source.addEventListener("start", (e) => { const d = JSON.parse(e.data); $("runName").textContent = `${d.run} · GPU training`; $("source").textContent = `${d.source} · device ${d.device}`; $("status").textContent = "Training on NVIDIA GPU…"; });
  source.addEventListener("epoch", (e) => { const d = JSON.parse(e.data); addEpoch(d, totalEpochs); });
  source.addEventListener("complete", (e) => { const d = JSON.parse(e.data); $("status").textContent = "Training complete"; $("summary").textContent = `The actual training process completed ${d.epochs} epochs. Metrics above came from its results.csv.`; $("summary").classList.remove("hidden"); $("start").disabled = false; source.close(); });
  source.addEventListener("error", (e) => { try { const d = JSON.parse(e.data); $("status").textContent = d.message; $("summary").textContent = d.log || d.message; $("summary").classList.remove("hidden"); } catch { $("status").textContent = "Training failed"; } $("start").disabled = false; source.close(); });
  source.onerror = () => { if (source.readyState === EventSource.CLOSED) { $("status").textContent = "Connection closed"; $("start").disabled = false; } };
}
$("start").addEventListener("click", start); draw();
