#!/usr/bin/env python3
# ==============================================================================
#  Version : 0.3          Date : 2026-04-16
#  Project : All
#  File    : web_monitor.py
#  Function: Parse license/process map file and display real-time monitoring
#            dashboard with charts, user-sum mode, and bjobs log viewer.
#  Author  : RickTran (Tran Dang Vinh Khang)
#  History :
#    v0.1 : Collect data from existing file
#    v0.2 : Add real-time refresh + charts
#    v0.3 : Add SumByUser mode, bjobs log viewer, English comments,
#            version info, full-path log assembly, duplicate-user sorting
# ==============================================================================

import os
import sys
import json
import time
import base64
import threading
import subprocess
import re
from io import BytesIO
from datetime import datetime
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, render_template_string, request

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# ==============================================================================
#  APP CONSTANTS
# ==============================================================================

APP_VERSION  = "0.3"
APP_AUTHOR   = "RickTran (Tran Dang Vinh Khang)"
APP_NAME     = "LICENSE CHECK Monitor"

app = Flask(__name__)

# Default data file path – can be overridden via the UI file-path input
DATA_FILE        = "/project/VAST_PI/WORKPLACE/CPU_CHECK/list.map.post"
REFRESH_INTERVAL = 5       # seconds between background cache refreshes
ALERT_THRESHOLD  = 4       # count >= this value triggers a red alert

# Shared in-memory cache updated by background thread
_cache   = {"data": [], "timestamp": "", "total": 0, "alerts": 0}
_history = []              # rolling list of {"time": HH:MM:SS, "total": int}
_lock    = threading.Lock()

# ==============================================================================
#  DATA PARSING
# ==============================================================================

def parse_map_file(filepath: str) -> list:
    """
    Parse the list.map / list.map.post file.

    Expected line format (real file):
      <license_id> <SERVER> ... -- <first>.<last> <GROUP>

    The parser extracts:
      - license_id : first token  (e.g. gsme001)
      - server     : second token (e.g. GSME-TW-12)
      - username   : second-to-last token after '--' separator
                     (handles "first. last" with optional space after dot)
      - group      : last token   (e.g. PID1, PID3, EO, AC)

    Returns a list of dicts:
      [{"license_id", "count", "server", "username", "group"}, ...]
    sorted by server name.
    """
    if not filepath or not os.path.exists(filepath):
        return []

    try:
        with open(filepath, "r", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[parse_map_file] Error reading {filepath}: {e}")
        return []

    records = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) < 4:
            continue  # skip malformed lines

        license_id = parts[0]   # e.g. gsme001
        server     = parts[1]   # e.g. GSME-TW-12

        # Extract username and group from after the '--' separator.
        # Format: "-- first.last GROUP"  or  "-- first. last GROUP"
        # We join tokens after '--' and normalise spaces inside names.
        try:
            dash_idx = parts.index("--")
        except ValueError:
            # No '--' separator: fall back to second-to-last / last tokens
            username = parts[-2].replace(" ", "")
            group    = parts[-1]
        else:
            # Tokens after '--': could be ["first.last", "GROUP"]
            #                  or ["first.", "last", "GROUP"]
            after = parts[dash_idx + 1:]
            if not after:
                continue
            group    = after[-1]
            # Join the name tokens (everything before group) and remove spaces
            raw_name = " ".join(after[:-1])
            username = re.sub(r"\s*\.\s*", ".", raw_name).strip()

        if not username or not group:
            continue

        records.append({
            "license_id": license_id,
            "server":     server,
            "username":   username,
            "group":      group,
        })

    # --- Aggregate: count occurrences per (server, username, group) ---
    counter = Counter(
        (r["license_id"], r["server"], r["username"], r["group"])
        for r in records
    )

    results = []
    for (lid, srv, usr, grp), cnt in counter.items():
        results.append({
            "license_id": lid,
            "count":      cnt,
            "server":     srv,
            "username":   usr,
            "group":      grp,
        })

    results.sort(key=lambda x: x["server"])
    return results


def aggregate_by_user(data: list) -> list:
    """
    Collapse rows with the same username into a single row, summing counts.
    The 'server' field becomes a comma-separated list of all servers.
    The 'group' field keeps the most common group for that user.
    Used when the 'Sum by User' checkbox is active.
    """
    user_map = defaultdict(lambda: {"count": 0, "servers": [], "groups": []})
    for row in data:
        u = row["username"]
        user_map[u]["count"]   += row["count"]
        user_map[u]["servers"].append(row["server"])
        user_map[u]["groups"].append(row["group"])

    result = []
    for username, info in sorted(user_map.items()):
        # Most common group for this user
        top_group = Counter(info["groups"]).most_common(1)[0][0]
        # Deduplicate + sort server list
        srv_list  = sorted(set(info["servers"]))
        result.append({
            "license_id": "",
            "count":      info["count"],
            "server":     ", ".join(srv_list),
            "username":   username,
            "group":      top_group,
        })

    # Sort by count descending, then username
    result.sort(key=lambda x: (-x["count"], x["username"]))
    return result


def refresh_cache(fp: str = None):
    """Refresh the shared cache from the data file. Called by background thread."""
    global _history
    target = fp or DATA_FILE
    data   = parse_map_file(target)
    ts     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total  = sum(d["count"] for d in data)
    alerts = sum(1 for d in data if d["count"] >= ALERT_THRESHOLD)

    with _lock:
        _cache["data"]      = data
        _cache["timestamp"] = ts
        _cache["total"]     = total
        _cache["alerts"]    = alerts
        _history.append({"time": ts.split(" ")[1], "total": total})
        if len(_history) > 60:
            _history = _history[-60:]


def background_thread():
    """Daemon thread: refresh the cache every REFRESH_INTERVAL seconds."""
    while True:
        try:
            refresh_cache()
        except Exception as e:
            print(f"[background_thread] Error: {e}")
        time.sleep(REFRESH_INTERVAL)

# ==============================================================================
#  BJOBS LOG VIEWER
# ==============================================================================

def run_bjobs(username: str) -> dict:
    """
    Run: bjobs -u <username> -o "SUB_CWD JOB_NAME" -noheader
    Parse output and assemble full log paths.

    Path-assembly rule:
      If SUB_CWD ends with /pr  AND  JOB_NAME looks like a relative path
      containing .log  → full_path = SUB_CWD + "/" + JOB_NAME
      Otherwise        → return the raw values as-is.

    Returns:
      {"jobs": [{"job_name", "sub_cwd", "log_path", "full_path"}], "raw": str, "error": str}
    """
    cmd = ["bjobs", "-u", username, "-o", "SUB_CWD JOB_NAME", "-noheader"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15
        )
        raw_output = proc.stdout.strip()
        if proc.returncode != 0 or not raw_output:
            # Return mock data when bjobs is unavailable (demo / test env)
            raw_output = _mock_bjobs(username)

    except FileNotFoundError:
        # bjobs binary not found – use mock data for demonstration
        raw_output = _mock_bjobs(username)
    except subprocess.TimeoutExpired:
        return {"jobs": [], "raw": "", "error": "bjobs command timed out"}
    except Exception as e:
        return {"jobs": [], "raw": "", "error": str(e)}

    jobs = _parse_bjobs_output(raw_output)
    return {"jobs": jobs, "raw": raw_output, "error": ""}


def _mock_bjobs(username: str) -> str:
    """
    Return fake bjobs output for testing environments where LSF is not installed.
    Format: SUB_CWD   JOB_NAME
    """
    base = f"/project/VAST_PI/WORKPLACE/{username.upper()}"
    return (
        f"{base}/run01/pr   sim_output/run01_corner_tt.log\n"
        f"{base}/run02/pr   sim_output/run02_corner_ff.log\n"
        f"{base}/run03/pr   sim_output/run03_corner_ss.log\n"
        f"{base}/verify     reports/timing_check.log\n"
        f"{base}/impl/pr    synth/netlist_check.log\n"
    )


def _parse_bjobs_output(raw: str) -> list:
    """
    Parse the whitespace-separated bjobs output lines and assemble full paths.

    Assembly rule for log path:
      If   SUB_CWD ends with '/pr'  AND  JOB_NAME contains '/'
      Then full_path = SUB_CWD + '/' + JOB_NAME
      Else full_path = JOB_NAME (already absolute or just a name)
    """
    jobs = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("SUB_CWD"):
            continue  # skip header / blank lines

        # Split on whitespace – first token = SUB_CWD, rest = JOB_NAME
        tokens = line.split(None, 1)
        if len(tokens) < 2:
            sub_cwd  = tokens[0] if tokens else ""
            job_name = ""
        else:
            sub_cwd, job_name = tokens[0], tokens[1].strip()

        # Build full path
        full_path = _assemble_log_path(sub_cwd, job_name)

        jobs.append({
            "sub_cwd":   sub_cwd,
            "job_name":  job_name,
            "full_path": full_path,
        })
    return jobs


def _assemble_log_path(sub_cwd: str, job_name: str) -> str:
    """
    Assemble the full log file path from SUB_CWD and JOB_NAME.

    Rules:
      1. If sub_cwd ends with /pr and job_name is a relative path
         → full_path = sub_cwd + '/' + job_name
         Example: /proj/user/run01/pr  +  sim/result.log
                  → /proj/user/run01/pr/sim/result.log
      2. If job_name is already an absolute path → use as-is.
      3. Otherwise → sub_cwd + '/' + job_name
    """
    if not job_name:
        return sub_cwd

    # Case 2: job_name is already absolute
    if job_name.startswith("/"):
        return job_name

    # Case 1 & 3: relative job_name – join with sub_cwd
    # Normalise the resulting path (resolve .. etc.)
    joined = os.path.normpath(os.path.join(sub_cwd, job_name))
    return joined

# ==============================================================================
#  CHART GENERATION  (matplotlib → base64 PNG)
# ==============================================================================

BG_DARK  = "#1e1e2e"
BG_PANEL = "#2a2a3e"
FG_GREEN = "#a6e3a1"
FG_RED   = "#f38ba8"
FG_YELLOW= "#f9e2af"
FG_BLUE  = "#89b4fa"
FG_TEAL  = "#94e2d5"
FG_MAUVE = "#cba6f7"
FG_NORM  = "#cdd6f4"


def fig_to_b64(fig) -> str:
    """Save matplotlib figure to base64-encoded PNG string."""
    buf = BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(),
                bbox_inches="tight", dpi=110)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def apply_chart_style(ax, title: str):
    """Apply the shared dark-theme style to a matplotlib Axes."""
    ax.set_facecolor(BG_PANEL)
    ax.tick_params(colors=FG_NORM, labelsize=9)
    ax.set_title(title, color=FG_BLUE, fontsize=11, fontweight="bold", pad=10)
    for spine in ax.spines.values():
        spine.set_edgecolor("#45475a")
    ax.xaxis.label.set_color(FG_NORM)
    ax.yaxis.label.set_color(FG_NORM)


def make_bar_chart(data: list) -> str:
    """Horizontal bar chart: top servers ordered by total process count."""
    fig, ax = plt.subplots(figsize=(7, 5), facecolor=BG_DARK)
    if not data:
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes,
                ha="center", va="center", color=FG_NORM)
        result = fig_to_b64(fig); plt.close(fig); return result

    # Aggregate count per server
    srv_counts: dict[str, int] = {}
    for d in data:
        for srv in d["server"].split(", "):
            srv_counts[srv] = srv_counts.get(srv, 0) + d["count"]

    top = sorted(srv_counts.items(), key=lambda x: x[1], reverse=True)[:25]
    if not top:
        result = fig_to_b64(fig); plt.close(fig); return result

    labels, values = zip(*top)
    colors = [
        FG_RED    if v >= ALERT_THRESHOLD * 2 else
        FG_YELLOW if v >= ALERT_THRESHOLD else
        FG_GREEN
        for v in values
    ]

    bars = ax.barh(range(len(labels)), values, color=colors,
                   edgecolor="#45475a", linewidth=0.5, height=0.65)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9, color=FG_NORM, fontfamily="monospace")
    ax.invert_yaxis()
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))

    # Value labels on bar ends
    for bar, val in zip(bars, values):
        ax.text(val + 0.05, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", ha="left", color=FG_NORM, fontsize=8)

    # Alert threshold line
    ax.axvline(x=ALERT_THRESHOLD, color=FG_RED, linestyle="--",
               linewidth=1.2, alpha=0.8, label=f"Alert ≥{ALERT_THRESHOLD}")
    ax.legend(fontsize=9, facecolor=BG_PANEL, edgecolor="#45475a", labelcolor=FG_NORM)
    apply_chart_style(ax, "Top Servers by Process Count")
    ax.set_xlabel("Process Count", fontsize=10)
    fig.tight_layout(pad=1.5)
    result = fig_to_b64(fig); plt.close(fig); return result


def make_pie_chart(data: list) -> str:
    """Pie chart: process count distribution by group."""
    fig, ax = plt.subplots(figsize=(6, 5), facecolor=BG_DARK)
    grp_counts: dict[str, int] = {}
    for d in data:
        grp_counts[d["group"]] = grp_counts.get(d["group"], 0) + d["count"]

    if not grp_counts:
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes,
                ha="center", va="center", color=FG_NORM)
        result = fig_to_b64(fig); plt.close(fig); return result

    palette = [FG_BLUE, FG_GREEN, FG_MAUVE, FG_YELLOW, FG_TEAL, FG_RED, "#fab387"]
    labels  = list(grp_counts.keys())
    sizes   = list(grp_counts.values())
    colors  = [palette[i % len(palette)] for i in range(len(labels))]

    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, autopct="%1.1f%%", colors=colors,
        startangle=140, pctdistance=0.78,
        wedgeprops={"edgecolor": BG_DARK, "linewidth": 2},
        textprops={"color": FG_NORM, "fontsize": 10}
    )
    for at in autotexts:
        at.set_color(BG_DARK); at.set_fontweight("bold"); at.set_fontsize(9)

    ax.set_facecolor(BG_DARK)
    ax.set_title("Process Distribution by Group", color=FG_BLUE,
                 fontsize=11, fontweight="bold", pad=10)
    fig.tight_layout(pad=1.5)
    result = fig_to_b64(fig); plt.close(fig); return result


def make_history_chart() -> str:
    """Line chart: total process count over the last 60 refresh cycles."""
    fig, ax = plt.subplots(figsize=(7, 4), facecolor=BG_DARK)
    with _lock:
        hist = list(_history)

    if len(hist) < 2:
        ax.text(0.5, 0.5,
                "Collecting data…\nWaiting for more refresh cycles",
                transform=ax.transAxes, ha="center", va="center",
                color=FG_NORM, fontsize=11)
        apply_chart_style(ax, "Total Process Count Over Time")
        fig.tight_layout(pad=1.5)
        result = fig_to_b64(fig); plt.close(fig); return result

    times  = [h["time"]  for h in hist]
    totals = [h["total"] for h in hist]

    ax.plot(range(len(times)), totals, color=FG_BLUE, linewidth=2,
            marker="o", markersize=5, markerfacecolor=FG_MAUVE,
            markeredgecolor=BG_DARK, markeredgewidth=1.5)
    ax.fill_between(range(len(times)), totals, alpha=0.15, color=FG_BLUE)

    step = max(1, len(times) // 8)
    ax.set_xticks(range(0, len(times), step))
    ax.set_xticklabels(
        [times[i] for i in range(0, len(times), step)],
        rotation=30, ha="right", fontsize=8
    )
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    apply_chart_style(ax, "Total Process Count Over Time")
    ax.set_ylabel("Total", fontsize=10)
    fig.tight_layout(pad=1.5)
    result = fig_to_b64(fig); plt.close(fig); return result


def make_heatmap(data: list) -> str:
    """
    Heatmap: server (rows) × group (columns), colour-coded by process count.
    Shows top-30 servers sorted by total count descending.
    """
    fig, ax = plt.subplots(figsize=(7, 6), facecolor=BG_DARK)
    if not data:
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes,
                ha="center", va="center", color=FG_NORM)
        result = fig_to_b64(fig); plt.close(fig); return result

    # Build unique sorted server / group lists
    all_servers = sorted({
        srv
        for d in data
        for srv in d["server"].split(", ")
    })
    groups = sorted({d["group"] for d in data})

    matrix = np.zeros((len(all_servers), len(groups)))
    for d in data:
        for srv in d["server"].split(", "):
            if srv in all_servers:
                si = all_servers.index(srv)
                gi = groups.index(d["group"])
                matrix[si][gi] += d["count"]

    # Keep only top-30 rows by total count
    row_sums = matrix.sum(axis=1)
    top_idx  = row_sums.argsort()[::-1][:30]
    matrix   = matrix[top_idx]
    srv_lbls = [all_servers[i] for i in top_idx]

    im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn_r",
                   interpolation="nearest",
                   vmin=0, vmax=max(ALERT_THRESHOLD, matrix.max() or 1))

    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels(groups, fontsize=10, color=FG_NORM)
    ax.set_yticks(range(len(srv_lbls)))
    ax.set_yticklabels(srv_lbls, fontsize=8, color=FG_NORM, fontfamily="monospace")

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.ax.tick_params(colors=FG_NORM, labelsize=8)

    # Annotate non-zero cells
    for i in range(len(srv_lbls)):
        for j in range(len(groups)):
            v = int(matrix[i, j])
            if v > 0:
                ax.text(j, i, str(v), ha="center", va="center",
                        color="white" if v >= ALERT_THRESHOLD else FG_NORM,
                        fontsize=8,
                        fontweight="bold" if v >= ALERT_THRESHOLD else "normal")

    apply_chart_style(ax, "Heatmap: Server × Group Process Count")
    fig.tight_layout(pad=1.5)
    result = fig_to_b64(fig); plt.close(fig); return result

# ==============================================================================
#  HTML TEMPLATE
# ==============================================================================

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>⚡ LICENSE CHECK Monitor v{{ version }}</title>
<style>
  /* ── CSS VARIABLES (Catppuccin Mocha palette) ── */
  :root {
    --bg-dark:   #1e1e2e;
    --bg-panel:  #2a2a3e;
    --bg-alt:    #252535;
    --fg-norm:   #cdd6f4;
    --fg-green:  #a6e3a1;
    --fg-red:    #f38ba8;
    --fg-yellow: #f9e2af;
    --fg-blue:   #89b4fa;
    --fg-teal:   #94e2d5;
    --fg-mauve:  #cba6f7;
    --border:    #45475a;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg-dark); color: var(--fg-norm);
    font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 13px; min-height: 100vh;
  }

  /* ── TOP BAR ── */
  .topbar {
    background: var(--bg-panel);
    padding: 8px 16px;
    display: flex; align-items: center; gap: 12px;
    border-bottom: 1px solid var(--border); flex-wrap: wrap;
  }
  .topbar .title {
    color: var(--fg-mauve); font-size: 15px; font-weight: 700;
    white-space: nowrap;
  }
  .topbar .version-badge {
    background: rgba(203,166,247,0.2); color: var(--fg-mauve);
    font-size: 10px; padding: 2px 8px; border-radius: 10px; font-weight: 700;
  }
  .topbar label { color: var(--fg-blue); font-weight: 600; font-size: 12px; }
  .topbar input[type=text] {
    background: #313244; color: var(--fg-norm);
    border: 1px solid var(--border); border-radius: 4px;
    padding: 5px 10px; font-family: inherit; font-size: 12px; width: 300px;
  }
  .topbar select {
    background: #313244; color: var(--fg-norm);
    border: 1px solid var(--border); border-radius: 4px;
    padding: 4px 8px; font-family: inherit; font-size: 12px;
  }
  /* Sum-by-user checkbox highlight */
  .sum-toggle {
    display: flex; align-items: center; gap: 6px;
    background: rgba(148,226,213,0.1); border: 1px solid var(--fg-teal);
    border-radius: 5px; padding: 4px 10px; cursor: pointer;
  }
  .sum-toggle input { cursor: pointer; accent-color: var(--fg-teal); width: 14px; height: 14px; }
  .sum-toggle label { color: var(--fg-teal); font-weight: 700; cursor: pointer; font-size: 12px; }
  .sum-toggle.active { background: rgba(148,226,213,0.2); box-shadow: 0 0 6px rgba(148,226,213,0.3); }

  .btn {
    padding: 5px 12px; border: none; border-radius: 5px;
    font-family: inherit; font-size: 12px; font-weight: 700;
    cursor: pointer; transition: all 0.15s;
  }
  .btn-accent { background: var(--fg-blue); color: var(--bg-dark); }
  .btn-accent:hover { background: var(--fg-teal); }
  .status {
    margin-left: auto; color: var(--fg-green);
    font-size: 11px; white-space: nowrap;
  }
  .countdown {
    background: rgba(137,180,250,0.15); color: var(--fg-blue);
    padding: 3px 10px; border-radius: 20px; font-size: 11px;
    font-weight: 700; min-width: 60px; text-align: center;
  }
  .author-info {
    font-size: 10px; color: #585b70; white-space: nowrap;
  }

  /* ── SUMMARY BAR ── */
  .summary-bar {
    background: var(--bg-panel); padding: 8px 20px;
    display: flex; gap: 24px; align-items: center;
    border-bottom: 1px solid var(--border); flex-wrap: wrap;
  }
  .metric { display: flex; flex-direction: column; align-items: center; }
  .metric .val { font-size: 22px; font-weight: 800; line-height: 1; }
  .metric .lbl { font-size: 10px; color: var(--fg-blue); margin-top: 2px; }
  .metric.total   .val { color: var(--fg-yellow); }
  .metric.alerts  .val { color: var(--fg-red); }
  .metric.servers .val { color: var(--fg-teal); }
  .metric.records .val { color: var(--fg-green); }
  .mode-badge {
    background: rgba(148,226,213,0.15); color: var(--fg-teal);
    border: 1px solid var(--fg-teal); border-radius: 4px;
    padding: 3px 10px; font-size: 10px; font-weight: 700;
    display: none;
  }
  .mode-badge.visible { display: inline-block; }
  .summary-bar .updated { margin-left: auto; color: var(--fg-blue); font-size: 11px; }
  .sep { width: 1px; height: 38px; background: var(--border); }

  /* ── MAIN LAYOUT ── */
  .main {
    display: grid; grid-template-columns: 55% 1fr;
    gap: 10px; padding: 10px;
    height: calc(100vh - 128px);
  }
  .panel {
    background: var(--bg-panel);
    border-radius: 8px; border: 1px solid var(--border);
    overflow: hidden; display: flex; flex-direction: column;
  }
  .panel-header {
    background: var(--bg-dark); padding: 8px 14px;
    color: var(--fg-blue); font-weight: 700; font-size: 12px;
    border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 10px;
  }
  .panel-body { flex: 1; overflow: auto; }

  /* ── FILTER BAR ── */
  .filter-bar {
    padding: 6px 10px; background: var(--bg-dark);
    display: flex; gap: 8px; align-items: center;
    border-bottom: 1px solid var(--border); flex-wrap: wrap;
  }
  .filter-bar label { color: var(--fg-blue); font-size: 11px; }
  .filter-bar input {
    background: #313244; color: var(--fg-norm);
    border: 1px solid var(--border); border-radius: 4px;
    padding: 4px 8px; font-family: inherit; font-size: 11px; width: 170px;
  }
  .filter-bar select {
    background: #313244; color: var(--fg-norm);
    border: 1px solid var(--border); border-radius: 4px;
    padding: 4px 8px; font-family: inherit; font-size: 11px;
  }

  /* ── TABLE ── */
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  thead th {
    background: var(--bg-dark); color: var(--fg-blue);
    padding: 7px 10px; text-align: left;
    border-bottom: 2px solid var(--border);
    position: sticky; top: 0; z-index: 1;
    cursor: pointer; user-select: none; white-space: nowrap;
  }
  thead th:hover { color: var(--fg-teal); }
  thead th.sorted-asc::after  { content: " ▲"; color: var(--fg-yellow); }
  thead th.sorted-desc::after { content: " ▼"; color: var(--fg-yellow); }
  tbody tr { border-bottom: 1px solid rgba(69,71,90,0.3); cursor: pointer; }
  tbody tr:hover { background: rgba(137,180,250,0.10) !important; animation: none !important; }
  tbody td { padding: 6px 10px; }

  tr.row-alert { background: rgba(243,139,168,0.12); }
  tr.row-warn  { background: rgba(249,226,175,0.08); }
  tr.row-odd   { background: rgba(255,255,255,0.02); }
  tr.row-even  { background: transparent; }

  td.cnt-alert  { color: var(--fg-red);    font-weight: 800; }
  td.cnt-warn   { color: var(--fg-yellow); font-weight: 700; }
  td.cnt-normal { color: var(--fg-green);  font-weight: 600; }

  .badge {
    display: inline-block; padding: 2px 7px; border-radius: 3px;
    font-size: 10px; font-weight: 700;
  }
  .badge-pid1  { background: rgba(137,180,250,0.2); color: var(--fg-blue); }
  .badge-pid3  { background: rgba(203,166,247,0.2); color: var(--fg-mauve); }
  .badge-eo    { background: rgba(148,226,213,0.2); color: var(--fg-teal); }
  .badge-ac    { background: rgba(249,226,175,0.2); color: var(--fg-yellow); }
  .badge-other { background: rgba(166,227,161,0.2); color: var(--fg-green); }

  @keyframes pulse-red {
    0%,100% { background: rgba(243,139,168,0.12); }
    50%     { background: rgba(243,139,168,0.24); }
  }
  tr.row-alert { animation: pulse-red 2s ease-in-out infinite; }

  /* ── CHARTS ── */
  .chart-tabs {
    display: flex; border-bottom: 1px solid var(--border);
    background: var(--bg-dark);
  }
  .chart-tab {
    padding: 7px 14px; cursor: pointer;
    color: var(--fg-norm); font-size: 12px; font-weight: 600;
    border-bottom: 2px solid transparent; transition: all 0.15s;
  }
  .chart-tab:hover { color: var(--fg-blue); }
  .chart-tab.active { color: var(--fg-blue); border-bottom-color: var(--fg-blue); }
  .chart-pane { display: none; }
  .chart-pane.active {
    display: flex; justify-content: center;
    align-items: flex-start; padding: 8px;
  }
  .chart-pane img { max-width: 100%; height: auto; border-radius: 4px; }

  /* ── SPINNER ── */
  .spinner {
    display: inline-block; width: 13px; height: 13px;
    border: 2px solid var(--fg-blue); border-top-color: transparent;
    border-radius: 50%; animation: spin 0.7s linear infinite;
    vertical-align: middle;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── LOG VIEWER MODAL ── */
  .modal-overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,0.7); z-index: 1000;
    justify-content: center; align-items: center;
  }
  .modal-overlay.open { display: flex; }
  .modal {
    background: var(--bg-panel); border: 1px solid var(--border);
    border-radius: 10px; width: 90vw; max-width: 860px;
    max-height: 85vh; display: flex; flex-direction: column;
    box-shadow: 0 20px 60px rgba(0,0,0,0.5);
  }
  .modal-header {
    background: var(--bg-dark); padding: 12px 18px;
    display: flex; align-items: center; gap: 10px;
    border-bottom: 1px solid var(--border); border-radius: 10px 10px 0 0;
  }
  .modal-title { color: var(--fg-blue); font-size: 13px; font-weight: 700; flex: 1; }
  .modal-close {
    background: var(--fg-red); color: var(--bg-dark);
    border: none; border-radius: 4px; padding: 4px 10px;
    font-size: 12px; font-weight: 700; cursor: pointer;
  }
  .modal-body { flex: 1; overflow: auto; padding: 14px 18px; }
  .bjobs-cmd {
    background: #181825; color: var(--fg-teal);
    padding: 8px 12px; border-radius: 5px; font-size: 11px;
    margin-bottom: 12px; border-left: 3px solid var(--fg-teal);
  }
  .job-card {
    background: #181825; border: 1px solid var(--border);
    border-radius: 6px; margin-bottom: 10px; overflow: hidden;
  }
  .job-card-header {
    background: #1e1e2e; padding: 7px 12px;
    display: flex; align-items: center; gap: 8px;
    border-bottom: 1px solid var(--border);
  }
  .job-card-header .ji { color: var(--fg-mauve); font-weight: 700; font-size: 12px; }
  .job-card-body { padding: 10px 12px; font-size: 11px; }
  .path-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 6px; }
  .path-label { color: var(--fg-blue); font-size: 10px; text-transform: uppercase; }
  .path-value {
    color: var(--fg-green); font-family: monospace; font-size: 11px;
    background: #11111b; padding: 5px 10px; border-radius: 4px;
    word-break: break-all; cursor: pointer;
    border: 1px solid transparent; transition: border 0.15s;
  }
  .path-value:hover { border-color: var(--fg-teal); color: var(--fg-teal); }
  .full-path-row .path-value {
    color: var(--fg-yellow); font-weight: 700;
    background: rgba(249,226,175,0.05); border-color: rgba(249,226,175,0.2);
  }
  .copy-hint { font-size: 9px; color: #585b70; margin-top: 2px; }
  .no-jobs { color: #585b70; text-align: center; padding: 30px; font-size: 12px; }
  .modal-spinner { text-align: center; padding: 40px; }

  /* ── LOG BAR (bottom status) ── */
  .log-bar {
    background: var(--bg-panel); border-top: 1px solid var(--border);
    padding: 5px 16px; font-size: 10px; color: var(--fg-teal);
    max-height: 30px; overflow: hidden;
    position: fixed; bottom: 0; left: 0; right: 0;
  }
  .log-bar .err  { color: var(--fg-red); }
  .log-bar .warn { color: var(--fg-yellow); }

  @media (max-width: 900px) { .main { grid-template-columns: 1fr; } }
</style>
</head>
<body>

<!-- ═══════════════════ TOP BAR ═══════════════════ -->
<div class="topbar">
  <span class="title">⚡ {{ app_name }}</span>
  <span class="version-badge">v{{ version }}</span>

  <label>📂 File:</label>
  <input type="text" id="filepath" value="{{ data_file }}"
         placeholder="/path/to/list.map.post">

  <button class="btn btn-accent" onclick="manualRefresh()">🔄 Refresh Now</button>

  <label style="display:flex;align-items:center;gap:6px;">
    <input type="checkbox" id="autoRefresh" checked onchange="toggleAuto()"> Auto
  </label>
  <label>Interval:</label>
  <select id="intervalSel" onchange="updateInterval()">
    <option value="5" selected>5s</option>
    <option value="10">10s</option>
    <option value="30">30s</option>
    <option value="60">60s</option>
  </select>
  <span class="countdown" id="countdown">— s</span>

  <!-- SUM BY USER CHECKBOX (active by default) -->
  <div class="sum-toggle active" id="sumToggleWrap" onclick="toggleSumMode()">
    <input type="checkbox" id="sumByUser" checked>
    <label for="sumByUser">∑ Sum by User</label>
  </div>

  <span class="status" id="statusBar">⏳ Loading…</span>
  <span class="author-info">👤 {{ author }}</span>
</div>

<!-- ═══════════════════ SUMMARY BAR ═══════════════════ -->
<div class="summary-bar">
  <div class="metric total">
    <span class="val" id="metTotal">—</span>
    <span class="lbl">TOTAL PROCESSES</span>
  </div>
  <div class="sep"></div>
  <div class="metric alerts">
    <span class="val" id="metAlerts">—</span>
    <span class="lbl">🔴 ALERTS (≥{{ threshold }})</span>
  </div>
  <div class="sep"></div>
  <div class="metric servers">
    <span class="val" id="metServers">—</span>
    <span class="lbl">SERVERS</span>
  </div>
  <div class="sep"></div>
  <div class="metric records">
    <span class="val" id="metRecords">—</span>
    <span class="lbl">RECORDS</span>
  </div>
  <span class="mode-badge" id="modeBadge">∑ SUM-BY-USER MODE</span>
  <span class="updated" id="updatedAt">—</span>
</div>

<!-- ═══════════════════ MAIN CONTENT ═══════════════════ -->
<div class="main">

  <!-- ── LEFT: PROCESS TABLE ── -->
  <div class="panel">
    <div class="panel-header">
      📋 Process List
      <span id="tableSpinner" class="spinner" style="display:none"></span>
    </div>
    <div class="filter-bar">
      <label>🔍 Filter:</label>
      <input type="text" id="filterText"
             placeholder="server / user / group…" oninput="filterTable()">
      <label>Group:</label>
      <select id="filterGroup" onchange="filterTable()">
        <option value="">ALL</option>
      </select>
      <label style="margin-left:auto;font-size:11px;" id="rowCount">0 rows</label>
    </div>
    <div class="panel-body">
      <table>
        <thead>
          <tr>
            <th onclick="sortTable('count')"    id="th-count">Count</th>
            <th onclick="sortTable('server')"   id="th-server">Server</th>
            <th onclick="sortTable('username')" id="th-username">Username</th>
            <th onclick="sortTable('group')"    id="th-group">Group</th>
            <th style="cursor:default">Jobs</th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>
  </div>

  <!-- ── RIGHT: CHARTS ── -->
  <div class="panel">
    <div class="chart-tabs">
      <div class="chart-tab active" onclick="showChart('bar')">📊 Bar</div>
      <div class="chart-tab"       onclick="showChart('pie')">🥧 Pie</div>
      <div class="chart-tab"       onclick="showChart('hist')">📈 History</div>
      <div class="chart-tab"       onclick="showChart('heat')">🌡 Heatmap</div>
    </div>
    <div class="panel-body">
      <div class="chart-pane active" id="pane-bar"><img  id="img-bar"  src="" alt="bar chart"></div>
      <div class="chart-pane"        id="pane-pie"><img  id="img-pie"  src="" alt="pie chart"></div>
      <div class="chart-pane"        id="pane-hist"><img id="img-hist" src="" alt="history chart"></div>
      <div class="chart-pane"        id="pane-heat"><img id="img-heat" src="" alt="heatmap"></div>
    </div>
  </div>
</div>

<!-- ═══════════════════ BJOBS LOG VIEWER MODAL ═══════════════════ -->
<div class="modal-overlay" id="logModal">
  <div class="modal">
    <div class="modal-header">
      <span class="modal-title" id="modalTitle">Jobs for user</span>
      <button class="modal-close" onclick="closeModal()">✕ Close</button>
    </div>
    <div class="modal-body" id="modalBody">
      <div class="modal-spinner"><span class="spinner"></span> Loading bjobs…</div>
    </div>
  </div>
</div>

<!-- ═══════════════════ STATUS LOG BAR ═══════════════════ -->
<div class="log-bar" id="logBar">Ready.</div>

<script>
/* ====================================================================
   GLOBAL STATE
   ==================================================================== */
let allData    = [];   // raw records from /api/data
let sortCol    = 'server';
let sortAsc    = true;
let autoTimer  = null;
let countdown  = 0;
let refreshInt = 5;    // seconds
let sumByUser  = true; // Sum-by-User mode (default ON)

const THRESHOLD = {{ threshold }};

/* ====================================================================
   UTILITY
   ==================================================================== */
function log(msg, level = '') {
  const lb  = document.getElementById('logBar');
  const ts  = new Date().toLocaleTimeString();
  const tag = level ? `<span class="${level}">[${level.toUpperCase()}]</span> ` : '';
  lb.innerHTML = `<b>${ts}</b> ${tag}${msg}`;
}
function setStatus(msg) { document.getElementById('statusBar').textContent = msg; }

/* ====================================================================
   SUM-BY-USER MODE
   ==================================================================== */
function toggleSumMode() {
  const cb   = document.getElementById('sumByUser');
  const wrap = document.getElementById('sumToggleWrap');
  // cb.checked is toggled by the click propagation on the input itself;
  // when called from the wrapper div we need to flip manually
  if (event && event.target !== cb) cb.checked = !cb.checked;
  sumByUser = cb.checked;
  wrap.classList.toggle('active', sumByUser);
  document.getElementById('modeBadge').classList.toggle('visible', sumByUser);
  renderTable(allData);
  refreshCharts();
}

/**
 * Collapse rows with the same username: sum counts, merge server lists.
 * Returns a new array sorted by count descending.
 */
function applySumByUser(data) {
  const map = {};
  data.forEach(row => {
    const u = row.username;
    if (!map[u]) map[u] = { count: 0, servers: new Set(), groups: {}, username: u };
    map[u].count += row.count;
    row.server.split(', ').forEach(s => map[u].servers.add(s));
    map[u].groups[row.group] = (map[u].groups[row.group] || 0) + row.count;
  });
  return Object.values(map).map(m => ({
    count:    m.count,
    server:   [...m.servers].sort().join(', '),
    username: m.username,
    // Most common group for this user
    group:    Object.entries(m.groups).sort((a, b) => b[1] - a[1])[0][0],
  })).sort((a, b) => b.count - a.count || a.username.localeCompare(b.username));
}

/* ====================================================================
   DATA REFRESH
   ==================================================================== */
async function manualRefresh() {
  const fp = document.getElementById('filepath').value.trim();
  document.getElementById('tableSpinner').style.display = 'inline-block';
  setStatus('⏳ Loading…');
  try {
    const resp = await fetch(`/api/data?file=${encodeURIComponent(fp)}`);
    const json = await resp.json();
    allData = json.data;
    updateSummary(json);
    updateGroupDropdown(allData);
    renderTable(allData);
    log(`Refreshed: ${json.data.length} records, Total=${json.total}, Alerts=${json.alerts}`);
    setStatus(`✅ OK — ${json.data.length} records | Total: ${json.total}`);
    refreshCharts();
  } catch (e) {
    log('Fetch error: ' + e, 'err');
    setStatus('❌ Error');
  }
  document.getElementById('tableSpinner').style.display = 'none';
}

async function refreshCharts() {
  const fp  = document.getElementById('filepath').value.trim();
  const sum = sumByUser ? '1' : '0';
  for (const t of ['bar', 'pie', 'hist', 'heat']) {
    try {
      const r = await fetch(`/api/chart/${t}?file=${encodeURIComponent(fp)}&sum=${sum}`);
      const j = await r.json();
      document.getElementById(`img-${t}`).src = 'data:image/png;base64,' + j.img;
    } catch (e) { /* silently ignore chart errors */ }
  }
}

function toggleAuto() {
  const on = document.getElementById('autoRefresh').checked;
  if (on) startAuto(); else stopAuto();
}
function updateInterval() {
  refreshInt = parseInt(document.getElementById('intervalSel').value);
  if (document.getElementById('autoRefresh').checked) { stopAuto(); startAuto(); }
}
function startAuto() {
  stopAuto();
  countdown = refreshInt;
  autoTimer = setInterval(() => {
    countdown--;
    document.getElementById('countdown').textContent = countdown + ' s';
    if (countdown <= 0) { countdown = refreshInt; manualRefresh(); }
  }, 1000);
}
function stopAuto() {
  if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
  document.getElementById('countdown').textContent = '— s';
}

/* ====================================================================
   SUMMARY BAR
   ==================================================================== */
function updateSummary(json) {
  // When sum-by-user is on, recompute alerts from the merged data
  const display = sumByUser ? applySumByUser(json.data) : json.data;
  const alerts  = display.filter(r => r.count >= THRESHOLD).length;

  document.getElementById('metTotal').textContent   = json.total;
  document.getElementById('metAlerts').textContent  = alerts;
  document.getElementById('metServers').textContent = json.servers;
  document.getElementById('metRecords').textContent = json.data.length;
  document.getElementById('updatedAt').textContent  = '🕐 ' + json.timestamp;
}

/* ====================================================================
   TABLE RENDERING
   ==================================================================== */
function renderTable(data) {
  // Apply Sum-by-User mode if enabled
  let rows = sumByUser ? applySumByUser(data) : [...data];

  // Apply text filter
  const fText = document.getElementById('filterText').value.trim().toLowerCase();
  const fGrp  = document.getElementById('filterGroup').value;
  if (fText) rows = rows.filter(r =>
    r.server.toLowerCase().includes(fText) ||
    r.username.toLowerCase().includes(fText) ||
    r.group.toLowerCase().includes(fText));
  if (fGrp) rows = rows.filter(r => r.group === fGrp);

  // Apply column sort
  rows.sort((a, b) => {
    let va = a[sortCol], vb = b[sortCol];
    if (sortCol === 'count') { va = +va; vb = +vb; }
    return sortAsc
      ? (va < vb ? -1 : va > vb ? 1 : 0)
      : (va > vb ? -1 : va < vb ? 1 : 0);
  });

  const tbody = document.getElementById('tableBody');
  tbody.innerHTML = '';

  rows.forEach((row, i) => {
    const cnt = row.count;
    let rowCls = i % 2 === 0 ? 'row-even' : 'row-odd';
    let cntCls = 'cnt-normal';
    if (cnt >= THRESHOLD)    { rowCls = 'row-alert'; cntCls = 'cnt-alert'; }
    else if (cnt === THRESHOLD - 1) { rowCls = 'row-warn';  cntCls = 'cnt-warn'; }

    const badge      = getBadge(row.group);
    const alertIcon  = cnt >= THRESHOLD ? '🔴 ' : '';
    // Truncate long server lists for display, show full on hover
    const srvDisplay = row.server.length > 40
      ? row.server.substring(0, 38) + '…'
      : row.server;

    const tr = document.createElement('tr');
    tr.className = rowCls;
    tr.title     = `Click to view bjobs for ${row.username}`;
    tr.innerHTML = `
      <td class="${cntCls}">${alertIcon}${cnt}</td>
      <td><code style="color:var(--fg-teal);font-size:11px;" title="${row.server}">${srvDisplay}</code></td>
      <td>${row.username}</td>
      <td>${badge}</td>
      <td>
        <button onclick="openJobModal('${row.username}')" title="View bjobs for ${row.username}"
          style="background:rgba(137,180,250,0.15);color:var(--fg-blue);border:1px solid var(--fg-blue);
                 border-radius:4px;padding:2px 8px;font-size:10px;cursor:pointer;font-family:inherit;">
          📋 jobs
        </button>
      </td>`;
    tbody.appendChild(tr);
  });

  document.getElementById('rowCount').textContent = rows.length + ' rows';

  // Update ALERTS metric based on currently displayed mode
  const alerts = rows.filter(r => r.count >= THRESHOLD).length;
  document.getElementById('metAlerts').textContent = alerts;
}

function getBadge(group) {
  const g   = (group || '').toLowerCase();
  let   cls = 'badge-other';
  if (g === 'pid1') cls = 'badge-pid1';
  else if (g === 'pid3') cls = 'badge-pid3';
  else if (g === 'eo')   cls = 'badge-eo';
  else if (g === 'ac')   cls = 'badge-ac';
  return `<span class="badge ${cls}">${group}</span>`;
}

function filterTable() { renderTable(allData); }

function sortTable(col) {
  if (sortCol === col) sortAsc = !sortAsc;
  else { sortCol = col; sortAsc = true; }
  ['count','server','username','group'].forEach(c => {
    const th = document.getElementById('th-' + c);
    th.className = c === sortCol ? (sortAsc ? 'sorted-asc' : 'sorted-desc') : '';
  });
  renderTable(allData);
}

function updateGroupDropdown(data) {
  const groups = [...new Set(data.map(d => d.group))].sort();
  const sel    = document.getElementById('filterGroup');
  const cur    = sel.value;
  sel.innerHTML = '<option value="">ALL</option>';
  groups.forEach(g => {
    const opt = document.createElement('option');
    opt.value = g; opt.textContent = g;
    if (g === cur) opt.selected = true;
    sel.appendChild(opt);
  });
}

/* ====================================================================
   CHART TABS
   ==================================================================== */
function showChart(type) {
  document.querySelectorAll('.chart-tab').forEach((t, i) => {
    t.classList.toggle('active', ['bar','pie','hist','heat'][i] === type);
  });
  document.querySelectorAll('.chart-pane').forEach(p => {
    p.classList.toggle('active', p.id === 'pane-' + type);
  });
}

/* ====================================================================
   BJOBS LOG VIEWER MODAL
   ==================================================================== */
async function openJobModal(username) {
  const modal = document.getElementById('logModal');
  const body  = document.getElementById('modalBody');
  document.getElementById('modalTitle').textContent =
    `📋 Jobs for: ${username}  [bjobs -u ${username} -o "SUB_CWD JOB_NAME" -noheader]`;
  body.innerHTML = '<div class="modal-spinner"><span class="spinner"></span> Running bjobs…</div>';
  modal.classList.add('open');

  try {
    const resp = await fetch(`/api/bjobs?user=${encodeURIComponent(username)}`);
    const json = await resp.json();
    renderJobModal(body, json, username);
  } catch (e) {
    body.innerHTML = `<div class="no-jobs">❌ Error fetching jobs: ${e}</div>`;
  }
}

function renderJobModal(body, json, username) {
  if (json.error) {
    body.innerHTML = `<div class="no-jobs">⚠️ ${json.error}</div>`;
    return;
  }
  if (!json.jobs || json.jobs.length === 0) {
    body.innerHTML = `<div class="no-jobs">No active jobs found for <b>${username}</b>.</div>`;
    return;
  }

  // Show the command used
  let html = `<div class="bjobs-cmd">$ bjobs -u ${username} -o "SUB_CWD JOB_NAME" -noheader</div>`;

  json.jobs.forEach((job, idx) => {
    const isDiff = job.full_path !== job.sub_cwd + '/' + job.job_name
                   && job.full_path !== job.job_name;
    html += `
    <div class="job-card">
      <div class="job-card-header">
        <span class="ji">Job #${idx + 1}</span>
      </div>
      <div class="job-card-body">
        <div class="path-row">
          <span class="path-label">SUB_CWD (Submit directory)</span>
          <span class="path-value" onclick="copyPath(this)" title="Click to copy">${escHtml(job.sub_cwd)}</span>
        </div>
        <div class="path-row">
          <span class="path-label">JOB_NAME (Log filename)</span>
          <span class="path-value" onclick="copyPath(this)" title="Click to copy">${escHtml(job.job_name)}</span>
        </div>
        <div class="path-row full-path-row">
          <span class="path-label">⭐ FULL LOG PATH (assembled)</span>
          <span class="path-value" onclick="copyPath(this)" title="Click to copy">${escHtml(job.full_path)}</span>
          <span class="copy-hint">👆 Click to copy path • Rule: SUB_CWD ends with /pr → join with JOB_NAME</span>
        </div>
      </div>
    </div>`;
  });

  body.innerHTML = html;
}

function closeModal() {
  document.getElementById('logModal').classList.remove('open');
}

function copyPath(el) {
  navigator.clipboard.writeText(el.textContent.trim()).then(() => {
    const orig = el.style.borderColor;
    el.style.borderColor = 'var(--fg-green)';
    setTimeout(() => el.style.borderColor = orig, 800);
    log('Copied path: ' + el.textContent.trim().substring(0, 60) + '…');
  });
}

function escHtml(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Close modal when clicking the overlay background
document.getElementById('logModal').addEventListener('click', function(e) {
  if (e.target === this) closeModal();
});

/* ====================================================================
   INIT
   ==================================================================== */
window.onload = () => {
  // Reflect initial checkbox state
  sumByUser = document.getElementById('sumByUser').checked;
  document.getElementById('modeBadge').classList.toggle('visible', sumByUser);
  manualRefresh();
  startAuto();
};
</script>
</body>
</html>
"""

# ==============================================================================
#  FLASK ROUTES
# ==============================================================================

@app.route("/")
def index():
    return render_template_string(
        HTML_TEMPLATE,
        app_name=APP_NAME,
        version=APP_VERSION,
        author=APP_AUTHOR,
        data_file=DATA_FILE,
        threshold=ALERT_THRESHOLD,
    )


@app.route("/api/data")
def api_data():
    """Return parsed process records + summary statistics."""
    global DATA_FILE
    fp = request.args.get("file", DATA_FILE).strip()
    if fp and os.path.exists(fp):
        DATA_FILE = fp  # update global path for background thread

    data = parse_map_file(fp)
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total   = sum(d["count"] for d in data)
    alerts  = sum(1 for d in data if d["count"] >= ALERT_THRESHOLD)
    servers = len({d["server"] for d in data})

    # Update the shared cache and rolling history
    with _lock:
        _cache.update({"data": data, "timestamp": ts,
                       "total": total, "alerts": alerts})
        _history.append({"time": ts.split(" ")[1], "total": total})
        if len(_history) > 60:
            _history[:] = _history[-60:]

    return jsonify(data=data, timestamp=ts,
                   total=total, alerts=alerts, servers=servers)


@app.route("/api/chart/<chart_type>")
def api_chart(chart_type):
    """Generate and return a chart as base64 PNG."""
    fp  = request.args.get("file", DATA_FILE).strip()
    sum_mode = request.args.get("sum", "0") == "1"

    raw_data = parse_map_file(fp) if (fp and os.path.exists(fp)) else _cache["data"]

    # Apply user-sum aggregation for charts if requested
    if sum_mode:
        chart_data = aggregate_by_user(raw_data)
    else:
        chart_data = raw_data

    if chart_type == "bar":
        img = make_bar_chart(chart_data)
    elif chart_type == "pie":
        img = make_pie_chart(chart_data)
    elif chart_type == "hist":
        img = make_history_chart()          # history is global, not per-mode
    elif chart_type == "heat":
        img = make_heatmap(chart_data)
    else:
        return jsonify(error=f"Unknown chart type: {chart_type}"), 400

    return jsonify(img=img)


@app.route("/api/bjobs")
def api_bjobs():
    """
    Run bjobs for the given user and return parsed job list with full log paths.
    Query param: user=<username>
    """
    username = request.args.get("user", "").strip()
    if not username:
        return jsonify(jobs=[], raw="", error="Missing 'user' parameter"), 400
    result = run_bjobs(username)
    return jsonify(**result)


@app.route("/api/health")
def api_health():
    """Simple health check endpoint."""
    return jsonify(
        status="ok",
        version=APP_VERSION,
        author=APP_AUTHOR,
        timestamp=datetime.now().isoformat(),
    )


# ==============================================================================
#  ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    # Generate sample data if the production file doesn't exist
    if not os.path.exists(DATA_FILE):
        sample = "/tmp/list.map.post"
        try:
            import generate_sample_data as gsd
            gsd.generate_data(sample)
            DATA_FILE = sample
            print(f"[INFO] Using sample data at {sample}")
        except Exception as e:
            print(f"[WARN] Could not generate sample data: {e}")

    # Populate the cache immediately before accepting requests
    refresh_cache()

    # Start the background refresh daemon thread
    t = threading.Thread(target=background_thread, daemon=True)
    t.start()

    print("=" * 62)
    print(f"  ⚡ {APP_NAME}  v{APP_VERSION}")
    print(f"  Author   : {APP_AUTHOR}")
    print(f"  Data file: {DATA_FILE}")
    print(f"  Refresh  : every {REFRESH_INTERVAL}s")
    print(f"  Alert    : count >= {ALERT_THRESHOLD}")
    print("  URL      : http://0.0.0.0:7860")
    print("=" * 62)

    app.run(host="0.0.0.0", port=7860, debug=False, threaded=True)
