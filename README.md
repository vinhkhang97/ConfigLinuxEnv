# ⚡ LICENSE CHECK Monitor

**Version:** 0.3 | **Author:** RickTran (Tran Dang Vinh Khang)

A Python-based real-time monitoring dashboard for EDA license/process usage.
Converts the original CSH shell pipeline into a full GUI application with charts,
user-aggregation, and a bjobs log viewer.

---

## Features

| Feature | Description |
|---|---|
| 📊 **Real-time refresh** | Auto-refresh every 5/10/30/60 seconds with countdown timer |
| 📋 **Sortable table** | Columns: Count, Server, Username, Group — click headers to sort |
| 🔴 **Alert highlight** | Rows with Count ≥ 4 pulse red; count=3 shown in yellow |
| **∑ Sum by User** | Checkbox (default ON): collapses rows by username and sums counts |
| 🔍 **Filter** | Text filter + Group dropdown (PID1, PID3, EO, AC, ALL) |
| 📊 **Bar Chart** | Top servers by total process count |
| 🥧 **Pie Chart** | Group distribution (PID1 / PID3 / EO / AC) |
| 📈 **History** | Rolling timeline of total count over last 60 refresh cycles |
| 🌡 **Heatmap** | Server × Group matrix — colour-coded intensity |
| 📋 **bjobs Log Viewer** | Click any username → runs `bjobs -u <user>` and shows full log paths |
| 🗂 **Full path assembly** | SUB_CWD + JOB_NAME auto-joined; `/pr/` boundary handled automatically |
| 👤 **Version info** | App version + author shown in title bar and top toolbar |

---

## File Format

The input file (`list.map.post` or `list.map`) contains one license record per line:

```
gsme001 GSME-TW-12 localhost: 12.0 (v25.100) (gsme-tw-cmp01/5280 18405), start Mon 4/13 17:42 -- chanh.tran PID1
gsme005 GSME-TW-21 localhost: 10.0 (v25.100) (gsme-tw-cmp01/5280 17107), start Tue 4/14 11:45 -- nguyenkhang.tran PID1
gsme023 GSME-TW-03 localhost: 10.0 (v25.100) (gsme-tw-cmp01/5280 5001), start Tue 4/14 14:00 -- dat.do PID3
```

**Parser extracts:**
- `$1` → license_id (e.g. `gsme001`)
- `$2` → server name (e.g. `GSME-TW-12`)
- token after `--`, second-to-last → username (`chanh.tran`)
- token after `--`, last → group (`PID1`, `PID3`, `EO`, `AC`)

---

## Quick Start

### Web Interface (Recommended)

```bash
# Install dependencies
pip install flask matplotlib numpy

# Start server
python3 web_monitor.py

# Open in browser
http://localhost:7860
```

### Tkinter GUI (Linux Desktop with X11)

```bash
pip install matplotlib numpy
python3 cpu_check_monitor.py
```

---

## Configuration

Edit the top of `web_monitor.py`:

```python
DATA_FILE        = "/project/VAST_PI/WORKPLACE/CPU_CHECK/list.map.post"
REFRESH_INTERVAL = 5       # background cache refresh in seconds
ALERT_THRESHOLD  = 4       # count >= this → red alert
```

---

## Sum by User Mode

When **∑ Sum by User** is checked (default ON):

- All rows with the same `username` are merged into one row
- Their `count` values are **summed**
- If the summed count ≥ `ALERT_THRESHOLD` (4) → **red alert**
- The `server` column shows all servers used by that user (comma-separated)

Example — raw data:
```
count=1  dat.do  GSME-TW-03  PID3
count=1  dat.do  GSME-TW-04  PID3
count=1  dat.do  GSME-TW-06  PID3
count=1  dat.do  GSME-TW-07  PID3
```
After Sum by User → `count=4  dat.do  GSME-TW-03, GSME-TW-04, GSME-TW-06, GSME-TW-07  PID3  🔴`

---

## bjobs Log Viewer

Click the **📋 jobs** button next to any username (or double-click a row in the Tkinter app).

The tool runs:
```bash
bjobs -u <username> -o "SUB_CWD JOB_NAME" -noheader
```

**Path assembly rule:**
```
SUB_CWD  = /project/user/run01/pr
JOB_NAME = sim_output/result.log
FULL PATH = /project/user/run01/pr/sim_output/result.log
```

> When `bjobs` is not installed (no LSF), demo data is shown automatically.

---

## API Endpoints (Web Mode)

| Endpoint | Description |
|---|---|
| `GET /` | Main dashboard UI |
| `GET /api/data?file=<path>` | JSON: parsed records + summary stats |
| `GET /api/chart/<type>?sum=1` | PNG chart (bar / pie / hist / heat) |
| `GET /api/bjobs?user=<name>` | JSON: bjobs jobs + assembled log paths |
| `GET /api/health` | Health check with version info |

---

## Requirements

```
python >= 3.10
flask
matplotlib
numpy
tkinter  (built-in, for GUI mode)
```

---

## History

| Version | Changes |
|---|---|
| v0.1 | Collect data from existing file |
| v0.2 | Real-time refresh, dark theme, charts |
| v0.3 | Sum-by-User mode, bjobs log viewer, version info, English comments, full-path assembly |
