# 24/7 Uptime Monitor + Phone Dashboard (GitHub-hosted)

Runs entirely on GitHub — **your laptop can be off**. A scheduled GitHub Action
checks your endpoints every 5 minutes, alerts Slack on status changes, and
commits a `status.json` that a GitHub Pages PWA dashboard reads on your phone.

```
GitHub Actions (cron */5)          GitHub Pages (/docs)
   monitor.py one cycle      ┌────►  index.html + app.js
        │                    │         fetches status.json
        ├─ Slack alert       │
        └─ commit ───────────┘
           state.json + status.json
```

---

## How it works

| File | Role |
|---|---|
| `monitor.py` | Runs ONE check cycle and exits (cron re-triggers it) |
| `state.json` | Persists status/failure counts across ephemeral runs (committed) |
| `status.json` | Clean public feed the dashboard reads (committed) |
| `.github/workflows/monitor.yml` | Cron schedule + commit/push |
| `docs/` | The mobile PWA dashboard (served by GitHub Pages) |

Alerts fire **only on transitions**: UP→DOWN (🔴) and DOWN→UP (✅, with downtime
duration). DOWN requires `failures_before_alert` consecutive failed runs
(default 2 ≈ 10 min) to avoid false alarms.

---

## Setup — step by step

### 1. Create a GitHub repo and push this project

```bash
cd gh-monitor
git init
git add .
git commit -m "Initial uptime monitor + dashboard"
git branch -M main
git remote add origin https://github.com/<USER>/<REPO>.git
git push -u origin main
```

> The repo must be **public** for the `raw.githubusercontent.com` status URL and
> GitHub Pages to be freely reachable.

### 2. Add your Slack webhook as a repo secret

1. Repo → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret**
3. Name: `SLACK_WEBHOOK_URL`
4. Value: your `https://hooks.slack.com/services/…` URL
5. **Add secret**

(Get a webhook: [api.slack.com/apps](https://api.slack.com/apps) → your app →
Incoming Webhooks → Add to channel.)

### 3. Enable GitHub Pages from /docs

1. Repo → **Settings** → **Pages**
2. **Source**: *Deploy from a branch*
3. **Branch**: `main`, folder: **/docs** → **Save**
4. Wait ~1 min. Your dashboard URL appears at the top:
   `https://<USER>.github.io/<REPO>/`

### 4. Paste the status.json raw URL into the dashboard

Your status feed lives at:

```
https://raw.githubusercontent.com/<USER>/<REPO>/main/status.json
```

(It's also printed in every Actions run log under **"Print public status.json URL"**.)

Edit **`docs/app.js`**, line near the top:

```js
// <<< PASTE YOUR status.json RAW URL HERE >>>
const STATUS_URL = 'https://raw.githubusercontent.com/USER/REPO/main/status.json';
```

Replace `USER`/`REPO` with yours, commit, and push:

```bash
git add docs/app.js
git commit -m "Set status.json URL"
git push
```

### 5. Trigger a test run

1. Repo → **Actions** tab → **Uptime Monitor** workflow
2. **Run workflow** → **Run workflow**
3. Watch it: it checks endpoints, may post to Slack, and commits `status.json`.

> The schedule (`*/5`) starts automatically once the workflow file is on the
> default branch. GitHub cron is best-effort and can lag a few minutes.

### 6. Open the dashboard on your phone + Add to Home Screen

Open `https://<USER>.github.io/<REPO>/` on your phone.

- **iPhone (Safari):** Share → **Add to Home Screen**
- **Android (Chrome):** ⋮ → **Add to Home screen**

Opens full-screen with an app icon. Auto-refreshes every 30 s.

### 7. Swap test endpoints for your own

Edit `config.yaml`:

```yaml
timeout_seconds: 10
failures_before_alert: 2
endpoints:
  - name: My API
    url: https://api.myapp.com/health
  - name: Marketing Site
    url: https://myapp.com
```

Commit + push. The next run picks them up.

---

## Replace the placeholder icons

`docs/icons/icon-192.svg` and `icon-512.svg` are simple placeholders.

To use your own:
1. Make PNGs at exactly **192×192** and **512×512**.
2. Save as `docs/icons/icon-192.png` / `icon-512.png`.
3. In `docs/manifest.json` change each `"type": "image/svg+xml"` → `"image/png"`
   and update the filenames. Do the same in `service-worker.js` `SHELL_ASSETS`.
4. Bump `CACHE_VERSION` in `service-worker.js` so phones refresh.

---

## Local testing (optional)

```bash
cp .env.example .env          # paste your webhook into .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python monitor.py             # runs one cycle, writes state.json + status.json
```

---

## Notes & limits

- **Public data.** Anyone can read `status.json` and the dashboard — endpoint
  names + up/down are visible. Don't put sensitive names in `config.yaml`.
- **Freshness.** Cron runs every 5 min (best-effort). The dashboard polls every
  30 s, so it shows whatever the last committed run wrote.
- **GitHub Actions minutes.** Public repos get free unlimited Actions minutes;
  `*/5` ≈ 8,640 runs/month, each a few seconds.
- **`[skip ci]`** in the auto-commit message stops the status commit from
  triggering other CI workflows.
