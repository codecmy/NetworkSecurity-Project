// PhishGuard content script.
// Renders a blocking interstitial (high risk) or a warning banner (medium risk).

(() => {
  if (window.__phishguardInjected) return;
  window.__phishguardInjected = true;

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

  let overlay = null;

  function ensureContainer() {
    if (overlay && document.body.contains(overlay)) return overlay;
    const root = document.createElement("div");
    root.id = "phishguard-overlay-root";
    root.style.cssText = `
      all: initial;
      position: fixed;
      top: 0; left: 0; right: 0;
      z-index: 2147483647;
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: #202124;
    `;
    document.documentElement.appendChild(root);
    overlay = root;
    return root;
  }

  function removeOverlay() {
    if (overlay && overlay.parentNode) {
      overlay.parentNode.removeChild(overlay);
    }
    overlay = null;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function topIssues(features) {
    const issues = [];
    for (const [key, value] of Object.entries(features || {})) {
      if (value === -1 || value === 0) {
        issues.push({ value, text: FEATURE_LABELS[key] || key.replace(/_/g, " ") });
      }
    }
    issues.sort((a, b) => (a.value === -1 ? -1 : 1) - (b.value === -1 ? -1 : 1));
    return issues;
  }

  function issuesList(features, limit) {
    const issues = topIssues(features).slice(0, limit);
    const items = issues
      .map(
        (i) => `
          <div style="display:flex; gap:8px; align-items:flex-start; padding:5px 0; font-size:13px; line-height:1.45; color:#3c4043;">
            <span style="width:8px; height:8px; border-radius:50%; flex-shrink:0; margin-top:5px; background:${i.value === -1 ? "#d93025" : "#e37400"};"></span>
            <span>${escapeHtml(i.text)}</span>
          </div>`
      )
      .join("");
    if (issues.length > limit) {
      return items + `<div style="padding:5px 0; font-size:12.5px; color:#80868b;">+ ${issues.length - limit} more signals checked</div>`;
    }
    return items;
  }

  async function dismissedFor(url) {
    try {
      const res = await chrome.storage.session.get("pg-dismissed:" + url);
      return Boolean(res["pg-dismissed:" + url]);
    } catch {
      return false;
    }
  }

  async function markDismissed(url) {
    try {
      await chrome.storage.session.set({ ["pg-dismissed:" + url]: Date.now() });
    } catch { /* storage unavailable */ }
  }

  // ---------- High risk: blocking interstitial ----------
  async function renderHigh(verdict) {
    const url = verdict.url || location.href;
    if (await dismissedFor(url)) return;

    const root = ensureContainer();
    root.innerHTML = `
      <div style="position:fixed; inset:0; display:flex; align-items:center; justify-content:center; padding:24px;
                  background:rgba(15,15,18,0.88); z-index:2147483647;
                  animation:pgfade 0.18s ease-out;">
        <div role="alertdialog" aria-label="Suspected phishing website"
             style="background:#fff; max-width:520px; width:100%; border-radius:16px; padding:32px 32px 24px;
                    box-shadow:0 24px 80px rgba(0,0,0,0.45); font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
                    animation:pgpop 0.2s cubic-bezier(0.2, 0.9, 0.3, 1.2);">
          <div style="display:flex; align-items:center; gap:14px;">
            <div style="width:52px; height:52px; border-radius:50%; background:#fce8e6; display:flex; align-items:center; justify-content:center; flex-shrink:0;">
              <svg viewBox="0 0 24 24" width="30" height="30" fill="none">
                <path d="M12 2l8 3.2v5.6c0 4.7-3.2 8.5-8 11.2-4.8-2.7-8-6.5-8-11.2V5.2L12 2z" fill="#d93025"/>
                <path d="M12 8v4.5" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>
                <circle cx="12" cy="15.2" r="1.3" fill="#fff"/>
              </svg>
            </div>
            <div>
              <div style="font-size:21px; font-weight:700; color:#d93025; letter-spacing:-0.01em;">Suspected phishing website</div>
              <div style="font-size:13px; color:#5f6368; margin-top:2px;">PhishGuard blocked this page before you could be tricked.</div>
            </div>
          </div>

          <p style="margin:18px 0 0; font-size:14px; color:#3c4043; line-height:1.55;">
            This page was scored as highly likely to be a phishing attempt
            (${Math.round((verdict.phishingProbability || verdict.confidence || 0) * 100)}% risk).
            Legitimate sites never ask you to re-enter your password, bank details, or verification codes like this.
          </p>

          <div style="margin-top:14px; display:flex; align-items:center; gap:8px; padding:10px 12px; background:#f1f3f4; border-radius:10px;">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" style="flex-shrink:0;"><rect x="5" y="10" width="14" height="10" rx="2" fill="#80868b"/><path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="#80868b" stroke-width="2"/></svg>
            <span style="font-size:12.5px; color:#3c4043; word-break:break-all; user-select:text;">${escapeHtml(url)}</span>
          </div>

          <details id="pg-why" style="margin-top:14px; border:1px solid #e2e6ea; border-radius:12px;">
            <summary style="cursor:pointer; padding:11px 14px; font-size:13.5px; font-weight:600; color:#3c4043; user-select:none;
                           list-style:none; display:flex; align-items:center; gap:8px;">
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 11v5" stroke-linecap="round"/><circle cx="12" cy="8" r="1.1" fill="currentColor" stroke="none"/></svg>
              Why PhishGuard blocked this page
              <span style="margin-left:auto; color:#80868b;">&#9660;</span>
            </summary>
            <div style="padding:4px 14px 12px; border-top:1px solid #e2e6ea;">${issuesList(verdict.features, 6)}</div>
          </details>

          <div style="display:flex; gap:10px; margin-top:20px; flex-wrap:wrap;">
            <button id="pg-leave" style="flex:1; min-width:160px; padding:12px 14px; border:none; border-radius:10px;
                    background:#d93025; color:#fff; font-size:14px; font-weight:700; cursor:pointer;
                    box-shadow:0 1px 2px rgba(0,0,0,0.2);">Go back to safety</button>
            <button id="pg-proceed" style="flex:1; min-width:160px; padding:12px 14px; border:1px solid #dadce0;
                    background:#fff; color:#3c4043; font-size:14px; font-weight:600; cursor:pointer; border-radius:10px;">
              I understand the risk, continue anyway
            </button>
          </div>

          <div style="margin-top:16px; text-align:center; font-size:12px; color:#80868b;">
            Protected by <strong style="color:#1a73e8;">PhishGuard</strong>
          </div>
        </div>
      </div>
      <style>
        @keyframes pgfade { from { opacity: 0; } to { opacity: 1; } }
        @keyframes pgpop { from { opacity: 0; transform: translateY(14px) scale(0.97); } to { opacity: 1; transform: none; } }
      </style>`;

    root.querySelector("#pg-leave").addEventListener("click", () => {
      if (history.length > 1) {
        history.back();
      } else {
        chrome.runtime.sendMessage({ type: "PHISHGUARD_CLOSE_TAB" }).catch(() => {});
      }
    });
    root.querySelector("#pg-proceed").addEventListener("click", async () => {
      await markDismissed(url);
      removeOverlay();
    });
  }

  // ---------- Medium risk: dismissible floating card ----------
  async function renderMedium(verdict) {
    const url = verdict.url || location.href;
    if (await dismissedFor(url)) return;

    const risk = Math.round((verdict.phishingProbability || 0) * 100);
    const root = ensureContainer();
    root.innerHTML = `
      <div style="position:fixed; top:12px; left:0; right:0; z-index:2147483647;
                  display:flex; justify-content:center; padding:0 12px; pointer-events:none;
                  animation:pgdrop 0.18s ease-out;">
        <div role="alert" aria-label="Suspicious site warning"
             style="pointer-events:auto; max-width:560px; width:100%;
                    background:#fff; border:1px solid #e2e6ea; border-left:3px solid #e37400;
                    border-radius:12px; box-shadow:0 8px 30px rgba(60,64,67,0.16);
                    padding:12px 12px 12px 14px; display:flex; align-items:flex-start; gap:10px;
                    color:#202124; font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" style="flex-shrink:0; margin-top:1px;">
            <path d="M12 3 2.8 19.5h18.4L12 3z" fill="#e37400"/>
            <path d="M12 9.5v4.5" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>
            <circle cx="12" cy="16.6" r="1.3" fill="#fff"/>
          </svg>
          <div style="flex:1; min-width:0;">
            <div style="font-size:13.5px; font-weight:700; letter-spacing:-0.01em;">This site looks suspicious</div>
            <div style="font-size:12.5px; color:#5f6368; margin-top:2px; line-height:1.45;">
              Avoid entering passwords or payment details
              <span style="color:#e37400; font-weight:600;">(&middot; ${risk}% risk)</span>
            </div>
            <details id="pg-why-banner" style="margin-top:7px; font-size:12.5px;">
              <summary style="cursor:pointer; color:#1a73e8; font-weight:600; list-style:none; user-select:none; display:inline-block;">
                Why? <span style="color:#80868b; font-size:10px;">&#9660;</span>
              </summary>
              <div style="margin-top:8px; padding:10px 12px; background:#f8f9fa; border-radius:10px;">${issuesList(verdict.features, 4)}</div>
            </details>
          </div>
          <button id="pg-dismiss" title="Dismiss" aria-label="Dismiss warning"
            style="background:transparent; border:none; cursor:pointer; font-size:20px; color:#9aa0a6; line-height:1; padding:0 2px; flex-shrink:0;">&times;</button>
        </div>
      </div>
      <style>
        @keyframes pgdrop { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: none; } }
        @media (prefers-reduced-motion: reduce) { @keyframes pgdrop { from { opacity: 1; } to { opacity: 1; } } }
      </style>`;

    root.querySelector("#pg-dismiss").addEventListener("click", async () => {
      await markDismissed(url);
      removeOverlay();
    });
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!message || message.type !== "PHISHGUARD_VERDICT") return;
    const verdict = message.verdict || {};
    if (verdict.risk === "high") {
      renderHigh(verdict);
    } else if (verdict.risk === "medium") {
      renderMedium(verdict);
    } else {
      removeOverlay();
    }
    if (sendResponse) sendResponse({ ok: true });
  });
})();
