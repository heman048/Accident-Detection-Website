const $ = (id) => document.getElementById(id);

function showPage(name) {
  document.querySelectorAll(".page").forEach(p => p.classList.toggle("active", p.id === name));
  document.querySelectorAll(".nav-link").forEach(b => b.classList.toggle("active", b.dataset.page === name));
  const titles = {dashboard:"Dashboard",image:"Image Detection",video:"Video Detection",history:"Accident History",alerts:"Emergency Alerts"};
  $("page-title").textContent = titles[name] || "Dashboard";
  if (name === "dashboard") loadStats();
  if (name === "history") loadHistory();
  if (name === "alerts") loadAlerts();
}
document.querySelectorAll("[data-page]").forEach(b => b.addEventListener("click", () => showPage(b.dataset.page)));
document.querySelectorAll("[data-go]").forEach(b => b.addEventListener("click", () => showPage(b.dataset.go)));

async function api(url, options={}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}
function badge(status) {
  return status === "Accident detected" ? '<span class="pill danger">Accident detected</span>' : '<span class="pill safe">No accident detected</span>';
}
function dateText(value) { return value ? new Date(value).toLocaleString() : "—"; }

async function loadStats() {
  try {
    const d = await api("/api/stats");
    $("stat-total").textContent=d.total; $("stat-accidents").textContent=d.accidents;
    $("stat-safe").textContent=d.safe; $("stat-alerts").textContent=d.pending_alerts;
    $("recent-body").innerHTML = d.recent.length ? d.recent.map(r =>
      `<tr><td>${escapeHtml(r.original_name)}</td><td>${r.media_type}</td><td>${badge(r.status)}</td><td>${dateText(r.created_at)}</td></tr>`
    ).join("") : '<tr><td colspan="4" class="empty">No analyses yet.</td></tr>';
  } catch(e) { console.error(e); }
}
async function loadHistory() {
  try {
    const rows = await api("/api/history");
    $("history-body").innerHTML = rows.length ? rows.map(r =>
      `<tr><td>${r.id}</td><td>${escapeHtml(r.original_name)}</td><td>${r.media_type}</td><td>${badge(r.status)}</td><td>${r.detections}</td><td>${dateText(r.created_at)}</td></tr>`
    ).join("") : '<tr><td colspan="6" class="empty">No history available.</td></tr>';
  } catch(e) { $("history-body").innerHTML=`<tr><td colspan="6" class="empty">${escapeHtml(e.message)}</td></tr>`; }
}
async function loadAlerts() {
  try {
    const rows = await api("/api/alerts");
    $("alerts-list").innerHTML = rows.length ? rows.map(a =>
      `<article class="alert-card"><div><b>⚠ Possible accident: ${escapeHtml(a.original_name)}</b><p>${escapeHtml(a.message)}</p><small>${dateText(a.created_at)} · ${a.status}</small></div>${a.status==="Pending" ? `<button class="secondary-btn" data-resolve="${a.id}">Mark reviewed</button>` : '<span class="pill safe">Reviewed</span>'}</article>`
    ).join("") : '<div class="empty">No alerts generated yet.</div>';
    document.querySelectorAll("[data-resolve]").forEach(b => b.addEventListener("click", async () => {
      await api(`/api/alerts/${b.dataset.resolve}/resolve`, {method:"POST"});
      loadAlerts(); loadStats();
    }));
  } catch(e) { $("alerts-list").textContent=e.message; }
}
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function bindFile(inputId, nameId) {
  $(inputId).addEventListener("change", e => $(nameId).textContent = e.target.files[0]?.name || "No file selected");
}
bindFile("image-file","image-name"); bindFile("video-file","video-name");

async function runDetection(type) {
  const isImage = type === "image";
  const file = $(isImage ? "image-file" : "video-file").files[0];
  const button = $(isImage ? "image-submit" : "video-submit");
  const panel = $(isImage ? "image-result" : "video-result");
  if (!file) { alert("Please choose a file first."); return; }
  const form = new FormData(); form.append("file", file);
  button.disabled=true; button.textContent="Analysing... please wait";
  panel.classList.remove("hidden"); panel.innerHTML="<p>AI model is analysing your file. Please wait...</p>";
  try {
    const d = await api(`/api/detect/${type}`, {method:"POST",body:form});
    const visual = isImage
      ? `<img src="${d.result_url}" alt="Annotated detection result">`
      : `<video controls src="${d.result_url}"></video>`;
    panel.innerHTML = `<h3>${escapeHtml(d.status)}</h3><p>Detections: <b>${isImage ? d.detections : d.frames_with_detections + " frames with detections"}</b></p><p>Highest confidence: <b>${(d.confidence*100).toFixed(1)}%</b></p>${visual}<p class="disclaimer">AI output is a screening result, not confirmation of a real accident. Verify manually.</p>`;
    loadStats();
  } catch(e) {
    panel.innerHTML=`<h3>Unable to analyse</h3><p>${escapeHtml(e.message)}</p><p>Check that the trained YOLO model is installed and the Flask server is running.</p>`;
  } finally {
    button.disabled=false; button.textContent=isImage?"Run image detection":"Run video detection";
  }
}
$("image-submit").addEventListener("click",()=>runDetection("image"));
$("video-submit").addEventListener("click",()=>runDetection("video"));
$("history-refresh").addEventListener("click",loadHistory);
$("alerts-refresh").addEventListener("click",loadAlerts);
loadStats();
