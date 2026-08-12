// PhishGuard background service worker (MV3).
// Watches navigation, scores URLs via the PhishGuard backend, and drives the
// toolbar badge + in-page warning overlay.

const DEFAULTS = {
  backendUrl: "http://127.0.0.1:8000",
  apiKey: "",
  autoScan: true,
  highThreshold: 0.6,
  mediumThreshold: 0.4,
};

const SKIP_PROTOCOLS = new Set([
  "chrome:", "chrome-extension:", "about:", "devtools:", "edge:", "moz-extension:",
  "view-source:", "data:", "blob:", "file:", "javascript:", "opera:",
]);

const state = new Map(); // tabId -> { url, label, tier, confidence, phishingProbability }

async function getSettings() {
  const stored = await chrome.storage.sync.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

function isSkippableUrl(url) {
  try {
    const protocol = new URL(url).protocol;
    return SKIP_PROTOCOLS.has(protocol);
  } catch {
    return true;
  }
}

function normalizeUrl(url) {
  try {
    const parsed = new URL(url);
    parsed.hash = "";
    return parsed.href;
  } catch {
    return url;
  }
}

function riskLevel(phishingProbability, settings) {
  if (phishingProbability >= settings.highThreshold) return "high";
  if (phishingProbability >= settings.mediumThreshold) return "medium";
  return "low";
}

const BADGE = {
  high: { text: "!" , color: "#d93025" },
  medium: { text: "?", color: "#f9ab00" },
  low: { text: "✓", color: "#188038" },
  unknown: { text: "", color: "#5f6368" },
};

async function scoreTab(tabId, url, force) {
  if (!url || isSkippableUrl(url)) return;
  const settings = await getSettings();
  if (!settings.autoScan && !force) return;

  const normalized = normalizeUrl(url);
  const cached = state.get(tabId);
  if (!force && cached && cached.url === normalized && cached.timestamp) {
    if (Date.now() - cached.timestamp < 60_000) {
      applyVerdict(tabId, cached);
      return;
    }
  }

  const label = "scanning";
  setBadge(tabId, "…", "#1a73e8");

  try {
    const response = await fetch(`${settings.backendUrl}/predict_url`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(settings.apiKey ? { "X-API-Key": settings.apiKey } : {}),
      },
      body: JSON.stringify({ url: normalized }),
    });

    if (!response.ok) {
      throw new Error(`backend responded ${response.status}`);
    }

    const verdict = await response.json();
    const level = riskLevel(verdict.phishing_probability, settings);
    const record = {
      url: normalized,
      label: verdict.label,
      tier: verdict.tier,
      confidence: verdict.confidence,
      phishingProbability: verdict.phishing_probability,
      risk: level,
      timestamp: Date.now(),
    };
    state.set(tabId, record);
    applyVerdict(tabId, record);
    notifyContent(tabId, record);
  } catch (err) {
    console.warn("PhishGuard: score failed", err);
    setBadge(tabId, "", "#80868b");
    notifyContent(tabId, {
      url: normalized,
      label: "unknown",
      tier: null,
      confidence: null,
      phishingProbability: null,
      risk: "unknown",
      error: String(err && err.message ? err.message : err),
      timestamp: Date.now(),
    });
  }
}

function setBadge(tabId, text, color) {
  chrome.action.setBadgeText({ tabId, text }).catch(() => {});
  chrome.action.setBadgeBackgroundColor({ tabId, color }).catch(() => {});
}

function applyVerdict(tabId, record) {
  const badge = BADGE[record.risk] || BADGE.unknown;
  setBadge(tabId, badge.text, badge.color);
}

async function notifyContent(tabId, record) {
  try {
    await chrome.tabs.sendMessage(tabId, { type: "PHISHGUARD_VERDICT", verdict: record });
  } catch {
    // content script not injected in this tab yet - ignore
  }
}

// Navigation events
chrome.webNavigation.onCommitted.addListener((details) => {
  if (details.frameType !== "outermost_frame") return;
  scoreTab(details.tabId, details.url, false);
});

// Manual re-scan requests (popup / content script)
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.type === "PHISHGUARD_RESCAN") {
    scoreTab(sender.tab ? sender.tab.id : message.tabId, message.url, true).then(() => {
      const record = state.get(sender.tab ? sender.tab.id : message.tabId) || null;
      sendResponse({ ok: true, verdict: record });
    });
    return true; // async response
  }
  if (message && message.type === "PHISHGUARD_GET_STATE") {
    const record = state.get(sender.tab ? sender.tab.id : message.tabId) || null;
    sendResponse({ ok: true, verdict: record });
    return true;
  }
  if (message && message.type === "PHISHGUARD_CLOSE_TAB" && sender.tab) {
    chrome.tabs.remove(sender.tab.id).catch(() => {});
    sendResponse({ ok: true });
    return true;
  }
});

chrome.tabs.onRemoved.addListener((tabId) => state.delete(tabId));
