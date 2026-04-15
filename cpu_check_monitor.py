#!/usr/bin/env python3
# ==============================================================================
#  Version : 0.3          Date : 2026-04-16
#  Project : All
#  File    : cpu_check_monitor.py
#  Function: Tkinter GUI for LICENSE/CPU check monitoring.
#            Reads list.map.post, displays process table with real-time refresh,
#            column charts, and a bjobs log viewer panel.
#  Author  : RickTran (Tran Dang Vinh Khang)
#  History :
#    v0.1 : Initial Tkinter layout with table + charts
#    v0.2 : Real-time refresh, dark theme, filter bar
#    v0.3 : Sum-by-User mode, bjobs log viewer, English comments,
#            version info in title bar, full-path log assembly
# ==============================================================================

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import subprocess
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.ticker as mticker

# ==============================================================================
#  APPLICATION CONSTANTS
# ==============================================================================

APP_VERSION = "0.3"
APP_AUTHOR  = "RickTran (Tran Dang Vinh Khang)"
APP_NAME    = "LICENSE CHECK Monitor"

# --- Dark theme colour palette (Catppuccin Mocha) ---
BG_DARK    = "#1e1e2e"
BG_PANEL   = "#2a2a3e"
BG_ROW_ODD = "#252535"
BG_ROW_EVN = "#2a2a3e"
FG_NORM    = "#cdd6f4"
FG_GREEN   = "#a6e3a1"
FG_RED     = "#f38ba8"
FG_YELLOW  = "#f9e2af"
FG_BLUE    = "#89b4fa"
FG_TEAL    = "#94e2d5"
FG_MAUVE   = "#cba6f7"
ACCENT     = "#89b4fa"

ALERT_THRESHOLD = 4   # count >= this value → red alert row

# ==============================================================================
#  DATA PARSING  (mirrors web_monitor.py logic)
# ==============================================================================

def parse_map_file(filepath: str) -> list:
    """
    Parse the list.map / list.map.post file.

    Line format:
      <license_id> <SERVER> ... -- <first>.<last> <GROUP>

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
        return [{"error": str(e)}]

    records = []
    for raw in lines:
        line  = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 4:
            continue

        license_id = parts[0]
        server     = parts[1]

        # Extract username / group from after the '--' separator
        try:
            di = parts.index("--")
        except ValueError:
            username = parts[-2].replace(" ", "")
            group    = parts[-1]
        else:
            after    = parts[di + 1:]
            if not after:
                continue
            group    = after[-1]
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

    # Aggregate: count occurrences per (license_id, server, username, group)
    counter = Counter(
        (r["license_id"], r["server"], r["username"], r["group"])
        for r in records
    )
    result = []
    for (lid, srv, usr, grp), cnt in counter.items():
        result.append({
            "license_id": lid,
            "count":      cnt,
            "server":     srv,
            "username":   usr,
            "group":      grp,
        })
    result.sort(key=lambda x: x["server"])
    return result


def aggregate_by_user(data: list) -> list:
    """
    Collapse all rows with the same username into one row, summing counts.
    server field becomes a comma-separated list; group is the most common.
    Used when 'Sum by User' mode is enabled.
    """
    user_map = defaultdict(lambda: {"count": 0, "servers": [], "groups": []})
    for row in data:
        u = row["username"]
        user_map[u]["count"]   += row["count"]
        user_map[u]["servers"].append(row["server"])
        user_map[u]["groups"].append(row["group"])

    result = []
    for username, info in sorted(user_map.items()):
        top_group = Counter(info["groups"]).most_common(1)[0][0]
        srv_list  = sorted(set(info["servers"]))
        result.append({
            "license_id": "",
            "count":      info["count"],
            "server":     ", ".join(srv_list),
            "username":   username,
            "group":      top_group,
        })
    result.sort(key=lambda x: (-x["count"], x["username"]))
    return result

# ==============================================================================
#  BJOBS LOG VIEWER
# ==============================================================================

def run_bjobs(username: str) -> dict:
    """
    Execute: bjobs -u <username> -o "SUB_CWD JOB_NAME" -noheader
    Falls back to mock data when LSF is not installed.
    Returns {"jobs": [...], "raw": str, "error": str}
    """
    cmd = ["bjobs", "-u", username, "-o", "SUB_CWD JOB_NAME", "-noheader"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        raw  = proc.stdout.strip()
        if proc.returncode != 0 or not raw:
            raw = _mock_bjobs(username)
    except FileNotFoundError:
        raw = _mock_bjobs(username)
    except subprocess.TimeoutExpired:
        return {"jobs": [], "raw": "", "error": "bjobs timed out"}
    except Exception as e:
        return {"jobs": [], "raw": "", "error": str(e)}

    jobs = _parse_bjobs_output(raw)
    return {"jobs": jobs, "raw": raw, "error": ""}


def _mock_bjobs(username: str) -> str:
    """Fake bjobs output for environments without LSF."""
    base = f"/project/VAST_PI/WORKPLACE/{username.upper()}"
    return (
        f"{base}/run01/pr   sim_output/run01_corner_tt.log\n"
        f"{base}/run02/pr   sim_output/run02_corner_ff.log\n"
        f"{base}/verify     reports/timing_check.log\n"
        f"{base}/impl/pr    synth/netlist_check.log\n"
    )


def _parse_bjobs_output(raw: str) -> list:
    """Parse bjobs stdout and assemble full log paths."""
    jobs = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("SUB_CWD"):
            continue
        tokens   = line.split(None, 1)
        sub_cwd  = tokens[0] if tokens else ""
        job_name = tokens[1].strip() if len(tokens) > 1 else ""
        full     = _assemble_log_path(sub_cwd, job_name)
        jobs.append({"sub_cwd": sub_cwd, "job_name": job_name, "full_path": full})
    return jobs


def _assemble_log_path(sub_cwd: str, job_name: str) -> str:
    """
    Build the full log file path.
      - Absolute job_name  → use as-is.
      - Relative job_name  → join with sub_cwd (os.path.normpath applied).
    """
    if not job_name:
        return sub_cwd
    if job_name.startswith("/"):
        return job_name
    return os.path.normpath(os.path.join(sub_cwd, job_name))

# ==============================================================================
#  MAIN APPLICATION WINDOW
# ==============================================================================

class CpuCheckApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title(f"⚡ {APP_NAME}  v{APP_VERSION}  —  {APP_AUTHOR}")
        self.geometry("1440x860")
        self.configure(bg=BG_DARK)
        self.resizable(True, True)

        # --- Application state ---
        self.filepath     = tk.StringVar(
            value="/project/VAST_PI/WORKPLACE/CPU_CHECK/list.map.post")
        self.auto_refresh = tk.BooleanVar(value=True)
        self.refresh_secs = tk.IntVar(value=5)
        self.sum_by_user  = tk.BooleanVar(value=True)   # Sum-by-User default ON
        self.use_shell    = tk.BooleanVar(value=False)

        self.data         = []     # raw parsed records
        self._after_id    = None   # Tk.after() handle
        self.sort_col     = "server"
        self.sort_rev     = False
        self._history     = []     # list of (timestamp, total) for history chart

        self._build_styles()
        self._build_ui()
        self._schedule_refresh()

    # ==========================================================================
    #  TTK STYLES
    # ==========================================================================

    def _build_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=BG_DARK, foreground=FG_NORM,
                        font=("JetBrains Mono", 10))

        # --- Toolbar / panel frames ---
        style.configure("TB.TFrame", background=BG_PANEL)
        style.configure("TB.TLabel", background=BG_PANEL, foreground=FG_BLUE,
                        font=("JetBrains Mono", 10, "bold"))

        # --- Text entry ---
        style.configure("Dark.TEntry", fieldbackground="#313244",
                        foreground=FG_NORM, insertcolor=FG_NORM)

        # --- Buttons ---
        style.configure("Acc.TButton", background=ACCENT, foreground=BG_DARK,
                        font=("JetBrains Mono", 10, "bold"), relief="flat", padding=6)
        style.map("Acc.TButton",
                  background=[("active", FG_TEAL), ("pressed", FG_MAUVE)])

        style.configure("Sum.TButton", background=FG_TEAL, foreground=BG_DARK,
                        font=("JetBrains Mono", 10, "bold"), relief="flat", padding=6)

        # --- Treeview ---
        style.configure("CPU.Treeview",
                        background=BG_ROW_EVN, fieldbackground=BG_ROW_EVN,
                        foreground=FG_NORM, rowheight=24,
                        font=("JetBrains Mono", 10))
        style.configure("CPU.Treeview.Heading",
                        background=BG_PANEL, foreground=FG_BLUE,
                        font=("JetBrains Mono", 10, "bold"), relief="flat")
        style.map("CPU.Treeview",
                  background=[("selected", "#45475a")],
                  foreground=[("selected", FG_NORM)])

        # --- LabelFrame ---
        style.configure("D.TLabelframe",
                        background=BG_DARK, bordercolor="#45475a")
        style.configure("D.TLabelframe.Label",
                        background=BG_DARK, foreground=FG_BLUE,
                        font=("JetBrains Mono", 10, "bold"))

        # --- Checkbutton ---
        style.configure("D.TCheckbutton", background=BG_PANEL, foreground=FG_NORM)
        style.configure("Sum.TCheckbutton", background=BG_PANEL,
                        foreground=FG_TEAL, font=("JetBrains Mono", 10, "bold"))

        # --- Notebook (chart tabs) ---
        style.configure("TNotebook", background=BG_DARK, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_PANEL, foreground=FG_NORM,
                        font=("JetBrains Mono", 10), padding=[12, 6])
        style.map("TNotebook.Tab",
                  background=[("selected", BG_DARK)],
                  foreground=[("selected", FG_BLUE)])

        # --- Scrollbars ---
        style.configure("D.Vertical.TScrollbar",
                        background=BG_PANEL, troughcolor=BG_DARK,
                        arrowcolor=FG_BLUE, borderwidth=0)
        style.configure("D.Horizontal.TScrollbar",
                        background=BG_PANEL, troughcolor=BG_DARK,
                        arrowcolor=FG_BLUE, borderwidth=0)

    # ==========================================================================
    #  UI CONSTRUCTION
    # ==========================================================================

    def _build_ui(self):
        """Build all UI widgets: toolbar, summary bar, table, charts, log."""
        self._build_toolbar()
        self._build_summary_bar()
        self._build_main_area()
        self._build_log_bar()

    # --- Toolbar ---------------------------------------------------------------
    def _build_toolbar(self):
        tb = ttk.Frame(self, style="TB.TFrame", height=52)
        tb.pack(fill="x", side="top")
        tb.pack_propagate(False)

        tk.Label(tb, text=f"⚡ {APP_NAME}",
                 bg=BG_PANEL, fg=FG_MAUVE,
                 font=("JetBrains Mono", 13, "bold")).pack(side="left", padx=10)

        tk.Label(tb, text=f"v{APP_VERSION}",
                 bg=BG_PANEL, fg=FG_BLUE,
                 font=("JetBrains Mono", 9)).pack(side="left", padx=2)

        ttk.Separator(tb, orient="vertical").pack(side="left", fill="y", padx=8, pady=8)

        # File path
        ttk.Label(tb, text="File:", style="TB.TLabel").pack(side="left", padx=(4, 2))
        ttk.Entry(tb, textvariable=self.filepath,
                  width=48, style="Dark.TEntry").pack(side="left", padx=2, pady=8)
        ttk.Button(tb, text="📂", style="Acc.TButton",
                   command=self._browse_file).pack(side="left", padx=4)

        ttk.Separator(tb, orient="vertical").pack(side="left", fill="y", padx=8, pady=8)

        # Refresh controls
        ttk.Label(tb, text="Refresh (s):", style="TB.TLabel").pack(side="left", padx=2)
        tk.Spinbox(tb, from_=1, to=300, textvariable=self.refresh_secs,
                   width=4, bg="#313244", fg=FG_NORM,
                   buttonbackground=BG_PANEL, relief="flat",
                   font=("JetBrains Mono", 10)).pack(side="left", padx=2, pady=8)
        ttk.Checkbutton(tb, text="Auto", variable=self.auto_refresh,
                        style="D.TCheckbutton",
                        command=self._toggle_auto).pack(side="left", padx=4)
        ttk.Button(tb, text="🔄 Refresh Now", style="Acc.TButton",
                   command=self._manual_refresh).pack(side="left", padx=6)

        ttk.Separator(tb, orient="vertical").pack(side="left", fill="y", padx=8, pady=8)

        # Sum-by-User toggle (highlighted, active by default)
        self._sum_btn_var = tk.StringVar(value="∑ Sum by User  ✔")
        ttk.Checkbutton(tb, text="∑ Sum by User",
                        variable=self.sum_by_user,
                        style="Sum.TCheckbutton",
                        command=self._on_sum_toggle).pack(side="left", padx=6)

        # Author info (right side)
        tk.Label(tb, text=f"👤 {APP_AUTHOR}",
                 bg=BG_PANEL, fg="#585b70",
                 font=("JetBrains Mono", 8)).pack(side="right", padx=12)

        # Status indicator
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(tb, textvariable=self._status_var,
                 bg=BG_PANEL, fg=FG_GREEN,
                 font=("JetBrains Mono", 9)).pack(side="right", padx=8)

    # --- Summary bar -----------------------------------------------------------
    def _build_summary_bar(self):
        sb = tk.Frame(self, bg=BG_PANEL, height=48)
        sb.pack(fill="x")
        sb.pack_propagate(False)

        def metric(parent, var, lbl, color):
            f = tk.Frame(parent, bg=BG_PANEL)
            f.pack(side="left", padx=18)
            tk.Label(f, textvariable=var, bg=BG_PANEL, fg=color,
                     font=("JetBrains Mono", 20, "bold")).pack()
            tk.Label(f, text=lbl, bg=BG_PANEL, fg=FG_BLUE,
                     font=("JetBrains Mono", 8)).pack()

        self._met_total   = tk.StringVar(value="—")
        self._met_alerts  = tk.StringVar(value="—")
        self._met_servers = tk.StringVar(value="—")
        self._met_records = tk.StringVar(value="—")
        self._met_mode    = tk.StringVar(value="")

        metric(sb, self._met_total,   "TOTAL PROCESSES",   FG_YELLOW)
        tk.Frame(sb, bg="#45475a", width=1).pack(side="left", fill="y", pady=8)
        metric(sb, self._met_alerts,  f"🔴 ALERTS (≥{ALERT_THRESHOLD})", FG_RED)
        tk.Frame(sb, bg="#45475a", width=1).pack(side="left", fill="y", pady=8)
        metric(sb, self._met_servers, "SERVERS",           FG_TEAL)
        tk.Frame(sb, bg="#45475a", width=1).pack(side="left", fill="y", pady=8)
        metric(sb, self._met_records, "RECORDS",           FG_GREEN)

        # Mode indicator (shows ∑ SUM-BY-USER when active)
        tk.Label(sb, textvariable=self._met_mode, bg=BG_PANEL, fg=FG_TEAL,
                 font=("JetBrains Mono", 9, "bold")).pack(side="left", padx=14)

        self._met_time = tk.StringVar(value="")
        tk.Label(sb, textvariable=self._met_time, bg=BG_PANEL, fg=FG_BLUE,
                 font=("JetBrains Mono", 9)).pack(side="right", padx=14)

    # --- Main area (table | charts) -------------------------------------------
    def _build_main_area(self):
        main = tk.PanedWindow(self, orient="horizontal",
                              bg=BG_DARK, sashwidth=6,
                              sashrelief="flat", handlesize=0)
        main.pack(fill="both", expand=True, padx=6, pady=4)

        # ── Left: table ──────────────────────────────────────────────
        left = tk.Frame(main, bg=BG_DARK)
        main.add(left, minsize=540)

        # Filter bar
        fb = tk.Frame(left, bg=BG_DARK)
        fb.pack(fill="x", pady=(0, 3))
        tk.Label(fb, text="🔍 Filter:", bg=BG_DARK, fg=FG_BLUE,
                 font=("JetBrains Mono", 10)).pack(side="left", padx=4)
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", lambda *_: self._apply_filter())
        tk.Entry(fb, textvariable=self._filter_var,
                 bg="#313244", fg=FG_NORM, insertbackground=FG_NORM,
                 relief="flat", font=("JetBrains Mono", 10),
                 width=28).pack(side="left", padx=4)
        tk.Label(fb, text="Group:", bg=BG_DARK, fg=FG_BLUE,
                 font=("JetBrains Mono", 10)).pack(side="left", padx=(10, 2))
        self._grp_var = tk.StringVar(value="ALL")
        self._grp_combo = ttk.Combobox(fb, textvariable=self._grp_var,
                                        values=["ALL"], width=8, state="readonly")
        self._grp_combo.pack(side="left")
        self._grp_combo.bind("<<ComboboxSelected>>", lambda *_: self._apply_filter())

        # Treeview
        tree_frame = tk.Frame(left, bg=BG_DARK)
        tree_frame.pack(fill="both", expand=True)

        cols = ("count", "server", "username", "group")
        self._tree = ttk.Treeview(tree_frame, columns=cols,
                                   show="headings", style="CPU.Treeview",
                                   selectmode="browse")

        for cid, ctext, cw, anchor in [
            ("count",    "Count",    70,  "center"),
            ("server",   "Server",   140, "w"),
            ("username", "Username", 200, "w"),
            ("group",    "Group",    80,  "center"),
        ]:
            self._tree.heading(cid, text=ctext,
                               command=lambda c=cid: self._sort_by(c))
            self._tree.column(cid, width=cw, anchor=anchor, stretch=True)

        # Row colour tags
        self._tree.tag_configure("alert", background="#3d1a1a", foreground=FG_RED)
        self._tree.tag_configure("warn",  background="#3d2e10", foreground=FG_YELLOW)
        self._tree.tag_configure("odd",   background=BG_ROW_ODD, foreground=FG_NORM)
        self._tree.tag_configure("even",  background=BG_ROW_EVN, foreground=FG_NORM)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                             command=self._tree.yview, style="D.Vertical.TScrollbar")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal",
                             command=self._tree.xview, style="D.Horizontal.TScrollbar")
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Double-click row → open bjobs viewer
        self._tree.bind("<Double-1>", self._on_row_double_click)

        # ── Right: notebook (charts + bjobs) ─────────────────────────
        right = tk.Frame(main, bg=BG_DARK)
        main.add(right, minsize=480)

        nb = ttk.Notebook(right)
        nb.pack(fill="both", expand=True)

        # Tab 1 – Bar chart
        tab_bar = tk.Frame(nb, bg=BG_DARK)
        nb.add(tab_bar, text="📊 Bar Chart")
        self._fig_bar = Figure(figsize=(5.5, 4.5), facecolor=BG_DARK)
        self._ax_bar  = self._fig_bar.add_subplot(111)
        self._cv_bar  = FigureCanvasTkAgg(self._fig_bar, master=tab_bar)
        self._cv_bar.get_tk_widget().pack(fill="both", expand=True)

        # Tab 2 – Pie chart
        tab_pie = tk.Frame(nb, bg=BG_DARK)
        nb.add(tab_pie, text="🥧 Group Pie")
        self._fig_pie = Figure(figsize=(5.5, 4.5), facecolor=BG_DARK)
        self._ax_pie  = self._fig_pie.add_subplot(111)
        self._cv_pie  = FigureCanvasTkAgg(self._fig_pie, master=tab_pie)
        self._cv_pie.get_tk_widget().pack(fill="both", expand=True)

        # Tab 3 – History
        tab_hist = tk.Frame(nb, bg=BG_DARK)
        nb.add(tab_hist, text="📈 History")
        self._fig_hist = Figure(figsize=(5.5, 4.5), facecolor=BG_DARK)
        self._ax_hist  = self._fig_hist.add_subplot(111)
        self._cv_hist  = FigureCanvasTkAgg(self._fig_hist, master=tab_hist)
        self._cv_hist.get_tk_widget().pack(fill="both", expand=True)

        # Tab 4 – Heatmap
        tab_heat = tk.Frame(nb, bg=BG_DARK)
        nb.add(tab_heat, text="🌡 Heatmap")
        self._fig_heat = Figure(figsize=(5.5, 4.5), facecolor=BG_DARK)
        self._ax_heat  = self._fig_heat.add_subplot(111)
        self._cv_heat  = FigureCanvasTkAgg(self._fig_heat, master=tab_heat)
        self._cv_heat.get_tk_widget().pack(fill="both", expand=True)

        # Tab 5 – bjobs log viewer
        tab_jobs = tk.Frame(nb, bg=BG_DARK)
        nb.add(tab_jobs, text="📋 Job Logs")
        self._build_bjobs_tab(tab_jobs)

    # --- bjobs viewer tab ------------------------------------------------------
    def _build_bjobs_tab(self, parent):
        top = tk.Frame(parent, bg=BG_PANEL, height=40)
        top.pack(fill="x")
        top.pack_propagate(False)

        tk.Label(top, text="Username:", bg=BG_PANEL, fg=FG_BLUE,
                 font=("JetBrains Mono", 10)).pack(side="left", padx=8)
        self._bjobs_user = tk.StringVar()
        tk.Entry(top, textvariable=self._bjobs_user,
                 bg="#313244", fg=FG_NORM, insertbackground=FG_NORM,
                 relief="flat", font=("JetBrains Mono", 10),
                 width=20).pack(side="left", padx=4, pady=6)
        tk.Button(top, text="Run bjobs",
                  bg=ACCENT, fg=BG_DARK,
                  font=("JetBrains Mono", 10, "bold"),
                  relief="flat", padx=10, pady=4,
                  command=self._run_bjobs_tab).pack(side="left", padx=6)

        self._bjobs_out = scrolledtext.ScrolledText(
            parent, bg="#11111b", fg=FG_NORM,
            font=("JetBrains Mono", 10),
            insertbackground=FG_NORM, relief="flat", wrap="none"
        )
        self._bjobs_out.pack(fill="both", expand=True, padx=4, pady=4)
        # Configure highlight tags
        self._bjobs_out.tag_configure("header",    foreground=FG_BLUE,  font=("JetBrains Mono", 10, "bold"))
        self._bjobs_out.tag_configure("label",     foreground=FG_TEAL)
        self._bjobs_out.tag_configure("path",      foreground=FG_GREEN)
        self._bjobs_out.tag_configure("full-path", foreground=FG_YELLOW, font=("JetBrains Mono", 10, "bold"))
        self._bjobs_out.tag_configure("sep",       foreground="#45475a")
        self._bjobs_out.tag_configure("error",     foreground=FG_RED)

    # --- Log bar ---------------------------------------------------------------
    def _build_log_bar(self):
        lf = tk.Frame(self, bg=BG_PANEL, height=30)
        lf.pack(fill="x", side="bottom")
        lf.pack_propagate(False)
        self._log_var = tk.StringVar(value="Ready.")
        tk.Label(lf, textvariable=self._log_var,
                 bg=BG_PANEL, fg=FG_TEAL,
                 font=("JetBrains Mono", 9),
                 anchor="w").pack(fill="x", padx=8, pady=5)

    # ==========================================================================
    #  HELPERS
    # ==========================================================================

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_var.set(f"[{ts}]  {msg}")

    def _set_status(self, msg: str):
        self._status_var.set(msg)

    def _on_sum_toggle(self):
        """Called when the Sum-by-User checkbox is toggled."""
        mode = "∑ SUM-BY-USER  ON" if self.sum_by_user.get() else ""
        self._met_mode.set(mode)
        self._populate_table(self.data)
        self._update_charts(self.data)

    # ==========================================================================
    #  FILE BROWSE
    # ==========================================================================

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Select list.map.post",
            filetypes=[("All files", "*.*"), ("Post files", "*.post")],
        )
        if path:
            self.filepath.set(path)
            self._manual_refresh()

    # ==========================================================================
    #  AUTO REFRESH
    # ==========================================================================

    def _toggle_auto(self):
        if self.auto_refresh.get():
            self._schedule_refresh()
        else:
            if self._after_id:
                self.after_cancel(self._after_id)
                self._after_id = None

    def _schedule_refresh(self):
        if self._after_id:
            self.after_cancel(self._after_id)
        interval = max(1, self.refresh_secs.get()) * 1000
        self._after_id = self.after(interval, self._auto_cycle)

    def _auto_cycle(self):
        if self.auto_refresh.get():
            self._do_refresh()
            self._schedule_refresh()

    def _manual_refresh(self):
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        fp = self.filepath.get().strip()
        self._set_status("⏳ Loading…")
        data = parse_map_file(fp)

        if data and "error" in data[0]:
            self._log(f"Error: {data[0]['error']}")
            self._set_status("❌ Error")
            return

        self.data = data
        ts    = datetime.now().strftime("%H:%M:%S")
        total = sum(d["count"] for d in data)
        self._history.append((ts, total))
        if len(self._history) > 60:
            self._history = self._history[-60:]

        self.after(0, self._update_ui)

    # ==========================================================================
    #  UI UPDATE
    # ==========================================================================

    def _update_ui(self):
        self._populate_table(self.data)
        self._update_charts(self.data)

        # Compute stats for display mode
        display = aggregate_by_user(self.data) if self.sum_by_user.get() else self.data
        total   = sum(d["count"] for d in self.data)
        alerts  = sum(1 for d in display if d["count"] >= ALERT_THRESHOLD)
        servers = len({d["server"] for d in self.data})
        ts      = datetime.now().strftime("%H:%M:%S")

        self._met_total.set(str(total))
        self._met_alerts.set(str(alerts))
        self._met_servers.set(str(servers))
        self._met_records.set(str(len(self.data)))
        self._met_mode.set("∑ SUM-BY-USER  ON" if self.sum_by_user.get() else "")
        self._met_time.set(f"Updated: {ts}")
        self._set_status(f"✅ OK — {len(self.data)} records | Total: {total}")
        self._log(f"Refreshed: {len(self.data)} records, Total={total}, Alerts={alerts}")

        # Update group dropdown with current groups
        groups = sorted({"ALL"} | {d["group"] for d in self.data})
        self._grp_combo["values"] = groups

    # ==========================================================================
    #  TABLE POPULATION
    # ==========================================================================

    def _populate_table(self, data: list):
        """Fill the Treeview with current data, applying Sum-by-User if active."""
        # Determine rows to display
        rows = aggregate_by_user(data) if self.sum_by_user.get() else list(data)

        # Apply text filter
        ft  = self._filter_var.get().strip().lower()
        grp = self._grp_var.get()
        if ft:
            rows = [r for r in rows
                    if ft in r["server"].lower()
                    or ft in r["username"].lower()
                    or ft in r["group"].lower()]
        if grp and grp != "ALL":
            rows = [r for r in rows if r["group"] == grp]

        # Preserve current selection
        sel = self._tree.selection()
        sel_vals = list(self._tree.item(sel[0])["values"]) if sel else None

        for item in self._tree.get_children():
            self._tree.delete(item)

        for i, row in enumerate(rows):
            cnt = row["count"]
            tag = ("alert" if cnt >= ALERT_THRESHOLD else
                   "warn"  if cnt == ALERT_THRESHOLD - 1 else
                   ("odd"  if i % 2 else "even"))

            prefix = "🔴 " if cnt >= ALERT_THRESHOLD else ""
            iid = self._tree.insert(
                "", "end",
                values=(f"{prefix}{cnt}", row["server"],
                        row["username"], row["group"]),
                tags=(tag,)
            )
            if sel_vals and sel_vals == list(self._tree.item(iid)["values"]):
                self._tree.selection_set(iid)
                self._tree.see(iid)

    def _apply_filter(self):
        self._populate_table(self.data)

    def _sort_by(self, col: str):
        if self.sort_col == col:
            self.sort_rev = not self.sort_rev
        else:
            self.sort_col = col
            self.sort_rev = False
        self.data.sort(key=lambda x: x.get(col, ""), reverse=self.sort_rev)
        self._populate_table(self.data)

    # ==========================================================================
    #  BJOBS (double-click on row)
    # ==========================================================================

    def _on_row_double_click(self, event):
        """Open a simple dialog showing bjobs output for the clicked username."""
        sel = self._tree.selection()
        if not sel:
            return
        values   = self._tree.item(sel[0])["values"]
        username = str(values[2]) if len(values) > 2 else ""
        if not username:
            return
        self._bjobs_user.set(username)
        self._run_bjobs_tab()

    def _run_bjobs_tab(self):
        """Run bjobs for the username in the input and show results in the log tab."""
        username = self._bjobs_user.get().strip()
        if not username:
            messagebox.showwarning("Input required", "Please enter a username.")
            return

        out = self._bjobs_out
        out.configure(state="normal")
        out.delete("1.0", "end")

        # Command header
        cmd_str = f'bjobs -u {username} -o "SUB_CWD JOB_NAME" -noheader'
        out.insert("end", f"$ {cmd_str}\n", "header")
        out.insert("end", "─" * 70 + "\n", "sep")

        def fetch():
            result = run_bjobs(username)
            self.after(0, lambda: _display(result))

        def _display(result):
            if result["error"]:
                out.insert("end", f"ERROR: {result['error']}\n", "error")
                out.configure(state="disabled")
                return
            jobs = result["jobs"]
            if not jobs:
                out.insert("end", "No active jobs found.\n")
                out.configure(state="disabled")
                return

            for i, job in enumerate(jobs, 1):
                out.insert("end", f"\n  Job #{i}\n", "header")
                out.insert("end", "  SUB_CWD  : ", "label")
                out.insert("end", job["sub_cwd"] + "\n", "path")
                out.insert("end", "  JOB_NAME : ", "label")
                out.insert("end", job["job_name"] + "\n", "path")
                out.insert("end", "  ⭐ FULL   : ", "label")
                out.insert("end", job["full_path"] + "\n", "full-path")
            out.insert("end", "\n" + "─" * 70 + "\n", "sep")
            out.configure(state="disabled")
            self._log(f"bjobs for {username}: {len(jobs)} jobs found")

        threading.Thread(target=fetch, daemon=True).start()

    # ==========================================================================
    #  CHARTS
    # ==========================================================================

    def _chart_style(self, ax, title: str):
        """Apply shared dark style to a matplotlib Axes."""
        ax.set_facecolor(BG_PANEL)
        ax.tick_params(colors=FG_NORM, labelsize=8)
        ax.set_title(title, color=FG_BLUE, fontsize=10, fontweight="bold")
        for spine in ax.spines.values():
            spine.set_edgecolor("#45475a")
        ax.xaxis.label.set_color(FG_NORM)
        ax.yaxis.label.set_color(FG_NORM)

    def _update_charts(self, data: list):
        """Redraw all chart tabs with current data."""
        if not data:
            return
        # Use aggregated data for charts when Sum-by-User is on
        chart_data = aggregate_by_user(data) if self.sum_by_user.get() else data
        self._draw_bar(chart_data)
        self._draw_pie(chart_data)
        self._draw_history()
        self._draw_heatmap(chart_data)

    def _draw_bar(self, data: list):
        ax = self._ax_bar
        ax.clear()
        self._fig_bar.patch.set_facecolor(BG_DARK)

        srv_counts: dict[str, int] = {}
        for d in data:
            for srv in d["server"].split(", "):
                srv_counts[srv] = srv_counts.get(srv, 0) + d["count"]

        top = sorted(srv_counts.items(), key=lambda x: x[1], reverse=True)[:25]
        if not top:
            return

        labels, values = zip(*top)
        colors = [FG_RED    if v >= ALERT_THRESHOLD * 2 else
                  FG_YELLOW if v >= ALERT_THRESHOLD else
                  FG_GREEN
                  for v in values]

        bars = ax.barh(range(len(labels)), values, color=colors,
                       edgecolor="#45475a", linewidth=0.5, height=0.65)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=8, color=FG_NORM, fontfamily="monospace")
        ax.invert_yaxis()
        ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))

        for bar, val in zip(bars, values):
            ax.text(val + 0.05, bar.get_y() + bar.get_height() / 2,
                    str(val), va="center", ha="left", color=FG_NORM, fontsize=8)

        ax.axvline(x=ALERT_THRESHOLD, color=FG_RED, linestyle="--",
                   linewidth=1, alpha=0.7, label=f"Alert ≥{ALERT_THRESHOLD}")
        ax.legend(fontsize=8, facecolor=BG_PANEL, edgecolor="#45475a", labelcolor=FG_NORM)
        self._chart_style(ax, "Top Servers by Process Count")
        ax.set_xlabel("Count", fontsize=9)
        self._fig_bar.tight_layout(pad=1.5)
        self._cv_bar.draw()

    def _draw_pie(self, data: list):
        ax = self._ax_pie
        ax.clear()
        self._fig_pie.patch.set_facecolor(BG_DARK)

        grp_counts: dict[str, int] = {}
        for d in data:
            grp_counts[d["group"]] = grp_counts.get(d["group"], 0) + d["count"]

        if not grp_counts:
            return

        palette = [FG_BLUE, FG_GREEN, FG_MAUVE, FG_YELLOW, FG_TEAL, FG_RED, "#fab387"]
        labels  = list(grp_counts.keys())
        sizes   = list(grp_counts.values())
        colors  = [palette[i % len(palette)] for i in range(len(labels))]

        wedges, texts, autotexts = ax.pie(
            sizes, labels=labels, autopct="%1.1f%%", colors=colors,
            startangle=140, pctdistance=0.75,
            wedgeprops={"edgecolor": BG_DARK, "linewidth": 2},
            textprops={"color": FG_NORM, "fontsize": 9}
        )
        for at in autotexts:
            at.set_color(BG_DARK); at.set_fontweight("bold"); at.set_fontsize(8)

        self._chart_style(ax, "Process Distribution by Group")
        ax.set_facecolor(BG_DARK)
        self._fig_pie.tight_layout(pad=1.5)
        self._cv_pie.draw()

    def _draw_history(self):
        ax = self._ax_hist
        ax.clear()
        self._fig_hist.patch.set_facecolor(BG_DARK)

        if len(self._history) < 2:
            ax.text(0.5, 0.5, "Collecting data…\nWaiting for more refresh cycles",
                    transform=ax.transAxes, ha="center", va="center",
                    color=FG_NORM, fontsize=10)
            self._chart_style(ax, "Total Process Count Over Time")
            self._fig_hist.tight_layout(pad=1.5)
            self._cv_hist.draw()
            return

        times  = [h[0] for h in self._history]
        totals = [h[1] for h in self._history]

        ax.plot(range(len(times)), totals, color=FG_BLUE, linewidth=2,
                marker="o", markersize=4, markerfacecolor=FG_MAUVE,
                markeredgecolor=BG_DARK)
        ax.fill_between(range(len(times)), totals, alpha=0.15, color=FG_BLUE)

        step = max(1, len(times) // 8)
        ax.set_xticks(range(0, len(times), step))
        ax.set_xticklabels([times[i] for i in range(0, len(times), step)],
                           rotation=30, ha="right", fontsize=7)
        ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        self._chart_style(ax, "Total Process Count Over Time")
        ax.set_ylabel("Total", fontsize=9)
        self._fig_hist.tight_layout(pad=1.5)
        self._cv_hist.draw()

    def _draw_heatmap(self, data: list):
        import numpy as np
        ax = self._ax_heat
        ax.clear()
        self._fig_heat.patch.set_facecolor(BG_DARK)

        if not data:
            return

        all_servers = sorted({
            srv for d in data for srv in d["server"].split(", ")
        })
        groups = sorted({d["group"] for d in data})

        matrix = np.zeros((len(all_servers), len(groups)))
        for d in data:
            for srv in d["server"].split(", "):
                if srv in all_servers:
                    si = all_servers.index(srv)
                    gi = groups.index(d["group"])
                    matrix[si][gi] += d["count"]

        row_sums = matrix.sum(axis=1)
        top_idx  = row_sums.argsort()[::-1][:30]
        matrix   = matrix[top_idx]
        srv_lbls = [all_servers[i] for i in top_idx]

        im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn_r",
                       interpolation="nearest",
                       vmin=0, vmax=max(ALERT_THRESHOLD, matrix.max() or 1))

        ax.set_xticks(range(len(groups)))
        ax.set_xticklabels(groups, fontsize=9, color=FG_NORM)
        ax.set_yticks(range(len(srv_lbls)))
        ax.set_yticklabels(srv_lbls, fontsize=7, color=FG_NORM, fontfamily="monospace")

        cbar = self._fig_heat.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
        cbar.ax.tick_params(colors=FG_NORM, labelsize=7)

        for i in range(len(srv_lbls)):
            for j in range(len(groups)):
                v = int(matrix[i, j])
                if v > 0:
                    ax.text(j, i, str(v), ha="center", va="center",
                            color="white" if v >= ALERT_THRESHOLD else FG_NORM,
                            fontsize=7,
                            fontweight="bold" if v >= ALERT_THRESHOLD else "normal")

        self._chart_style(ax, "Heatmap: Server × Group Count")
        self._fig_heat.tight_layout(pad=1.5)
        self._cv_heat.draw()


# ==============================================================================
#  ENTRY POINT
# ==============================================================================

def main():
    # Use sample data if the production file does not exist
    sample_path = "/tmp/list.map.post"
    if not os.path.exists(sample_path):
        try:
            import generate_sample_data as gsd
            gsd.generate_data(sample_path)
        except Exception:
            pass

    app = CpuCheckApp()

    real_path = app.filepath.get()
    if not os.path.exists(real_path):
        if os.path.exists(sample_path):
            app.filepath.set(sample_path)
            app._log(f"Production file not found. Using sample: {sample_path}")
        else:
            app._log("No data file found – use Browse to select one.")

    app.after(300, app._manual_refresh)
    app.mainloop()


if __name__ == "__main__":
    main()
