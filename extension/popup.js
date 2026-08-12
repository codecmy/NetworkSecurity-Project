// PhishGuard popup: scan button + verdict report for the current tab.

const DEFAULTS = {
  backendUrl: "http://127.0.0.1:8000",
  apiKey: "",
  autoScan: true,
  highThreshold: 0.6,
  mediumThreshold: 0.4,
};

const LABELS = {
  high: { title: "Phishing risk detected", sub: "Do not enter passwords, payment details, or personal information on this page.", tone: "high" },
  medium: { title: "This page looks suspicious", sub: "Avoid entering sensitive information here — some signals don't add up.", tone: "medium" },
  low: { title: "Looks safe", sub: "PhishGuard found no phishing signals on this page.", tone: "low" },
  unknown: { title: "No verdict yet", sub: "Open this page in a tab and PhishGuard will check it automatically.", tone: "unknown" },
};

const FEATURE_LABELS = {
  having_IP_Address: "Uses a raw IP address instead of a domain name",
  URL_Length: "The web address is unusually long",
  Shortining_Service: "Uses a link shortener",
  having_At_Symbol: "Contains an \u201c@\u201d symbol that hides the real domain",
  double_slash_redirecting: "Uses a redirect trick with double slashes",
  Prefix_Suffix: "Domain uses a hyphen, often to mimic a trusted brand",
  having_Sub_Domain: "Uses extra subdomains to disguise the real site",
  SSLfinal_State: "No valid secure (HTTPS) connection",
  port: "Uses a non-standard port",
  HTTPS_token: "\u201chttps\u201d is included in the domain name itself",
  Abnormal_URL: "Address doesn't match the brand shown on the page",
  DNSRecord: "The site looks unregistered or unreachable",
  Favicon: "Shows another site's icon (brand impersonation)",
  Request_URL: "Page content loads from a different domain",
  URL_of_Anchor: "Links on the page point to a different domain",
  Links_in_tags: "Links in the page metadata point elsewhere",
  SFH: "Forms send data to an unusual location",
  Submitting_to_email: "Forms submit data by email",
  Redirect: "The page hides its real destination with redirects",
  on_mouseover: "Uses status-bar tricks to hide link targets",
  RightClick: "Right-click is disabled (a common phishing trick)",
  popUpWidnow: "Asks for details in pop-up windows",
  Iframe: "Content is embedded from another site",
  age_of_domain: "Domain was registered recently",
  Domain_registration_length: "Domain is registered for only a short time",
  web_traffic: "Very low traffic for a real website",
  Google_Index: "Page is not indexed by search engines",
};

const $ = (id) => document.getElementById(id);

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

async function getSettings() {
  const stored = await chrome.storage.sync.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

function topIssues(features) {
  const issues = [];
  for (const [key, value] of Object.entries(features || {})) {
    if (value === -1 || value === 0) {
      issues.push({ key, value, text: FEATURE_LABELS[key] || key.replace(/_/g, " ") });
    }
  }
  issues.sort((a, b) => (a.value === -1 ? -1 : 1) - (b.value === -1 ? -1 : 1));
  return issues;
}

function relativeTime(ts) {
  const diff = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (diff < 5) return "just now";
  if (diff < 60) return `${diff}s ago`;
  const m = Math.round(diff / 60);
  return m < 60 ? `${m} min ago` : `${Math.round(m / 60)}h ago`;
}

function setPill(state) {
  const pill = $("pill");
  const map = {
    scanning: { text: "checking", cls: "scanning" },
    full: { text: "deep scan", cls: "full" },
    fast: { text: "quick scan", cls: "fast" },
    error: { text: "offline", cls: "error" },
    low: { text: "safe", cls: "full" },
  };
  const cfg = map[state] || { text: "", cls: "" };
  pill.textContent = cfg.text;
  pill.className = "pill " + cfg.cls;
  pill.classList.toggle("hidden", !cfg.text);
}

function showScanView() {
  $("reportView").classList.add("hidden");
  $("scanView").classList.remove("hidden");
  $("scanError").classList.add("hidden");
  setPill(null);
}

function showReportView() {
  $("scanView").classList.add("hidden");
  $("reportView").classList.remove("hidden");
}

function showScanning() {
  showReportView();
  $("spinner").classList.remove("hidden");
  for (const id of ["iconLow", "iconMedium", "iconHigh", "iconUnknown"]) {
    $(id).classList.add("hidden");
  }
  $("heroIcon").className = "icon-wrap scanning";
  $("heroTitle").textContent = "Scanning this page\u2026";
  $("heroSub").textContent = "PhishGuard is analyzing the address.";
  setPill("scanning");
}

function showHero(tone, title, sub) {
  $("heroTitle").textContent = title;
  $("heroSub").textContent = sub;
  $("spinner").classList.add("hidden");
  for (const id of ["iconLow", "iconMedium", "iconHigh", "iconUnknown"]) {
    $(id).classList.add("hidden");
  }
  const iconMap = { low: "iconLow", medium: "iconMedium", high: "iconHigh", unknown: "iconUnknown" };
  const iconId = iconMap[tone] || "iconUnknown";
  $(iconId).classList.remove("hidden");
  $("heroIcon").className = "icon-wrap " + tone;
}

function renderMeter(phishingProbability) {
  const meter = $("meter");
  if (phishingProbability == null) { meter.classList.add("hidden"); return; }
  meter.classList.remove("hidden");
  const pct = Math.max(2, Math.min(98, Math.round(phishingProbability * 100)));
  $("meterMarker").style.left = pct + "%";
  $("meterValue").textContent = `${pct}% phishing risk`;
}

function renderUrl(verdict) {
  const row = $("urlRow");
  if (!verdict || !verdict.url) { row.classList.add("hidden"); return; }
  row.classList.remove("hidden");
  const clean = verdict.url.replace(/^https?:\/\//, "").replace(/\/$/, "");
  $("urlText").textContent = clean;
  $("urlText").title = verdict.url;
  const isHttps = /^https:/.test(verdict.url);
  $("lockIcon").style.opacity = isHttps ? "1" : "0.35";
  $("lockIcon").title = isHttps ? "Secure connection" : "No secure connection";
}

function renderWhy(verdict) {
  const why = $("why");
  const issues = topIssues(verdict && verdict.features);
  const positive = issues.length === 0 && verdict && verdict.risk === "low";

  if (!verdict || (issues.length === 0 && !positive)) {
    why.classList.add("hidden");
    return;
  }
  why.classList.remove("hidden");
  $("whyTitle").textContent = positive
    ? "What PhishGuard checked"
    : verdict.risk === "high" ? "Why PhishGuard blocked this page" : "Why this looks suspicious";
  $("whyBody").innerHTML = "";
  if (positive) {
    const div = document.createElement("div");
    div.className = "positive-msg";
    div.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none"><circle cx="12" cy="12" r="10" fill="#188038"/><path d="M7.5 12.5l3 3 6-7" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg><span>No phishing signals found — the address, connection, and links check out.</span>`;
    $("whyBody").appendChild(div);
    return;
  }
  issues.slice(0, 6).forEach((issue) => {
    const div = document.createElement("div");
    div.className = "reason";
    const dot = issue.value === -1 ? "neg" : "zero";
    div.innerHTML = `<span class="dot ${dot}"></span><span>${escapeHtml(issue.text)}</span>`;
    $("whyBody").appendChild(div);
  });
  if (issues.length > 6) {
    const more = document.createElement("div");
    more.className = "reason more";
    more.textContent = `+ ${issues.length - 6} more signals checked`;
    $("whyBody").appendChild(more);
  }
}

function renderFeedback(verdict) {
  const fb = $("feedback");
  if (!verdict || !verdict.url || verdict.risk === "unknown") {
    fb.classList.add("hidden");
    return;
  }
  fb.classList.remove("hidden");
  $("feedbackPrompt").textContent =
    verdict.risk === "low" ? "Was this page checked correctly?" : "Was this warning helpful?";
}

function setVerdict(verdict) {
  const level = verdict && verdict.risk ? verdict.risk : "unknown";

  if (!verdict) {
    showScanView();
    $("scanError").textContent = "Couldn't get a verdict for this page. Try again.";
    $("scanError").classList.remove("hidden");
    return;
  }

  if (level === "unknown") {
    showScanView();
    $("scanError").textContent = verdict.error
      ? "Couldn't reach the PhishGuard backend. Check that it's running, then try again."
      : "Couldn't get a verdict for this page. Try again.";
    $("scanError").classList.remove("hidden");
    return;
  }

  showReportView();
  const cfg = LABELS[level] || LABELS.unknown;
  showHero(cfg.tone, cfg.title, cfg.sub);
  setPill(level === "low" ? "low" : verdict.tier === "full" ? "full" : "fast");
  renderMeter(verdict.phishingProbability);
  renderUrl(verdict);
  renderWhy(verdict);
  renderFeedback(verdict);
  $("lastChecked").textContent = verdict.timestamp ? `Last checked ${relativeTime(verdict.timestamp)}` : "";
}

function initFeedback(verdict) {
  $("fbForm").classList.add("hidden");
  $("fbThanks").classList.add("hidden");

  const submit = async (feedback, reason) => {
    const settings = await getSettings();
    try {
      const headers = { "Content-Type": "application/json" };
      if (settings.apiKey) headers["X-API-Key"] = settings.apiKey;
      await fetch(`${settings.backendUrl}/feedback`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          url: verdict.url,
          verdict: verdict.risk,
          label: verdict.label,
          phishing_probability: verdict.phishingProbability,
          feedback,
          reason,
        }),
      });
    } catch {
      // backend offline — feedback is best-effort, silently drop
    }
    $("fbForm").classList.add("hidden");
    $("fbThanks").classList.remove("hidden");
  };

  $("fbUp").onclick = () => submit("correct", "");
  $("fbDown").onclick = () => {
    $("fbForm").classList.remove("hidden");
    $("fbReason").focus();
  };
  $("fbForm").onsubmit = (e) => {
    e.preventDefault();
    submit("wrong", $("fbReason").value || "other");
  };
}

async function init() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  const url = tab && tab.url && /^https?:/.test(tab.url) ? tab.url : null;
  $("scanUrl").textContent = url
    ? url.replace(/^https?:\/\//, "").replace(/\/$/, "")
    : "Open a web page to scan it";
  $("scanUrl").title = url || "";

  $("scanBtn").addEventListener("click", async () => {
    if (!tab || !tab.id) return;
    const btn = $("scanBtn");
    btn.disabled = true;
    btn.textContent = "Scanning\u2026";
    showScanning();
    let verdict = null;
    try {
      const res = await chrome.runtime.sendMessage({
        type: "PHISHGUARD_RESCAN",
        tabId: tab.id,
        url: tab.url,
      });
      verdict = res && res.verdict ? res.verdict : null;
    } catch {
      verdict = null;
    }
    btn.disabled = false;
    btn.textContent = "Scan this website";
    $("lastChecked").textContent = "";
    setVerdict(verdict);
    if (verdict && verdict.risk !== "unknown") initFeedback(verdict);
  });

  $("copyUrl").addEventListener("click", async () => {
    const text = url || (tab && tab.url) || "";
    try {
      await navigator.clipboard.writeText(text);
      $("copyUrl").style.color = "#188038";
      setTimeout(() => ($("copyUrl").style.color = ""), 1200);
    } catch { /* clipboard unavailable */ }
  });

  const head = $("whyHead");
  head.addEventListener("click", () => {
    $("why").classList.toggle("open");
    $("whyBody").classList.toggle("hidden");
  });

  $("options").addEventListener("click", (e) => {
    e.preventDefault();
    chrome.runtime.openOptionsPage();
  });
}

document.addEventListener("DOMContentLoaded", init);
