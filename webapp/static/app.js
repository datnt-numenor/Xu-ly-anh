"use strict";
/* Web demo nhóm 9 — giao diện gọi API Flask (webapp/app.py). */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const PALETTE = ["#ff845e", "#4ae3c2", "#f7cc55", "#bca2ff", "#6cbfff",
                 "#ff6fae", "#9be15d", "#ffa94d", "#63e6be", "#e599f7", "#74c0fc", "#ffd8a8"];
const colorFor = id => PALETTE[(Math.abs(id) - 1 + PALETTE.length * 100) % PALETTE.length];
const METHOD_NAMES = { nearest: "Nearest neighbor", hungarian: "Hungarian", kalman: "Kalman + Hungarian" };
const pad3 = n => String(n).padStart(3, "0");
const fmt = (v, d = 3) => v === "" || v == null ? "—" : (typeof v === "number" ? +v.toFixed(d) : v);

let SOURCES = [];
const sourceById = id => SOURCES.find(s => s.id === id);

/* ------------------------------------------------------------------ helpers */
function toast(message, info = false) {
  const el = $("#toast");
  el.textContent = message;
  el.className = "toast" + (info ? " info" : "");
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.hidden = true), info ? 2500 : 5000);
}

async function api(path, body) {
  const options = body === undefined ? {} : {
    method: "POST",
    headers: body instanceof FormData ? {} : { "Content-Type": "application/json" },
    body: body instanceof FormData ? body : JSON.stringify(body),
  };
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({ error: response.statusText }));
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function debounce(fn, ms = 180) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

const frameUrl = (source, i, noise = 0, seed = 1) =>
  `/api/frame/${source}/${i}.png` + (noise > 0 ? `?noise=${noise}&seed=${seed}` : "");

const frameSets = new Map();
/** Array of Image objects for every frame of a source (loaded lazily, cached). */
function frameSet(source, noise = 0) {
  const key = `${source}|${noise}`;
  if (!frameSets.has(key)) {
    const info = sourceById(source);
    const images = Array.from({ length: info.frames }, (_, i) => {
      const img = new Image();
      img.src = frameUrl(source, i, noise);
      return img;
    });
    frameSets.set(key, images);
  }
  return frameSets.get(key);
}

/** Size a canvas to an integer multiple of the frame size and return the scale. */
function fitCanvas(canvas, width, height, target = 960) {
  const scale = Math.max(1, Math.min(4, Math.floor(target / width)));
  if (canvas.width !== width * scale || canvas.height !== height * scale) {
    canvas.width = width * scale;
    canvas.height = height * scale;
  }
  return scale;
}

function bindOutput(input) {
  const out = $(`#${input.id}-out`);
  if (!out) return;
  const sync = () => (out.textContent = input.value);
  input.addEventListener("input", sync);
  sync();
}

function label(ctx, text, x, y, color, size = 12) {
  ctx.font = `600 ${size}px system-ui, sans-serif`;
  ctx.lineWidth = 3;
  ctx.strokeStyle = "rgba(0,0,0,.85)";
  ctx.strokeText(text, x, y);
  ctx.fillStyle = color;
  ctx.fillText(text, x, y);
}

function fillSourceSelects() {
  for (const select of $$(".source-select")) {
    const value = select.value;
    select.innerHTML = SOURCES.map(s =>
      `<option value="${s.id}">${s.title} · ${s.frames} frame${s.has_truth ? "" : " (không GT)"}</option>`).join("");
    if (value && sourceById(value)) select.value = value;
  }
}

/* ------------------------------------------------------------------ tabs */
const tabHooks = {};
function showTab(name) {
  if (!$(`#tab-${name}`)) name = "data";
  $$("#tabs button").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach(t => t.classList.toggle("active", t.id === `tab-${name}`));
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  tabHooks[name]?.();
}
$("#tabs").addEventListener("click", e => e.target.dataset.tab && showTab(e.target.dataset.tab));

/* ================================================================== 1. DATA */
const preview = { truths: {}, tick: 0, cards: [] };

async function buildScenarioCards() {
  const host = $("#scenario-cards");
  host.innerHTML = "";
  preview.cards = [];
  for (const s of SOURCES) {
    const card = document.createElement("div");
    card.className = "panel card";
    card.innerHTML = `<canvas></canvas>
      <h3>${s.title} <span class="badge">${s.frames} frame · ${s.width}×${s.height}</span></h3>
      <p>${s.note}</p>`;
    card.addEventListener("click", () => {
      $("#trk-source").value = s.id;
      showTab("track");
      runTrack();
    });
    host.append(card);
    preview.cards.push({ source: s, canvas: $("canvas", card), images: frameSet(s.id) });
    if (s.has_truth && !preview.truths[s.id]) {
      api(`/api/truth/${s.id}`).then(rows => (preview.truths[s.id] = rows));
    }
  }
}

function drawPreviews() {
  if (!$("#tab-data").classList.contains("active")) return;
  preview.tick++;
  for (const card of preview.cards) {
    const { source, canvas, images } = card;
    const i = preview.tick % source.frames;
    const scale = fitCanvas(canvas, source.width, source.height, 640);
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    if (images[i].complete) ctx.drawImage(images[i], 0, 0, canvas.width, canvas.height);
    for (const r of preview.truths[source.id] || []) {
      if (r.frame !== i || !r.visible) continue;
      ctx.strokeStyle = colorFor(r.id);
      ctx.lineWidth = 1.5;
      ctx.strokeRect(r.x * scale - 12, r.y * scale - 12, 24, 24);
    }
    label(ctx, `frame ${pad3(i)}`, 8, 18, "#fff", 11);
  }
}
setInterval(drawPreviews, 1000 / 12);

/* upload */
const drop = $("#drop");
["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", e => uploadFiles(e.dataTransfer.files));
$("#upload-input").addEventListener("change", e => uploadFiles(e.target.files));

async function uploadFiles(files) {
  if (!files?.length) return;
  const form = new FormData();
  [...files].forEach(f => form.append("files", f));
  const status = $("#upload-status");
  status.textContent = `Đang tải ${files.length} tệp và trích frame…`;
  try {
    const info = await api("/api/upload", form);
    SOURCES = await api("/api/sources");
    fillSourceSelects();
    await buildScenarioCards();
    status.textContent = `Đã thêm "${info.title}": ${info.frames} frame ${info.width}×${info.height}. Chọn nguồn này ở bước Phát hiện để chỉnh ngưỡng trước.`;
    $("#det-source").value = info.id;
    $("#trk-source").value = info.id;
    onDetSourceChange();
  } catch (err) {
    status.textContent = "";
    toast(err.message);
  }
}

/* ================================================================== 2. DETECT */
const DET_DEFAULTS = { threshold: 110, blur: 0, noise: 0, min_area: 35, max_area: 240, opening: true, connectivity: "8", otsu: false };

function detParams() {
  return {
    source: $("#det-source").value,
    frame: +$("#det-frame").value,
    noise: +$("#det-noise").value,
    threshold: $("#det-otsu").checked ? "otsu" : +$("#det-threshold").value,
    blur: +$("#det-blur").value,
    min_area: +$("#det-min-area").value,
    max_area: +$("#det-max-area").value,
    opening: $("#det-opening").checked,
    connectivity: +$("#det-connectivity").value,
  };
}

let detSeq = 0;
async function runDetect() {
  const params = detParams();
  const seq = ++detSeq;
  let result;
  try {
    result = await api("/api/detect", params);
  } catch (err) { return toast(err.message); }
  if (seq !== detSeq) return;
  if (params.threshold === "otsu") {
    $("#det-threshold").value = result.threshold;
    $("#det-threshold-out").textContent = `${result.threshold} (Otsu)`;
  }
  const info = sourceById(params.source);
  const input = await loadImage(frameUrl(params.source, params.frame, params.noise));
  const [raw, mask, smooth] = await Promise.all([loadImage(result.raw_mask), loadImage(result.mask),
    result.smoothed ? loadImage(result.smoothed) : null]);
  if (seq !== detSeq) return;

  const draw = (canvas, img, overlay) => {
    const scale = fitCanvas(canvas, info.width, info.height, 720);
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    const k = canvas.clientWidth ? canvas.width / canvas.clientWidth : 1;
    overlay?.(ctx, scale, size => Math.round(size * Math.max(1, k)));
  };
  const truthMarks = (ctx, s) => {
    for (const t of result.truth) {
      ctx.strokeStyle = "rgba(200,210,220,.7)";
      ctx.lineWidth = 1;
      ctx.strokeRect(t.x * s - 9, t.y * s - 9, 18, 18);
    }
  };
  draw($("#det-c-input"), input, (ctx, s, fs) => {
    truthMarks(ctx, s);
    result.spots.forEach((p, k) => {
      const c = PALETTE[k % PALETTE.length];
      ctx.strokeStyle = c; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(p.x * s, p.y * s, fs(8), 0, 7); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(p.x * s - 4, p.y * s); ctx.lineTo(p.x * s + 4, p.y * s);
      ctx.moveTo(p.x * s, p.y * s - 4); ctx.lineTo(p.x * s, p.y * s + 4); ctx.stroke();
      label(ctx, `(${p.x.toFixed(1)}, ${p.y.toFixed(1)})`, p.x * s + fs(11), p.y * s - fs(8), c, fs(12));
    });
  });
  $("#det-smooth-fig").hidden = !smooth;
  if (smooth) draw($("#det-c-smooth"), smooth);
  draw($("#det-c-raw"), raw);
  draw($("#det-c-mask"), mask, (ctx, s, fs) => {
    for (const c of result.components) {
      const color = c.accepted ? "#46d18b" : "#ff5d6c";
      const r = Math.max(4, Math.sqrt(c.area / Math.PI) * s + 3);
      ctx.strokeStyle = color; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(c.x * s, c.y * s, r, 0, 7); ctx.stroke();
      if (c.accepted || c.area >= 4) label(ctx, `${c.area}`, c.x * s + r + 2, c.y * s + 4, color, fs(12));
    }
  });
  drawHistogram($("#det-hist"), result.histogram, result.threshold, result.otsu);

  const rejected = result.component_count - result.spots.length;
  const truthCount = result.truth.length;
  const ok = info.has_truth ? result.spots.length === truthCount : null;
  $("#det-stats").innerHTML = [
    stat(result.spots.length, "spot giữ lại", ok === null ? "" : ok ? "good" : "bad"),
    info.has_truth ? stat(truthCount, "vật thật đang hiện") : "",
    stat(rejected, "vùng bị loại (diện tích)"),
    stat(result.threshold, params.threshold === "otsu" ? "ngưỡng Otsu" : "ngưỡng"),
    stat(result.otsu, "Otsu gợi ý"),
    stat(result.elapsed_ms.toFixed(2), "ms / frame"),
  ].join("");
  $("#det-components").innerHTML = result.components.length ? `<div class="table-wrap"><table>
    <tr><th>#</th><th>x</th><th>y</th><th>diện tích (px)</th><th>kết quả</th></tr>
    ${result.components.map((c, k) => `<tr><td>${k + 1}</td><td>${c.x.toFixed(2)}</td><td>${c.y.toFixed(2)}</td>
      <td>${c.area}</td><td>${c.accepted ? "giữ" : c.area < params.min_area ? "loại: nhỏ" : "loại: lớn"}</td></tr>`).join("")}
    </table></div>${result.component_count > result.components.length ? `<p class="muted small">Chỉ hiện 200 / ${result.component_count} vùng.</p>` : ""}`
    : `<p class="muted">Không có vùng nào sau phân ngưỡng.</p>`;
}

const stat = (value, text, cls = "") => `<div class="stat ${cls}"><b>${value}</b><span>${text}</span></div>`;

function drawHistogram(canvas, hist, threshold, otsu) {
  const w = canvas.clientWidth * devicePixelRatio, h = canvas.clientHeight * devicePixelRatio;
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext("2d");
  const max = Math.log1p(Math.max(...hist));
  const bw = w / 256;
  ctx.fillStyle = "#6f8297";
  hist.forEach((v, i) => {
    const bh = (Math.log1p(v) / max) * (h - 14);
    ctx.fillStyle = i > threshold ? "#e4ebf2" : "#53657a";
    ctx.fillRect(i * bw, h - bh, Math.max(1, bw - .3), bh);
  });
  const line = (x, color, dash) => {
    ctx.strokeStyle = color; ctx.lineWidth = 2 * devicePixelRatio; ctx.setLineDash(dash);
    ctx.beginPath(); ctx.moveTo((x + .5) * bw, 0); ctx.lineTo((x + .5) * bw, h); ctx.stroke();
    ctx.setLineDash([]);
  };
  line(otsu, "#f7cc55", [6, 4]);
  line(threshold, "#4ae3c2", []);
}

function onDetSourceChange() {
  const info = sourceById($("#det-source").value);
  const slider = $("#det-frame");
  slider.max = info.frames - 1;
  if (+slider.value > info.frames - 1) slider.value = Math.min(21, info.frames - 1);
  $("#det-frame-out").textContent = slider.value;
  runDetect();
}

function initDetect() {
  const rerun = debounce(runDetect, 120);
  $$("#det-controls input, #det-controls select").forEach(el => {
    if (el.type === "range") bindOutput(el);
    if (el.id === "det-source") return el.addEventListener("change", onDetSourceChange);
    el.addEventListener("input", () => {
      if (el.id === "det-threshold") $("#det-otsu").checked = false;
      rerun();
    });
  });
  $("#det-reset").addEventListener("click", () => {
    $("#det-threshold").value = DET_DEFAULTS.threshold;
    $("#det-blur").value = DET_DEFAULTS.blur;
    $("#det-noise").value = DET_DEFAULTS.noise;
    $("#det-min-area").value = DET_DEFAULTS.min_area;
    $("#det-max-area").value = DET_DEFAULTS.max_area;
    $("#det-opening").checked = true;
    $("#det-otsu").checked = false;
    $("#det-connectivity").value = "8";
    $$("#det-controls input[type=range]").forEach(el => el.dispatchEvent(new Event("input")));
  });
  $("#det-to-track").addEventListener("click", () => {
    const p = detParams();
    $("#trk-source").value = p.source;
    $("#trk-noise").value = p.noise;
    $("#trk-otsu").checked = p.threshold === "otsu";
    $("#trk-threshold").value = $("#det-threshold").value;
    $("#trk-blur").value = p.blur;
    $("#trk-min-area").value = p.min_area;
    $("#trk-max-area").value = p.max_area;
    $$("#trk-controls input[type=range]").forEach(el => $(`#${el.id}-out`) && ($(`#${el.id}-out`).textContent = el.value));
    showTab("track");
    runTrack();
  });
  tabHooks.detect = () => { if (!$("#det-stats").innerHTML) onDetSourceChange(); };
}

/* ================================================================== 3. TRACK */
const trk = { data: null, frame: 0, playing: false, timer: null, views: [] };

function trkParams() {
  return {
    source: $("#trk-source").value,
    noise: +$("#trk-noise").value,
    methods: $$("input[name=trk-method]:checked").map(el => el.value),
    gate: +$("#trk-gate").value,
    max_missing: +$("#trk-missing").value,
    solver: $("#trk-solver").value,
    threshold: $("#trk-otsu").checked ? "otsu" : +$("#trk-threshold").value,
    blur: +$("#trk-blur").value,
    min_area: +$("#trk-min-area").value,
    max_area: +$("#trk-max-area").value,
  };
}

let trkSeq = 0;
async function runTrack() {
  const params = trkParams();
  if (!params.methods.length) return toast("Chọn ít nhất một phương pháp.");
  const seq = ++trkSeq;
  $("#trk-status").textContent = "Đang chạy…";
  let data;
  try {
    data = await api("/api/track", params);
  } catch (err) {
    $("#trk-status").textContent = "";
    return toast(err.message);
  }
  if (seq !== trkSeq) return;
  data.params = params;
  data.images = frameSet(params.source, params.noise);
  prepareTrack(data);
  trk.data = data;
  const slider = $("#trk-frame");
  slider.max = data.source.frames - 1;
  trk.frame = Math.min(trk.frame, data.source.frames - 1);
  buildViews();
  renderMetrics();
  $("#trk-status").textContent = `Phát hiện ${data.detect_ms.toFixed(2)} ms/frame`;
  setFrame(trk.frame);
}

function groupBy(rows, key) {
  const map = new Map();
  for (const r of rows) {
    const k = key(r);
    if (!map.has(k)) map.set(k, []);
    map.get(k).push(r);
  }
  return map;
}

function prepareTrack(data) {
  data.truthByFrame = groupBy(data.truth, r => r[0]);
  data.truthPos = new Map(data.truth.map(r => [`${r[0]}|${r[1]}`, r]));
  for (const [method, res] of Object.entries(data.results)) {
    res.name = method;
    res.obsByFrame = groupBy(res.observations, r => r[0]);
    res.statesByFrame = groupBy(res.states, r => r[0]);
    res.byTrack = groupBy(res.observations, r => r[1]);
    res.switchByFrame = groupBy(res.switches || [], s => s.frame);
    // Timeline rows: every ID with its first frame, observed frames and predicted-only frames.
    const ids = [...res.byTrack.keys()].sort((a, b) => res.byTrack.get(a)[0][0] - res.byTrack.get(b)[0][0] || a - b);
    const predicted = groupBy(res.states.filter(s => !s[6]), s => s[1]);
    res.timeline = ids.map(id => ({ id, obs: res.byTrack.get(id).map(r => r[0]), pred: (predicted.get(id) || []).map(s => s[0]) }));
  }
}

function buildViews() {
  const host = $("#trk-views");
  host.innerHTML = "";
  trk.views = orderedResults().map(res => {
    const el = document.createElement("figure");
    el.className = "panel view";
    el.innerHTML = `<header><b>${METHOD_NAMES[res.name]}</b><span class="kpis"></span></header>
      <canvas class="frame"></canvas><canvas class="timeline"></canvas>
      <div class="tl-label">Dòng thời gian: mỗi hàng là một ID · đặc = có quan sát · nhạt = đang dự đoán · đỏ = đổi ID</div>`;
    host.append(el);
    const view = { res, el, canvas: $("canvas.frame", el), timeline: $("canvas.timeline", el), kpis: $(".kpis", el) };
    view.timeline.addEventListener("click", e => {
      const rect = view.timeline.getBoundingClientRect();
      setFrame(Math.round(((e.clientX - rect.left) / rect.width) * (trk.data.source.frames - 1)));
    });
    const m = res.metrics;
    view.kpis.innerHTML = m ? `IDF1 <em>${fmt(m.idf1)}</em> · MOTA <em>${fmt(m.mota)}</em> · đổi ID <em>${m.id_switches}</em> · ${m.track_ids} ID`
      : `${res.timeline.length} ID`;
    return view;
  });
}

function drawView(view, f) {
  const data = trk.data, res = view.res, src = data.source;
  const scale = fitCanvas(view.canvas, src.width, src.height, trk.views.length > 1 ? 640 : 960);
  const ctx = view.canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  const img = data.images[f];
  if (img.complete && img.naturalWidth) ctx.drawImage(img, 0, 0, view.canvas.width, view.canvas.height);
  else { ctx.fillStyle = "#000"; ctx.fillRect(0, 0, view.canvas.width, view.canvas.height); img.onload = () => trk.frame === f && drawView(view, f); }
  const X = v => v * scale;
  const show = id => $(`#${id}`).checked;
  const k = view.canvas.clientWidth ? view.canvas.width / view.canvas.clientWidth : 1;  // canvas px per CSS px
  const ring = Math.max(6, 3 * scale, 7 * k);
  const fs = size => Math.round(size * Math.max(1, k));

  if (show("show-truth")) {
    for (const t of data.truthByFrame.get(f) || []) {
      ctx.strokeStyle = "rgba(220,230,240,.75)"; ctx.lineWidth = 1;
      ctx.strokeRect(X(t[2]) - ring - 4, X(t[3]) - ring - 4, 2 * ring + 8, 2 * ring + 8);
    }
  }
  if (show("show-dets")) {
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5;
    for (const [x, y] of data.detections[f] || []) {
      const a = fs(5);
      ctx.beginPath(); ctx.moveTo(X(x) - a, X(y)); ctx.lineTo(X(x) + a, X(y));
      ctx.moveTo(X(x), X(y) - a); ctx.lineTo(X(x), X(y) + a); ctx.stroke();
    }
  }
  if (show("show-trails")) {
    for (const [id, rows] of res.byTrack) {
      const recent = rows.filter(r => r[0] <= f && r[0] > f - 30);
      if (recent.length < 2) continue;
      ctx.strokeStyle = colorFor(id); ctx.lineWidth = Math.max(2, scale * .8, 2 * k); ctx.globalAlpha = .85;
      ctx.beginPath();
      for (let k = 1; k < recent.length; k++) {
        if (recent[k][0] !== recent[k - 1][0] + 1) continue;
        ctx.moveTo(X(recent[k - 1][2]), X(recent[k - 1][3]));
        ctx.lineTo(X(recent[k][2]), X(recent[k][3]));
      }
      ctx.stroke(); ctx.globalAlpha = 1;
    }
  }
  if (show("show-pred")) {
    for (const s of res.statesByFrame.get(f) || []) {
      if (s[6]) continue;
      const c = colorFor(s[1]);
      ctx.strokeStyle = c; ctx.lineWidth = 2; ctx.setLineDash([4, 3]);
      ctx.beginPath(); ctx.arc(X(s[2]), X(s[3]), ring, 0, 7); ctx.stroke(); ctx.setLineDash([]);
      label(ctx, `ID ${s[1]}?`, X(s[2]) + ring + 3, X(s[3]) - ring, c, fs(12));
    }
  }
  for (const [, id, x, y] of res.obsByFrame.get(f) || []) {
    const c = colorFor(id);
    ctx.strokeStyle = c; ctx.lineWidth = 2.5;
    ctx.beginPath(); ctx.arc(X(x), X(y), ring, 0, 7); ctx.stroke();
    label(ctx, `ID ${id}`, X(x) + ring + 3, X(y) - ring, c, fs(13));
  }
  for (const s of res.switchByFrame.get(f) || []) {
    const t = data.truthPos.get(`${f}|${s.object}`);
    if (!t) continue;
    ctx.strokeStyle = "#ff5d6c"; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.arc(X(t[2]), X(t[3]), ring + 9, 0, 7); ctx.stroke();
    label(ctx, `ĐỔI ID → ${s.track}`, X(t[2]) - ring - 10, X(t[3]) + ring + fs(24), "#ff5d6c", fs(13));
  }
  ctx.fillStyle = "rgba(16,25,35,.85)";
  ctx.fillRect(0, 0, view.canvas.width, fs(22));
  label(ctx, `${res.name.toUpperCase()}  |  FRAME ${pad3(f)}  |  ${(res.obsByFrame.get(f) || []).length} track hiện`, 8, fs(16), "#fff", fs(12));
  drawTimeline(view, f);
}

function drawTimeline(view, f) {
  const res = view.res, frames = trk.data.source.frames, canvas = view.timeline;
  const rows = res.timeline.length;
  const rowH = rows > 20 ? 4 : rows > 10 ? 7 : 12;
  const cssH = Math.max(40, rows * rowH + 8);
  canvas.style.height = cssH + "px";
  const w = canvas.clientWidth * devicePixelRatio, h = cssH * devicePixelRatio;
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext("2d");
  const cw = w / frames, rh = (h - 8 * devicePixelRatio) / Math.max(rows, 1);
  res.timeline.forEach((row, k) => {
    const y = 4 * devicePixelRatio + k * rh;
    ctx.fillStyle = colorFor(row.id);
    ctx.globalAlpha = .3;
    for (const fr of row.pred) ctx.fillRect(fr * cw, y + 1, cw, rh - 2);
    ctx.globalAlpha = 1;
    for (const fr of row.obs) ctx.fillRect(fr * cw, y + 1, Math.max(1, cw - .5), rh - 2);
  });
  ctx.fillStyle = "#ff5d6c";
  for (const s of res.switches || []) ctx.fillRect(s.frame * cw, 0, Math.max(2, cw * .35), h);
  ctx.fillStyle = "#fff";
  ctx.fillRect((f + .5) * cw - devicePixelRatio, 0, 2 * devicePixelRatio, h);
}

function setFrame(f) {
  if (!trk.data) return;
  f = Math.max(0, Math.min(trk.data.source.frames - 1, f));
  trk.frame = f;
  $("#trk-frame").value = f;
  $("#trk-frame-out").textContent = pad3(f);
  trk.views.forEach(v => drawView(v, f));
}

function setPlaying(on) {
  trk.playing = on;
  $("#play").textContent = on ? "❚❚" : "▶";
  clearInterval(trk.timer);
  if (on) {
    trk.timer = setInterval(() => {
      if (!$("#tab-track").classList.contains("active")) return setPlaying(false);
      setFrame((trk.frame + 1) % trk.data.source.frames);
    }, 1000 / +$("#trk-fps").value);
  }
}

/** Results in the fixed order nearest → hungarian → kalman (JSON keys arrive sorted). */
const orderedResults = () => Object.keys(METHOD_NAMES).filter(m => trk.data.results[m]).map(m => trk.data.results[m]);

function renderMetrics() {
  const results = orderedResults();
  if (!results[0].metrics) {
    $("#trk-metrics").innerHTML = `<p class="muted">Nguồn này không có ground truth nên không tính được chỉ số. Số ID tạo ra: ${results.map(r => `${METHOD_NAMES[r.name]} = ${r.timeline.length}`).join(", ")}.</p>`;
    $("#trk-switches").innerHTML = "";
    return;
  }
  const cols = [
    ["idf1", "IDF1", "max"], ["mota", "MOTA", "max"], ["id_switches", "Đổi ID", "min"], ["track_ids", "Số ID", "min"],
    ["matched", "Khớp", "max"], ["missed", "Bỏ sót", "min"], ["false_positive", "Phát hiện thừa", "min"],
    ["matched_detection_rmse_px", "RMSE (px)", "min"],
  ];
  const best = {};
  for (const [key, , dir] of cols) {
    const vals = results.map(r => r.metrics[key]).filter(v => v !== "");
    best[key] = vals.length ? (dir === "max" ? Math.max(...vals) : Math.min(...vals)) : null;
  }
  $("#trk-metrics").innerHTML = `<div class="table-wrap"><table>
    <tr><th>Phương pháp</th>${cols.map(c => `<th>${c[1]}</th>`).join("")}<th>Theo dõi (ms/frame)</th></tr>
    ${results.map(r => `<tr><td>${METHOD_NAMES[r.name]}</td>${cols.map(([k]) =>
      `<td class="${results.length > 1 && r.metrics[k] === best[k] ? "best" : ""}">${fmt(r.metrics[k], 4)}</td>`).join("")}
      <td>${r.track_ms.toFixed(3)}</td></tr>`).join("")}
  </table></div>`;
  $("#trk-switches").innerHTML = results.filter(r => r.switches.length).map(r =>
    `<div class="switch-list"><span class="muted small">${METHOD_NAMES[r.name]} đổi ID tại:</span>
     ${r.switches.slice(0, 40).map(s => `<button data-frame="${s.frame}">frame ${s.frame} · vật ${s.object}→ID ${s.track}</button>`).join("")}
     ${r.switches.length > 40 ? `<span class="muted small">… +${r.switches.length - 40}</span>` : ""}</div>`).join("");
}

const PRESETS = {
  crossing: { source: "crossing", methods: ["nearest", "hungarian", "kalman"], blur: 0, noise: 0, frame: 17, truth: true },
  dense: { source: "dense", methods: ["nearest", "hungarian"], blur: 0, noise: 0, frame: 15, truth: false },
  noisy: { source: "noisy", methods: ["nearest", "kalman"], blur: 0, noise: 0, frame: 18, dets: true },
  "noisy-blur": { source: "noisy", methods: ["nearest", "kalman"], blur: 1.5, noise: 0, frame: 18, dets: true },
};

function applyPreset(name) {
  const p = PRESETS[name];
  if (!sourceById(p.source)) return;
  $("#trk-source").value = p.source;
  $$("input[name=trk-method]").forEach(el => (el.checked = p.methods.includes(el.value)));
  Object.entries({ "trk-gate": 24, "trk-missing": 5, "trk-threshold": 110, "trk-blur": p.blur, "trk-noise": p.noise })
    .forEach(([id, v]) => { $(`#${id}`).value = v; $(`#${id}-out`).textContent = v; });
  $("#trk-otsu").checked = false;
  $("#trk-min-area").value = 35; $("#trk-max-area").value = 240;
  $("#show-truth").checked = !!p.truth;
  $("#show-dets").checked = !!p.dets;
  trk.frame = p.frame;
  setPlaying(false);
  runTrack();
}

function initTrack() {
  const rerun = debounce(runTrack, 250);
  $$("#trk-controls input, #trk-controls select").forEach(el => {
    if (el.type === "range") bindOutput(el);
    if (el.id.startsWith("show-")) return el.addEventListener("change", () => setFrame(trk.frame));
    el.addEventListener(el.type === "range" ? "input" : "change", () => {
      if (el.id === "trk-threshold") $("#trk-otsu").checked = false;
      rerun();
    });
  });
  $("#trk-frame").addEventListener("input", e => setFrame(+e.target.value));
  $("#play").addEventListener("click", () => setPlaying(!trk.playing));
  $("#step-back").addEventListener("click", () => { setPlaying(false); setFrame(trk.frame - 1); });
  $("#step-fwd").addEventListener("click", () => { setPlaying(false); setFrame(trk.frame + 1); });
  $("#trk-fps").addEventListener("change", () => trk.playing && setPlaying(true));
  $("#trk-switches").addEventListener("click", e => e.target.dataset.frame && (setPlaying(false), setFrame(+e.target.dataset.frame)));
  $$("[data-preset]").forEach(b => b.addEventListener("click", () => applyPreset(b.dataset.preset)));
  document.addEventListener("keydown", e => {
    if (!$("#tab-track").classList.contains("active") || !trk.data) return;
    if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName) && e.target.type !== "range") return;
    if (e.key === " ") { e.preventDefault(); setPlaying(!trk.playing); }
    if (e.key === "ArrowRight") { e.preventDefault(); setPlaying(false); setFrame(trk.frame + 1); }
    if (e.key === "ArrowLeft") { e.preventDefault(); setPlaying(false); setFrame(trk.frame - 1); }
  });
  window.addEventListener("resize", debounce(() => setFrame(trk.frame), 150));
  tabHooks.track = () => { if (!trk.data) applyPreset("crossing"); else setFrame(trk.frame); };
}

/* ================================================================== 4. ASSOCIATION */
const assoc = { tracks: [], spots: [], result: null, drag: null, W: 520, H: 320 };

const ASSOC_PRESETS = {
  // Two convoys 40 px apart moving 25 px/frame (step > half the spacing, as in data/dense
  // scaled 2.5x): greedy gives the leader's spot to the follower.
  dense: () => ({
    gate: 50,
    tracks: [[100, 100], [140, 100], [180, 100], [420, 220], [380, 220], [340, 220]],
    spots: [[125, 100], [165, 100], [205, 100], [395, 220], [355, 220], [315, 220]],
  }),
  cross: () => ({ gate: 40, tracks: [[220, 150], [300, 175]], spots: [[268, 172], [252, 150]] }),
  random: () => {
    const n = 3 + Math.floor(Math.random() * 3);
    const tracks = Array.from({ length: n }, () => [60 + Math.random() * 400, 50 + Math.random() * 220]);
    const spots = tracks.map(([x, y]) => [x + (Math.random() - .5) * 50, y + (Math.random() - .5) * 50]);
    if (Math.random() < .5) spots.pop();
    return { tracks, spots };
  },
};

function assocLoad(name) {
  const p = ASSOC_PRESETS[name]();
  assoc.tracks = p.tracks.map(([x, y]) => ({ x, y }));
  assoc.spots = p.spots.map(([x, y]) => ({ x, y }));
  if (p.gate) { $("#assoc-gate").value = p.gate; $("#assoc-gate-out").textContent = p.gate; }
  runAssoc();
}

let assocSeq = 0;
async function runAssoc() {
  const seq = ++assocSeq;
  try {
    const result = await api("/api/associate", {
      tracks: assoc.tracks.map(p => [p.x, p.y]), spots: assoc.spots.map(p => [p.x, p.y]), gate: +$("#assoc-gate").value,
    });
    if (seq !== assocSeq) return;
    assoc.result = result;
  } catch (err) { return toast(err.message); }
  drawAssoc();
}

function drawAssoc() {
  const r = assoc.result, gate = +$("#assoc-gate").value;
  for (const method of ["nearest", "hungarian"]) {
    const canvas = $(`#assoc-c-${method}`);
    const dpr = devicePixelRatio;
    canvas.width = assoc.W * dpr; canvas.height = assoc.H * dpr;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.strokeStyle = "#1a2330"; ctx.lineWidth = 1;
    for (let x = 0; x < assoc.W; x += 20) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, assoc.H); ctx.stroke(); }
    for (let y = 0; y < assoc.H; y += 20) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(assoc.W, y); ctx.stroke(); }
    const matches = r ? r[method].matches : [];
    const mt = new Map(matches.map(([i, j]) => [i, j]));
    const ms = new Set(matches.map(([, j]) => j));
    assoc.tracks.forEach((t, i) => {
      const c = PALETTE[i % PALETTE.length];
      ctx.strokeStyle = c; ctx.globalAlpha = .35; ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.arc(t.x, t.y, gate, 0, 7); ctx.stroke(); ctx.setLineDash([]); ctx.globalAlpha = 1;
      if (mt.has(i)) {
        const s = assoc.spots[mt.get(i)];
        ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(t.x, t.y); ctx.lineTo(s.x, s.y); ctx.stroke();
      }
    });
    assoc.spots.forEach((s, j) => {
      ctx.fillStyle = ms.has(j) ? "#e4ebf2" : "#ff5d6c";
      ctx.fillRect(s.x - 6, s.y - 6, 12, 12);
      label(ctx, `S${j + 1}${ms.has(j) ? "" : " → track mới"}`, s.x + 9, s.y + 16, ms.has(j) ? "#c9d3de" : "#ff5d6c", 11);
    });
    assoc.tracks.forEach((t, i) => {
      const c = PALETTE[i % PALETTE.length];
      ctx.fillStyle = c; ctx.beginPath(); ctx.arc(t.x, t.y, 8, 0, 7); ctx.fill();
      ctx.strokeStyle = "#000"; ctx.lineWidth = 1.5; ctx.stroke();
      label(ctx, `T${i + 1}${mt.has(i) ? "" : " (mất)"}`, t.x - 10, t.y - 13, c, 12);
    });
    if (r) {
      const info = r[method];
      $(`#assoc-${method[0]}-info`).textContent = `${info.matches.length} cặp · tổng ${info.cost.toFixed(1)} px`;
    }
  }
  if (!r) return;
  const n = new Set(r.nearest.matches.map(([i, j]) => `${i}|${j}`));
  const h = new Set(r.hungarian.matches.map(([i, j]) => `${i}|${j}`));
  $("#assoc-matrix").innerHTML = assoc.tracks.length && assoc.spots.length ? `<div class="table-wrap"><table class="matrix">
    <tr><th></th>${assoc.spots.map((_, j) => `<th>S${j + 1}</th>`).join("")}</tr>
    ${r.distances.map((row, i) => `<tr><th class="row" style="color:${PALETTE[i % PALETTE.length]}">T${i + 1}</th>${row.map((d, j) =>
      `<td class="${d > gate ? "out" : ""} ${n.has(`${i}|${j}`) ? "n" : ""} ${h.has(`${i}|${j}`) ? "h" : ""}">${d > gate ? `(${d.toFixed(0)})` : d.toFixed(1)}</td>`).join("")}</tr>`).join("")}
  </table></div>` : `<p class="muted">Thêm track và spot để xem ma trận.</p>`;
  const diff = r.nearest.matches.length !== r.hungarian.matches.length || Math.abs(r.nearest.cost - r.hungarian.cost) > 1e-6;
  $("#assoc-check").innerHTML = (diff
    ? `<b style="color:var(--warn)">Hai cách ghép khác nhau.</b> Nearest: ${r.nearest.matches.length} cặp, tổng ${r.nearest.cost} px · Hungarian: ${r.hungarian.matches.length} cặp, tổng ${r.hungarian.cost} px. `
    : "Hai cách ghép cho cùng kết quả. ") +
    `Giá trị trong ngoặc vượt gate nên bị cấm. Hungarian tự cài ${r.scipy_agrees ? "trùng" : "KHÁC"} kết quả SciPy <code>linear_sum_assignment</code>.`;
}

function initAssoc() {
  const gate = $("#assoc-gate");
  bindOutput(gate);
  gate.addEventListener("input", debounce(runAssoc, 60));
  $$("[data-assoc]").forEach(b => b.addEventListener("click", () => {
    const a = b.dataset.assoc;
    if (a === "add-track" && assoc.tracks.length < 12) assoc.tracks.push({ x: 40 + Math.random() * 440, y: 40 + Math.random() * 240 });
    else if (a === "add-spot" && assoc.spots.length < 12) assoc.spots.push({ x: 40 + Math.random() * 440, y: 40 + Math.random() * 240 });
    else if (a === "clear") { assoc.tracks = []; assoc.spots = []; }
    else if (ASSOC_PRESETS[a]) return assocLoad(a);
    runAssoc();
  }));
  for (const canvas of $$("canvas.assoc")) {
    const pos = e => {
      const rect = canvas.getBoundingClientRect();
      return { x: (e.clientX - rect.left) * assoc.W / rect.width, y: (e.clientY - rect.top) * assoc.H / rect.height };
    };
    canvas.addEventListener("pointerdown", e => {
      const p = pos(e);
      const hit = (list, kind) => list.findIndex(q => Math.hypot(q.x - p.x, q.y - p.y) < 14) >= 0 &&
        { kind, index: list.findIndex(q => Math.hypot(q.x - p.x, q.y - p.y) < 14) };
      assoc.drag = hit(assoc.tracks, "tracks") || hit(assoc.spots, "spots") || null;
      if (assoc.drag) { canvas.setPointerCapture(e.pointerId); canvas.style.cursor = "grabbing"; }
    });
    canvas.addEventListener("pointermove", e => {
      if (!assoc.drag) return;
      const p = pos(e);
      const item = assoc[assoc.drag.kind][assoc.drag.index];
      item.x = Math.max(5, Math.min(assoc.W - 5, p.x));
      item.y = Math.max(5, Math.min(assoc.H - 5, p.y));
      drawAssoc();
      runAssocThrottled();
    });
    canvas.addEventListener("pointerup", () => { assoc.drag = null; canvas.style.cursor = ""; runAssoc(); });
  }
  tabHooks.assoc = () => { if (!assoc.result) assocLoad("dense"); };
}
const runAssocThrottled = debounce(runAssoc, 30);

/* ================================================================== 5. RESULTS */
let saved = null;
const FIGURE_NOTES = {
  "idf1_methods.png": "IDF1 của 3 phương pháp, Python và TrackMate",
  "noise_robustness.png": "IDF1 và RMSE khi tăng nhiễu, có/không làm mượt",
  "noisy_detectors.png": "Detector Python vs Threshold/LoG của TrackMate trên noisy",
  "parameter_sweep.png": "Ảnh hưởng của gate và max_missing",
  "trajectories.png": "Quỹ đạo x theo frame, dấu x là lần đổi ID",
};
const SHOT_NOTES = {
  "01_hyperstack": "Ảnh đã mở dạng hyperstack (phóng 200 %)", "02_Start": "Hiệu chuẩn kích thước pixel và frame interval",
  "03_ChooseDetector": "Chọn detector", "04_Preview_image": "Preview: spot được khoanh ở frame 21",
  "05_ConfigureDetector": "Cấu hình detector", "06_ExecuteDetection": "Chạy phát hiện (log)",
  "07_InitialFiltering": "Lọc ban đầu", "08_SpotFilter": "Lọc spot theo Quality", "09_ChooseTracker": "Chọn tracker",
  "10_ConfigureTracker": "Cấu hình tracker", "11_ExecuteTracking": "Chạy tracking, số track tìm được",
  "12_TrackFilter": "Lọc track", "13_ConfigureViews": "Tùy chọn hiển thị", "14_TracksTable": "Bảng Tracks",
  "15_Overlay": "Quỹ đạo vẽ trên ảnh",
};
const shots = { set: null, index: 0 };

async function initResults() {
  if (saved) return;
  try { saved = await api("/api/results"); } catch (err) { return toast(err.message); }
  renderPivot();
  $("#res-metric").addEventListener("change", renderPivot);

  const scenarios = Object.keys(saved.videos);
  $("#res-video-scenario").innerHTML = scenarios.map(s => `<option>${s}</option>`).join("");
  $("#res-video-scenario").addEventListener("change", renderVideos);
  renderVideos();

  const sets = Object.keys(saved.screenshots);
  $("#res-shot-set").innerHTML = sets.map(s => `<option>${s}</option>`).join("");
  $("#res-shot-set").addEventListener("change", e => { shots.set = e.target.value; shots.index = 0; renderShot(); });
  shots.set = sets[0];
  $("#shot-prev").addEventListener("click", () => { shots.index--; renderShot(); });
  $("#shot-next").addEventListener("click", () => { shots.index++; renderShot(); });
  $("#shot-dots").addEventListener("click", e => { if (e.target.dataset.i) { shots.index = +e.target.dataset.i; renderShot(); } });
  if (shots.set) renderShot();

  const stages = [...new Set(saved.timing.map(r => r.stage))];
  const timingScen = [...new Set(saved.timing.map(r => r.scenario))];
  const tv = new Map(saved.timing.map(r => [`${r.scenario}|${r.stage}`, r.median_ms_per_frame]));
  $("#res-timing").innerHTML = `<div class="table-wrap"><table><tr><th>Kịch bản</th>${stages.map(s => `<th>${s}</th>`).join("")}</tr>
    ${timingScen.map(s => `<tr><td>${s}</td>${stages.map(st => `<td>${tv.has(`${s}|${st}`) ? (+tv.get(`${s}|${st}`)).toFixed(3) : "—"}</td>`).join("")}</tr>`).join("")}
  </table></div>`;

  const gallery = (host, list) => {
    host.innerHTML = list.map(p => {
      const name = p.split("/").pop();
      const note = FIGURE_NOTES[name] || name.replace(/\.png$/, "").replaceAll("_", " ");
      return `<figure data-src="/results/${p}" data-note="${note}"><img loading="lazy" src="/results/${p}" alt="${note}"><figcaption>${note}</figcaption></figure>`;
    }).join("");
  };
  gallery($("#res-figures"), saved.figures);
  gallery($("#res-report"), saved.report_figures);
}

function renderPivot() {
  const metric = $("#res-metric").value;
  const higher = ["idf1", "mota"].includes(metric);
  const cols = [
    ["python", "nearest", "Py Nearest"], ["python", "hungarian", "Py Hungarian"], ["python", "kalman", "Py Kalman"],
    ["python", "kalman_blur", "Py Kalman + blur"],
    ["fiji", "nearest", "TM Nearest"], ["fiji", "lap", "TM LAP"], ["fiji", "kalman", "TM Kalman"], ["fiji", "log_kalman", "TM LoG + Kalman"],
  ];
  const lookup = new Map();
  for (const src of ["python", "fiji"]) for (const r of saved[src]) lookup.set(`${src}|${r.scenario}|${r.method}`, r[metric]);
  const scenarios = [...new Set(saved.python.map(r => r.scenario))];
  const cell = v => {
    if (v === undefined || v === "") return `<td class="muted">—</td>`;
    const x = +v;
    let style = "";
    if (higher) style = `background: hsla(${Math.round(x * 140)}, 70%, 45%, .28)`;
    else if (metric === "id_switches") style = x === 0 ? "background: hsla(140,70%,45%,.25)" : `background: hsla(0,70%,50%,${Math.min(.45, .1 + x / 60)})`;
    return `<td style="${style}">${+x.toFixed(4)}</td>`;
  };
  $("#res-pivot").innerHTML = `<div class="table-wrap"><table><tr><th>Kịch bản</th>${cols.map(c => `<th>${c[2]}</th>`).join("")}</tr>
    ${scenarios.map(s => `<tr><td>${s}</td>${cols.map(([src, m]) => cell(lookup.get(`${src}|${s}|${m}`))).join("")}</tr>`).join("")}
  </table></div>`;
}

function renderVideos() {
  const s = $("#res-video-scenario").value;
  const items = [[`/media/${s}.mp4`, "Video đầu vào"], ...saved.videos[s].map(p => [`/results/${p}`, p.split("/").pop().replace(".mp4", "")])];
  $("#res-videos").innerHTML = items.map(([src, name]) =>
    `<figure><figcaption>${name}</figcaption><video src="${src}" controls loop muted playsinline preload="metadata"></video></figure>`).join("");
}

function renderShot() {
  const list = saved.screenshots[shots.set] || [];
  if (!list.length) return;
  shots.index = (shots.index + list.length) % list.length;
  const path = list[shots.index];
  const key = path.split("/").pop().replace(".png", "");
  $("#shot-img").src = `/results/${path}`;
  $("#shot-caption").textContent = `${shots.index + 1}/${list.length} · ${SHOT_NOTES[key] || key}`;
  $("#shot-dots").innerHTML = list.map((_, i) => `<button data-i="${i}" class="${i === shots.index ? "active" : ""}">${i + 1}</button>`).join("");
}

document.addEventListener("click", e => {
  const fig = e.target.closest(".gallery figure");
  const box = $("#lightbox");
  if (fig) {
    $("img", box).src = fig.dataset.src;
    $("p", box).textContent = fig.dataset.note;
    box.hidden = false;
  } else if (e.target.closest("#lightbox")) box.hidden = true;
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape") $("#lightbox").hidden = true;
  if ($("#tab-results").classList.contains("active") && saved && !["INPUT", "SELECT"].includes(e.target.tagName)) {
    if (e.key === "ArrowRight") { shots.index++; renderShot(); }
    if (e.key === "ArrowLeft") { shots.index--; renderShot(); }
  }
});

/* ================================================================== boot */
(async function boot() {
  try {
    SOURCES = await api("/api/sources");
  } catch (err) {
    return toast("Không kết nối được server: " + err.message);
  }
  fillSourceSelects();
  $("#det-source").value = "crossing";
  $("#trk-source").value = "crossing";
  await buildScenarioCards();
  initDetect();
  initTrack();
  initAssoc();
  tabHooks.results = initResults;
  showTab(location.hash.slice(1) || "data");
})();
