// PhishGuard options page: connection, scanning, alert levels. Auto-saves on change.

const DEFAULTS = {
  backendUrl: "http://127.0.0.1:8000",
  apiKey: "",
  autoScan: true,
  highThreshold: 0.6,
  mediumThreshold: 0.4,
};

const $ = (id) => document.getElementById(id);

let savedTimer = null;
let dirty = false;

function showSaved(message) {
  const el = $("saveStatus");
  el.textContent = message || "Saved";
  el.className = "save-status";
  clearTimeout(savedTimer);
  savedTimer = setTimeout(() => (el.textContent = ""), 1800);
}

function showError(message) {
  const el = $("saveStatus");
  el.textContent = message;
  el.className = "save-status error";
  clearTimeout(savedTimer);
  savedTimer = setTimeout(() => (el.textContent = ""), 3500);
}

async function readStored() {
  const stored = await chrome.storage.sync.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

function collect() {
  return {
    backendUrl: $("backendUrl").value.trim().replace(/\/+$/, ""),
    apiKey: $("apiKey").value.trim(),
    autoScan: $("autoScan").checked,
    highThreshold: parseFloat($("highThreshold").value),
    mediumThreshold: parseFloat($("mediumThreshold").value),
  };
}

function applyThresholdBounds() {
  const high = parseFloat($("highThreshold").value);
  const medium = parseFloat($("mediumThreshold").value);
  $("highThreshold").min = (Math.min(0.95, medium + 0.05)).toFixed(2);
  $("mediumThreshold").max = (Math.max(0.05, high - 0.05)).toFixed(2);
  $("highVal").textContent = Math.round(high * 100) + "%";
  $("mediumVal").textContent = Math.round(medium * 100) + "%";
}

function load(settings) {
  $("backendUrl").value = settings.backendUrl;
  $("apiKey").value = settings.apiKey;
  $("autoScan").checked = settings.autoScan;
  $("highThreshold").value = settings.highThreshold;
  $("mediumThreshold").value = settings.mediumThreshold;
  applyThresholdBounds();
}

async function save(quiet) {
  try {
    const settings = collect();
    if (!settings.backendUrl) throw new Error("Backend URL is required");
    if (!(settings.mediumThreshold > 0 && settings.mediumThreshold < settings.highThreshold && settings.highThreshold <= 1)) {
      throw new Error("Alert levels are inconsistent - make sure Blocking > Suspicious");
    }
    await chrome.storage.sync.set(settings);
    if (!quiet) showSaved();
    return settings;
  } catch (err) {
    if (!quiet) showError(err.message);
    throw err;
  }
}

async function loadState() {
  const settings = await readStored();
  load(settings);
  applyThresholdBounds();
}

// --- test connection ---
async function testConnection() {
  const btn = $("testBtn");
  const result = $("testResult");
  let settings;
  try {
    settings = await save(true);
  } catch (err) {
    result.className = "test-result bad";
    result.textContent = "Please fix the settings above first.";
    return;
  }
  btn.disabled = true;
  btn.textContent = "Testing\u2026";
  result.className = "test-result";
  result.textContent = "";
  try {
    const headers = { "Content-Type": "application/json" };
    if (settings.apiKey) headers["X-API-Key"] = settings.apiKey;
    const started = Date.now();
    const res = await fetch(settings.backendUrl + "/predict_url", {
      method: "POST",
      headers,
      body: JSON.stringify({ url: "https://example.com" }),
    });
    const ms = Date.now() - started;
    const body = await res.json();
    if (!res.ok) {
      throw new Error(`backend answered HTTP ${res.status}`);
    }
    const pct = Math.round((body.phishing_probability || 0) * 100);
    result.className = "test-result ok";
    result.innerHTML =
      `Connected in <strong>${ms}ms</strong>. ` +
      `Example verdict: <code>${escapeHtml(body.label || "unknown")}</code> ` +
      `(${pct}% phishing risk, ${escapeHtml(body.tier || "?")} scan).`;
  } catch (err) {
    result.className = "test-result bad";
    result.textContent = "Couldn't reach " + settings.backendUrl + ".";
    result.innerHTML +=
      " Check that the backend is deployed and reachable, then try again.";
  } finally {
    btn.disabled = false;
    btn.textContent = "Test connection";
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// --- events ---
["highThreshold", "mediumThreshold"].forEach((id) => {
  $(id).addEventListener("input", () => {
    applyThresholdBounds();
    dirty = true;
  });
});
["backendUrl", "apiKey", "autoScan"].forEach((id) => {
  $(id).addEventListener("change", () => {
    dirty = true;
  });
});

window.addEventListener("beforeunload", () => {
  if (dirty) save(true).catch(() => {});
});

$("saveBtn").addEventListener("click", () => {
  save(false)
    .then(() => (dirty = false))
    .catch(() => {});
});

$("resetBtn").addEventListener("click", async () => {
  await chrome.storage.sync.set(DEFAULTS);
  load(DEFAULTS);
  dirty = false;
  showSaved("Reset to defaults");
});

$("testBtn").addEventListener("click", testConnection);

document.addEventListener("DOMContentLoaded", loadState);
