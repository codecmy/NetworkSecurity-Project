# PhishGuard Browser Extension

Checks the sites you visit against the PhishGuard machine-learning backend and
warns you before you enter credentials on a suspected phishing page.

## Features

- **Automatic scanning** of every page you navigate to (badge turns green / amber / red).
- **Blocking interstitial** on high-risk pages.
- **Suspicious banner** on medium-risk pages.
- **Popup** with the verdict, phishing probability, and scan tier.
- **Configurable backend URL, API key, and risk thresholds.**

## Install (Chrome / Edge / Brave)

1. Open `chrome://extensions`.
2. Enable **Developer mode** (toggle in the top-right).
3. Click **Load unpacked** and select the `extension/` folder.
4. Pin the PhishGuard icon to the toolbar.

## Install (Firefox)

Use the `extension-firefox/` variant (Manifest V3 with Firefox metadata):

1. Open `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on** and select `extension-firefox/manifest.json`.

> Temporary add-ons unload when Firefox restarts. For permanent install you must
> sign the add-on via [addons.mozilla.org](https://addons.mozilla.org/).

## Backend setup

The extension posts to `POST /predict_url` on the backend:

```json
{ "url": "https://example.com/login" }
```

Response:

```json
{
  "url": "https://example.com/login",
  "result": 0,
  "label": "phishing",
  "confidence": 0.91,
  "phishing_probability": 0.91,
  "risk": "high",
  "tier": "full",
  "features": { "having_IP_Address": 1.0, "...": "..." }
}
```

`risk` maps the phishing probability to `low` / `medium` / `high` using the
backend's default thresholds (0.6 / 0.4).

### User feedback

The popup lets users rate each verdict ("Correct" / "Wrong"). Ratings are
posted to `POST /feedback`:

```json
{
  "url": "https://example.com/login",
  "verdict": "high",
  "label": "phishing",
  "phishing_probability": 0.91,
  "feedback": "wrong",
  "reason": "legitimate"
}
```

Feedback rows are stored in the dedicated MongoDB database
**`NetworkSecurityFeedback`** (collection `feedback`) — separate from the
training data — together with the 30 extracted features for the URL, so the
collected verdicts are directly usable for retraining. If MongoDB is
unreachable, feedback falls back to `real_data/feedback.csv` locally.

Fold feedback into the training set later with:

```bash
python train_from_feedback.py   # writes real_data/features_with_feedback.csv
```

Start the backend locally:

```bash
python app.py                 # serves on http://0.0.0.0:8000
# or
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Then set **Options → Backend URL** to `http://localhost:8000` (use `http://127.0.0.1:8000`
in the extension — mixed-content / localhost rules apply for remote HTTPS backends).

If the backend is deployed behind a domain with `API_KEY` set, paste the key into
**Options → API key** (sent as the `X-API-Key` header).

## Risk levels

| Level  | Phishing probability | UI                              |
| ------ | -------------------- | ------------------------------- |
| High   | >= 0.6 (default)     | Red badge, blocking interstitial |
| Medium | 0.4 – 0.6 (default)  | Amber badge, dismissible banner  |
| Low    | < 0.4 (default)      | Green badge                     |

Thresholds are adjustable in Options.

## Project layout

```
extension/
  manifest.json       Chrome MV3 manifest
  background.js       service worker: scores navigations, drives badge
  content.js          warning overlay / interstitial
  popup.html/js       per-tab verdict popup
  options.html/js     backend URL, API key, thresholds
  icons/              generated PNG icons
```
