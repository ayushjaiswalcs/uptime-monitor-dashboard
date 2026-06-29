"""
monitor.py — One-shot uptime checker for GitHub Actions (cron-driven).

Runs ONE check cycle and exits. A cron workflow re-triggers it on a schedule.
Because Actions runners are ephemeral, all status is persisted to state.json
(committed back to the repo by the workflow). A clean status.json is also
written for the public dashboard.

Behaviour:
  - HTTP GET each endpoint. 2xx/3xx = UP; else / timeout / conn error = DOWN.
  - Track consecutive failures in state.json; only declare DOWN after
    `failures_before_alert` consecutive failed runs.
  - Slack alert ONLY on transitions (UP->DOWN, DOWN->UP). Otherwise silent.
  - Slack webhook from env SLACK_WEBHOOK_URL (GitHub secret), .env fallback.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

# ── Paths (relative to this file) ──────────────────────────────────────────────
_HERE       = Path(__file__).parent
CONFIG_FILE = _HERE / "config.yaml"
STATE_FILE  = _HERE / "state.json"     # committed — internal bookkeeping
STATUS_FILE = _HERE / "status.json"    # committed — public dashboard feed

# ── Secret (env first, .env fallback for local testing) ────────────────────────
load_dotenv(_HERE / ".env")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")


# ── Config ─────────────────────────────────────────────────────────────────────
def load_config() -> dict:
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


# ── State ──────────────────────────────────────────────────────────────────────
def load_state() -> dict:
    """Read state.json; empty dict if absent or corrupt (first run / new repo)."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            print("⚠  state.json corrupt — starting fresh.")
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def _default_ep_state() -> dict:
    return {
        "status": "unknown",        # unknown | up | down
        "consecutive_failures": 0,
        "down_since": None,         # ISO-8601 — when current DOWN began
        "status_since": None,       # ISO-8601 — when current status began
        "last_http_code": None,
        "last_response_ms": None,
        "last_checked": None,
    }


def get_ep_state(state: dict, url: str) -> dict:
    if url not in state:
        state[url] = _default_ep_state()
    else:
        for k, v in _default_ep_state().items():
            state[url].setdefault(k, v)   # back-fill new keys on upgrade
    return state[url]


# ── status.json (public dashboard feed) ────────────────────────────────────────
def write_status_json(state: dict, endpoints: list) -> None:
    output = []
    for ep in endpoints:
        url = ep["url"]
        s   = state.get(url, _default_ep_state())
        output.append({
            "name":         ep["name"],
            "url":          url,
            "status":       s["status"].upper() if s["status"] != "unknown" else "UNKNOWN",
            "http_code":    s["last_http_code"],
            "response_ms":  s["last_response_ms"],
            "last_checked": s["last_checked"],
            "since":        s["status_since"],
        })
    STATUS_FILE.write_text(json.dumps(output, indent=2) + "\n")


# ── HTTP check ─────────────────────────────────────────────────────────────────
def check_endpoint(url: str, timeout: int) -> dict:
    start = time.monotonic()
    try:
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        is_up = resp.status_code < 400
        return {"is_up": is_up, "status_code": resp.status_code,
                "response_time": elapsed_ms,
                "error": None if is_up else f"HTTP {resp.status_code}"}
    except requests.Timeout:
        return {"is_up": False, "status_code": None, "response_time": None, "error": "Timeout"}
    except requests.ConnectionError as exc:
        msg = str(exc).split("\n")[0][:120]
        return {"is_up": False, "status_code": None, "response_time": None,
                "error": f"Connection error: {msg}"}
    except Exception as exc:  # noqa: BLE001
        return {"is_up": False, "status_code": None, "response_time": None, "error": str(exc)[:120]}


# ── Duration helper ─────────────────────────────────────────────────────────────
def format_duration(total_seconds: float) -> str:
    s = int(total_seconds)
    h, rem = divmod(s, 3600)
    m, s   = divmod(rem, 60)
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)


# ── Slack ──────────────────────────────────────────────────────────────────────
def build_payload(endpoint: dict, result: dict, transition: str,
                  down_duration: str | None = None) -> dict:
    is_down = (transition == "down")
    emoji   = "🔴" if is_down else "✅"
    label   = "DOWN" if is_down else "RECOVERED"
    color   = "#e02424" if is_down else "#0e9f6e"
    ts      = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    fields = [
        {"type": "mrkdwn", "text": f"*Endpoint*\n{endpoint['name']}"},
        {"type": "mrkdwn", "text": f"*URL*\n{endpoint['url']}"},
        {"type": "mrkdwn", "text": f"*Status*\n{emoji}  {label}"},
    ]
    if result["status_code"] is not None:
        fields.append({"type": "mrkdwn", "text": f"*HTTP Code*\n`{result['status_code']}`"})
    if result["error"]:
        fields.append({"type": "mrkdwn", "text": f"*Error*\n{result['error']}"})
    if result["response_time"] is not None:
        fields.append({"type": "mrkdwn", "text": f"*Response Time*\n{result['response_time']} ms"})
    if down_duration:
        fields.append({"type": "mrkdwn", "text": f"*Down For*\n{down_duration}"})
    fields.append({"type": "mrkdwn", "text": f"*Time*\n{ts}"})
    fields = fields[:10]

    return {
        "text": f"{emoji}  *{endpoint['name']}* is {label}",
        "attachments": [{
            "color": color,
            "blocks": [
                {"type": "header",
                 "text": {"type": "plain_text",
                          "text": f"{emoji}  {endpoint['name']} is {label}", "emoji": True}},
                {"type": "section", "fields": fields},
            ],
        }],
    }


def send_slack_alert(payload: dict) -> None:
    """Post to Slack. Retries once. Never raises (a failed alert must not fail the run)."""
    if not SLACK_WEBHOOK_URL:
        print("    ⚠  SLACK_WEBHOOK_URL not set — alert skipped (set the repo secret).")
        return
    for attempt in range(2):
        try:
            resp = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
            if resp.status_code == 200:
                return
            print(f"    ⚠  Slack HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as exc:  # noqa: BLE001
            print(f"    ⚠  Slack post failed (attempt {attempt + 1}): {exc}")
        if attempt == 0:
            time.sleep(2)
    print("    ⚠  Slack alert not delivered after 2 attempts — continuing.")


# ── One check cycle ─────────────────────────────────────────────────────────────
def run_once() -> None:
    config         = load_config()
    timeout        = config.get("timeout_seconds", 10)
    fail_threshold = config.get("failures_before_alert", 2)
    endpoints      = config.get("endpoints", [])
    state          = load_state()

    now      = datetime.now(timezone.utc)
    now_iso  = now.isoformat()
    ts_human = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts_human}]  Checking {len(endpoints)} endpoint(s)…")

    for ep in endpoints:
        url, name = ep["url"], ep["name"]
        ep_state    = get_ep_state(state, url)
        prev_status = ep_state["status"]

        result = check_endpoint(url, timeout)
        ep_state["last_http_code"]   = result["status_code"]
        ep_state["last_response_ms"] = result["response_time"]
        ep_state["last_checked"]     = now_iso

        if result["is_up"]:
            ep_state["consecutive_failures"] = 0

            if prev_status == "down":
                # DOWN -> UP
                down_duration = None
                if ep_state["down_since"]:
                    secs = (now - datetime.fromisoformat(ep_state["down_since"])).total_seconds()
                    down_duration = format_duration(secs)
                ep_state["status"]       = "up"
                ep_state["down_since"]   = None
                ep_state["status_since"] = now_iso
                suffix = f" (was down for {down_duration})" if down_duration else ""
                print(f"  ✅  {name} — RECOVERED{suffix}")
                send_slack_alert(build_payload(ep, result, "up", down_duration=down_duration))
            else:
                if ep_state["status"] != "up":
                    ep_state["status_since"] = now_iso
                ep_state["status"] = "up"
                rt = f"{result['response_time']} ms" if result["response_time"] else "—"
                print(f"  ✅  {name} — UP  (HTTP {result['status_code']}, {rt})")

        else:
            ep_state["consecutive_failures"] += 1
            failures = ep_state["consecutive_failures"]

            if failures >= fail_threshold and prev_status != "down":
                # UP/unknown -> DOWN
                ep_state["status"]       = "down"
                ep_state["status_since"] = now_iso
                if ep_state["down_since"] is None:
                    ep_state["down_since"] = now_iso
                print(f"  🔴  {name} — DOWN  ({result['error']})")
                send_slack_alert(build_payload(ep, result, "down"))
            elif failures < fail_threshold:
                print(f"  ⚠   {name} — fail {failures}/{fail_threshold}  ({result['error']})")
            else:
                print(f"  🔴  {name} — still DOWN  ({result['error']})")

    save_state(state)
    write_status_json(state, endpoints)
    print("Wrote state.json + status.json.")


if __name__ == "__main__":
    try:
        run_once()
    except Exception as exc:  # noqa: BLE001
        print(f"❌  Monitor run failed: {exc}", file=sys.stderr)
        sys.exit(1)
