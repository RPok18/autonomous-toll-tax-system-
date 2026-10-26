"use strict";
/* Toll dashboard (design: wiki article 08). Plain JavaScript, no build step.
   Every value from the API goes into the page with textContent, never innerHTML. */

const REFRESH_MS = 30000;
const TIMEOUT_MS = 10000;
const DASH_ROLES = ["admin", "operator", "auditor"];

const LABELS = {
  identification_method: {
    anpr_only: "ANPR only", rfid_only: "RFID only", hybrid_agreed: "Hybrid agreed",
    hybrid_rfid_primary: "Hybrid RFID", hybrid_anpr_primary: "Hybrid ANPR", manual: "Manual", unresolved: "Unresolved",
  },
  vehicle_class: {
    two_wheeler: "Two-wheeler", car_jeep_van: "Car/Jeep/Van", lcv: "LCV", bus_truck: "Bus/Truck",
    hcv_mav: "HCV/MAV", oversized: "Oversized", exempt_other: "Exempt/other", unknown: "Unknown",
  },
  exception_type: {
    low_confidence_plate: "Low-confidence plate", tag_mismatch: "Tag mismatch", no_identification: "No identification",
    tag_not_found: "Tag not found", policy_violation: "Policy violation", device_fault: "Device fault",
  },
  payment_status: { paid: "paid", pending: "pending", failed: "failed", waived: "waived", disputed: "disputed" },
};

const state = {
  token: null, role: null, username: "",
  view: "transactions",
  plazas: [], plazaById: {},
  tx: { transaction_id: "", plaza_id: "", exceptions_only: false, payment_status: "", from: "", to: "", limit: 50, offset: 0 },
  ex: { status: "open", plaza_id: "", exception_type: "", transaction_id: "", limit: 50, offset: 0 },
  rows: [], total: null, selectedId: null,
  loading: false, error: null, loaded: false, loadedAt: null, forbidden: false, notice: "",
  plazaError: null, actionError: {},
};
let timer = null;
let reqSeq = 0;

/* ------------------------------------------------------------ helpers */
function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k in e && k !== "list") e[k] = v;
    else e.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return e;
}
const DASH = "—";
const orDash = (v) => (v === null || v === undefined || v === "" ? DASH : String(v));
function fmtTime(iso) {
  if (!iso) return DASH;
  const d = new Date(iso);
  return d.toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}
function fmtMoney(v, currency) {
  if (v === null || v === undefined) return DASH;
  const n = Number(v);
  const sym = currency === "INR" || !currency ? "₹ " : currency + " ";
  return sym + n.toFixed(2);
}
const fmtConf = (v) => (v === null || v === undefined ? "" : " " + Number(v).toFixed(2));
const label = (group, v) => (v == null ? DASH : LABELS[group][v] || v);
const plazaName = (id) => (id ? (state.plazaById[id] ? state.plazaById[id].plaza_code : id.slice(0, 8)) : DASH);
const badge = (cls, text) => el("span", { class: "badge b-" + cls }, text);

function store(key, value) { try { value == null ? sessionStorage.removeItem(key) : sessionStorage.setItem(key, value); } catch (e) { /* storage blocked */ } }
function load(key) { try { return sessionStorage.getItem(key); } catch (e) { return null; } }

/* ------------------------------------------------------------ api */
async function api(path, options = {}) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(path, {
      ...options,
      signal: ctrl.signal,
      headers: { ...(options.headers || {}), ...(state.token ? { Authorization: "Bearer " + state.token } : {}) },
    });
    if (res.status === 401 && state.token) { logout("Your session has ended. Sign in again."); throw new Error("401"); }
    return res;
  } finally { clearTimeout(t); }
}
async function detail(res) {
  try { const j = await res.json(); return typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (e) { return "HTTP " + res.status; }
}

/* ------------------------------------------------------------ session */
function logout(notice) {
  state.token = null; state.role = null; state.notice = notice || "";
  store("token", null); store("role", null); store("username", null);
  stopTimer(); render();
}
async function login(username, password) {
  let res;
  try {
    res = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
  } catch {
    return "Could not sign in. Check the connection and try again.";
  }
  if (!res.ok) return res.status === 401 ? "Wrong user name or password." : "Sign-in failed (" + (await detail(res)) + ").";
  let body;
  try {
    body = await res.json();
  } catch {
    return "Sign-in failed because the server returned an invalid response.";
  }
  if (typeof body.access_token !== "string" || typeof body.role !== "string") {
    return "Sign-in failed because the server returned an invalid response.";
  }
  state.token = body.access_token; state.role = body.role; state.username = username; state.notice = "";
  store("token", state.token); store("role", state.role); store("username", username);
  return null;
}
const canWrite = () => state.role === "admin" || state.role === "operator";

/* ------------------------------------------------------------ data */
function params() {
  const q = new URLSearchParams();
  const f = state.view === "transactions" ? state.tx : state.ex;
  q.set("limit", f.limit); q.set("offset", f.offset);
  if (f.plaza_id) q.set("plaza_id", f.plaza_id);
  if (state.view === "transactions") {
    if (f.transaction_id) q.set("transaction_id", f.transaction_id);
    if (f.exceptions_only) q.set("is_exception", "true");
    if (f.payment_status) q.set("payment_status", f.payment_status);
    if (f.from) q.set("from", new Date(f.from + "T00:00:00").toISOString());
    if (f.to) { const d = new Date(f.to + "T00:00:00"); d.setDate(d.getDate() + 1); q.set("to", d.toISOString()); }
  } else {
    if (f.status === "open") q.set("resolved", "false");
    if (f.status === "resolved") q.set("resolved", "true");
    if (f.exception_type) q.set("exception_type", f.exception_type);
    if (f.transaction_id) q.set("transaction_id", f.transaction_id);
  }
  return q;
}
async function loadPlazas() {
  try {
    const res = await api("/plazas");
    if (!res.ok) { state.plazaError = "Could not load plaza filters (" + res.status + ")."; return; }
    state.plazas = await res.json();
    state.plazaById = Object.fromEntries(state.plazas.map((p) => [p.plaza_id, p]));
    state.plazaError = null;
  } catch (e) {
    if (e && e.message === "401") return;
    state.plazaError = "Could not load plaza filters. Check the connection.";
  }
}
async function loadRows(keepPanel) {
  if (!state.token) return;
  const seq = ++reqSeq;
  state.loading = true; state.error = null;
  render(keepPanel);
  try {
    const res = await api("/" + state.view + "?" + params());
    if (seq !== reqSeq) return;
    if (res.status === 403) { state.forbidden = true; return; }
    if (!res.ok) { state.error = res.status === 422 ? "Invalid filter: " + (await detail(res)) : "Could not load " + state.view + " (" + res.status + ")."; return; }
    state.rows = await res.json();
    const total = res.headers.get("X-Total-Count");
    state.total = total === null ? null : Number(total);
    state.loaded = true; state.loadedAt = new Date();
    if (state.selectedId && !state.rows.some((r) => rowId(r) === state.selectedId)) state.selectedId = null;
  } catch (e) {
    if (seq !== reqSeq || (e && e.message === "401")) return;
    state.error = "Could not load " + state.view + ". Check the connection.";
  } finally {
    if (seq === reqSeq) { state.loading = false; render(keepPanel); }
  }
}
const rowId = (r) => (state.view === "transactions" ? r.transaction_id : r.exception_id);

function startTimer() { stopTimer(); timer = setInterval(() => { if (!document.hidden && !state.loading && !state.error) loadRows(true); }, REFRESH_MS); }
function stopTimer() { if (timer) clearInterval(timer); timer = null; }

/* ------------------------------------------------------------ routing */
function readHash() {
  const [path, query] = location.hash.replace(/^#\/?/, "").split("?");
  state.view = path === "exceptions" ? "exceptions" : "transactions";
  const q = new URLSearchParams(query || "");
  const before = state.ex.transaction_id;
  state.ex.transaction_id = q.get("transaction_id") || "";
  state.tx.transaction_id = state.view === "transactions" ? q.get("transaction_id") || "" : "";
  // Following a link to one pass shows all its exceptions; leaving that link goes back to the Open queue.
  if (state.ex.transaction_id) state.ex.status = "all";
  else if (before) state.ex.status = "open";
}
function go(view, query) { location.hash = "#/" + view + (query ? "?" + query : ""); }
window.addEventListener("hashchange", () => {
  readHash(); state.rows = []; state.total = null; state.loaded = false; state.selectedId = null; state.error = null; state.forbidden = false;
  if (state.token) loadRows();
});

async function resolve(rec) {
  state.actionError[rec.exception_id] = "";
  try {
    const res = await api("/exceptions/" + rec.exception_id + "/resolve", { method: "PATCH" });
    if (res.ok) {
      const updated = await res.json();
      if (state.ex.status === "open") {
        state.rows = state.rows.filter((row) => row.exception_id !== updated.exception_id);
        state.total = Math.max(0, (state.total || 0) - 1);
        if (state.selectedId === updated.exception_id) state.selectedId = null;
        if (!state.rows.length && state.ex.offset > 0) {
          state.ex.offset = Math.max(0, state.ex.offset - state.ex.limit);
          await loadRows(true);
          return;
        }
      } else {
        replaceRow(updated);
      }
    }
    else state.actionError[rec.exception_id] = res.status === 404 ? "This exception no longer exists." : "Could not resolve (" + res.status + ").";
  } catch (e) { if (e.message !== "401") state.actionError[rec.exception_id] = "Could not resolve. Check the connection."; }
  render(true);
}
function replaceRow(updated) { state.rows = state.rows.map((r) => (r.exception_id === updated.exception_id ? updated : r)); }

/* ------------------------------------------------------------ rendering */
function render(keepPanel) {
  const app = document.getElementById("app");
  const scroll = window.scrollY;
  app.replaceChildren(state.token ? shell() : loginPage());
  if (keepPanel) window.scrollTo(0, scroll);
}

function loginPage() {
  const err = el("div", { class: "err" }, state.notice);
  const user = el("input", { type: "text", autocomplete: "username", required: true });
  const pass = el("input", { type: "password", autocomplete: "current-password", required: true });
  const form = el("form", { class: "login", onsubmit: async (ev) => {
    ev.preventDefault();
    const msg = await login(user.value.trim(), pass.value);
    if (msg) { state.notice = msg; render(); return; }
    await boot();
  } }, el("h1", {}, "Toll dashboard"), el("label", {}, "User name", user), el("label", {}, "Password", pass), el("button", { class: "primary", type: "submit" }, "Sign in"), err);
  return form;
}

function shell() {
  if (!DASH_ROLES.includes(state.role)) {
    return el("div", {}, topbar(false),
      el("div", { class: "state full" }, "Your role (" + state.role + ") cannot open the dashboard. Ask an administrator.", el("br"), el("button", { onclick: () => logout() }, "Log out")));
  }
  return el("div", {}, topbar(true), el("main", {}, state.view === "transactions" ? transactionsView() : exceptionsView()));
}
function topbar(withNav) {
  const link = (v, text) => el("a", { href: "#/" + v, class: state.view === v ? "on" : "" }, text);
  return el("header", { class: "top" }, el("span", { class: "brand" }, "Toll dashboard"),
    el("nav", {}, withNav ? [link("transactions", "Transactions"), link("exceptions", "Exceptions")] : null),
    el("span", { class: "who" }, (state.username || "") + " · " + state.role), el("button", { class: "link", onclick: () => logout() }, "Log out"));
}

function plazaSelect(f) {
  const sel = el("select", { onchange: () => { f.plaza_id = sel.value; f.offset = 0; loadRows(); } },
    el("option", { value: "" }, "All plazas"),
    state.plazas.map((p) => el("option", { value: p.plaza_id, selected: p.plaza_id === f.plaza_id }, p.plaza_code + " · " + p.name)));
  return el("label", {}, "Plaza", sel);
}
function limitSelect(f) {
  const sel = el("select", { onchange: () => { f.limit = Number(sel.value); f.offset = 0; loadRows(); } },
    [25, 50, 100, 200].map((n) => el("option", { value: n, selected: n === f.limit }, String(n))));
  return el("label", {}, "Rows", sel);
}

function body(columns, rows, renderRow, emptyKind) {
  if (state.forbidden) return el("div", { class: "state full" }, "Your role (" + state.role + ") cannot open this view.");
  const parts = [];
  if (state.error) {
    parts.push(el("div", { class: "banner" }, el("span", {}, state.error + (state.loadedAt ? " Showing data from " + state.loadedAt.toLocaleTimeString() + "." : "")),
      el("span", { class: "spacer" }), el("button", { onclick: () => loadRows() }, "Retry")));
  }
  const head = el("thead", {}, el("tr", {}, columns.map((c) => el("th", { class: c.num ? "num" : "" }, c.name))));
  let tbody;
  if (state.loading && !state.loaded) {
    tbody = el("tbody", {}, [0, 1, 2, 3, 4].map(() => el("tr", { class: "skeleton" }, columns.map(() => el("td", {}, " ")))));
  } else {
    tbody = el("tbody", {}, rows.map(renderRow));
  }
  if (state.loaded && !rows.length && !state.error) parts.push(emptyKind());
  else if (state.error && !state.loaded) { /* banner only */ }
  else parts.push(el("div", { class: "tablewrap " + (state.error ? "stale" : "") }, el("table", {}, head, tbody)));
  return parts;
}
function pager(f) {
  if (!state.loaded || state.total === null) return null;
  const from = state.total === 0 ? 0 : f.offset + 1;
  const to = Math.min(f.offset + f.limit, state.total);
  return el("div", { class: "pager" },
    el("button", { disabled: f.offset === 0, onclick: () => { f.offset = Math.max(0, f.offset - f.limit); loadRows(); } }, "Previous"),
    el("span", {}, from + "–" + to + " of " + state.total),
    el("button", { disabled: f.offset + f.limit >= state.total, onclick: () => { f.offset += f.limit; loadRows(); } }, "Next"),
    state.loading ? el("span", {}, "Loading…") : null);
}

/* ---- transactions view */
function transactionsView() {
  const f = state.tx;
  const exOnly = el("input", { type: "checkbox", checked: f.exceptions_only, onchange: () => { f.exceptions_only = exOnly.checked; f.offset = 0; loadRows(); } });
  const pay = el("select", { onchange: () => { f.payment_status = pay.value; f.offset = 0; loadRows(); } },
    el("option", { value: "" }, "Any"), Object.keys(LABELS.payment_status).map((s) => el("option", { value: s, selected: s === f.payment_status }, s)));
  const from = el("input", { type: "date", value: f.from, onchange: () => { f.from = from.value; f.offset = 0; loadRows(); } });
  const to = el("input", { type: "date", value: f.to, onchange: () => { f.to = to.value; f.offset = 0; loadRows(); } });
  const filtered = f.transaction_id || f.plaza_id || f.exceptions_only || f.payment_status || f.from || f.to;
  const cols = [{ name: "Time" }, { name: "Plaza" }, { name: "Lane" }, { name: "Plate" }, { name: "Tag" }, { name: "Identified by" }, { name: "Class" },
    { name: "Amount", num: true }, { name: "Payment" }, { name: "" }];
  const empty = () => el("div", { class: "state" }, filtered ? "No transactions match these filters." : "No transactions yet. Passes appear here as soon as a plaza charges a vehicle.",
    el("br"), filtered ? el("button", { onclick: () => { Object.assign(f, { transaction_id: "", plaza_id: "", exceptions_only: false, payment_status: "", from: "", to: "", offset: 0 }); loadRows(); } }, "Clear filters")
      : el("button", { onclick: () => loadRows() }, "Refresh"));
  const rowFn = (r) => {
    const sel = r.transaction_id === state.selectedId;
    const tr = el("tr", { class: "row" + (sel ? " sel" : ""), onclick: () => { state.selectedId = sel ? null : r.transaction_id; render(true); } },
      el("td", {}, fmtTime(r.transaction_time)), el("td", {}, plazaName(r.plaza_id)), el("td", {}, orDash(r.lane_id)),
      el("td", {}, r.plate_number ? r.plate_number + fmtConf(r.plate_confidence) : DASH),
      el("td", {}, r.tag_id ? r.tag_id + fmtConf(r.tag_confidence) : DASH),
      el("td", {}, label("identification_method", r.identification_method)), el("td", {}, label("vehicle_class", r.vehicle_class)),
      el("td", { class: "num" }, fmtMoney(r.amount_charged, r.currency)), el("td", {}, badge(r.payment_status, r.payment_status)),
      el("td", {}, r.is_exception ? el("a", { class: "flag", href: "#/exceptions?transaction_id=" + r.transaction_id, title: "Open in Exceptions", onclick: (e) => e.stopPropagation() }, "!") : null));
    return tr;
  };
  const selected = state.rows.find((r) => r.transaction_id === state.selectedId);
  return [
    el("h1", {}, "Transactions"), el("div", { class: "sub" }, "Latest passes, newest first"),
    state.plazaError ? el("div", { class: "banner" }, state.plazaError) : null,
    el("div", { class: "filters" }, plazaSelect(f), el("label", {}, exOnly, "Exceptions only"), el("label", {}, "Payment", pay),
      el("label", {}, "From", from), el("label", {}, "To", to), limitSelect(f), el("span", { class: "spacer" }),
      el("button", { class: "primary", onclick: () => loadRows() }, "Refresh")),
    body(cols, state.rows, rowFn, empty), pager(f), selected ? transactionPanel(selected) : null,
  ];
}
function transactionPanel(r) {
  const kv = (k, v) => [el("div", {}, el("div", { class: "k" }, k), el("div", { class: "v" }, v))];
  const rules = Array.isArray(r.applied_rules) && r.applied_rules.length
    ? r.applied_rules.map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join("; ") : "none";
  return el("div", { class: "panel" },
    el("h2", {}, "Selected pass · " + fmtTime(r.transaction_time) + " · " + plazaName(r.plaza_id) + " · " + orDash(r.lane_id)),
    el("div", { class: "grid" },
      kv("Base fare", fmtMoney(r.base_amount, r.currency)), kv("Discount", fmtMoney(r.discount_amount, r.currency)),
      kv("Surcharge", fmtMoney(r.surcharge_amount, r.currency)), kv("Charged", fmtMoney(r.amount_charged, r.currency)),
      kv("Latency", r.latency_ms == null ? DASH : Math.round(Number(r.latency_ms)) + " ms"), kv("Rules applied", rules)),
    el("p", { class: "small" }, "Transaction " + r.transaction_id + " · trip " + orDash(r.trip_id) + " · vehicle " + orDash(r.vehicle_id) +
      " · tariff " + orDash(r.tariff_id) + " · created " + fmtTime(r.created_at)),
    r.is_exception ? el("a", { href: "#/exceptions?transaction_id=" + r.transaction_id }, "Pass flagged as exception → open in Exceptions view") : null);
}

/* ---- exceptions view */
function exceptionsView() {
  const f = state.ex;
  const seg = el("span", { class: "seg" }, [["open", "Open"], ["resolved", "Resolved"], ["all", "All"]].map(([v, t]) =>
    el("button", { class: f.status === v ? "on" : "", onclick: () => { f.status = v; f.offset = 0; loadRows(); } }, t)));
  const type = el("select", { onchange: () => { f.exception_type = type.value; f.offset = 0; loadRows(); } },
    el("option", { value: "" }, "Any"), Object.entries(LABELS.exception_type).map(([v, t]) => el("option", { value: v, selected: v === f.exception_type }, t)));
  const cols = [{ name: "Created" }, { name: "Type" }, { name: "Plaza" }, { name: "Lane" }, { name: "Details" }, { name: "Transaction" }, { name: "Status" }, { name: "" }];
  const empty = () => el("div", { class: "state" },
    f.status === "open" && !f.plaza_id && !f.exception_type && !f.transaction_id ? "No open exceptions. Everything has been handled." :
      f.status === "open" ? "No open exceptions match these filters." : "No exceptions recorded yet.", el("br"),
    f.status === "open" ? el("button", { onclick: () => { f.status = "resolved"; loadRows(); } }, "Show Resolved") : null);
  const rowFn = (r) => {
    const sel = r.exception_id === state.selectedId;
    return el("tr", { class: "row" + (sel ? " sel" : ""), onclick: () => {
      state.selectedId = sel ? null : r.exception_id;
      render(true);
    } },
      el("td", {}, fmtTime(r.created_at)), el("td", {}, label("exception_type", r.exception_type)), el("td", {}, plazaName(r.plaza_id)),
      el("td", {}, orDash(r.lane_id)), el("td", {}, orDash(r.details)),
      el("td", {}, r.transaction_id ? el("a", { href: "#/transactions?transaction_id=" + r.transaction_id, title: r.transaction_id, onclick: (e) => e.stopPropagation() }, "open pass ↗") : DASH),
      el("td", {}, badge(r.resolved ? "resolved" : "open", r.resolved ? "Resolved" : "Open")),
      el("td", {}, canWrite() && !r.resolved ? el("button", { onclick: (e) => { e.stopPropagation(); resolve(r); } }, "Resolve") : null,
        state.actionError[r.exception_id] ? el("div", { class: "err" }, state.actionError[r.exception_id]) : null));
  };
  const selected = state.rows.find((r) => r.exception_id === state.selectedId);
  const open = state.total !== null && f.status === "open" ? el("strong", { style: "color:var(--bad)" }, state.total + " open") : null;
  return [
    el("h1", {}, "Exceptions"), el("div", { class: "sub" }, "Passes that need a person, newest first"),
    state.plazaError ? el("div", { class: "banner" }, state.plazaError) : null,
    el("div", { class: "filters" }, el("label", {}, "Status", seg), plazaSelect(f), el("label", {}, "Type", type), limitSelect(f), open,
      f.transaction_id ? el("span", { class: "chip" }, "One pass only", el("button", { class: "link", onclick: () => go("exceptions") }, "✕")) : null,
      el("span", { class: "spacer" }), el("button", { class: "primary", onclick: () => loadRows() }, "Refresh")),
    body(cols, state.rows, rowFn, empty), pager(f), selected ? exceptionPanel(selected) : null,
  ];
}
function exceptionPanel(r) {
  const kv = (k, v) => el("div", {}, el("div", { class: "k" }, k), el("div", { class: "v" }, v));
  return el("div", { class: "panel" },
    el("h2", {}, "Selected exception · " + label("exception_type", r.exception_type) + " · " + plazaName(r.plaza_id) + " · " + orDash(r.lane_id)),
    el("div", { class: "grid" },
      kv("Created", fmtTime(r.created_at)),
      kv("Status", r.resolved ? "Resolved" : "Open"),
      kv("Details", orDash(r.details)),
      kv("Transaction", r.transaction_id || DASH)),
    state.actionError[r.exception_id] ? el("div", { class: "err" }, state.actionError[r.exception_id]) : null);
}

/* ------------------------------------------------------------ start */
async function boot() {
  readHash();
  render();
  if (!state.token) return;
  if (DASH_ROLES.includes(state.role)) { await loadPlazas(); startTimer(); loadRows(); }
}
state.token = load("token"); state.role = load("role"); state.username = load("username") || "";
boot();
