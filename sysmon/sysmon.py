#!/usr/bin/env python3
"""sysmon — lightweight system resource monitor with ntfy.sh alerts."""

import os
import time
import logging
from collections import defaultdict

import psutil
import requests

# ── Config ───────────────────────────────────────────────────────────────────
NTFY_TOPIC      = os.environ.get("SYSMON_NTFY_TOPIC",   "sysmon-doug-a7x93k")
POLL_INTERVAL   = int(os.environ.get("SYSMON_INTERVAL",  "60"))   # seconds between polls
ALERT_COOLDOWN  = int(os.environ.get("SYSMON_COOLDOWN",  "1800")) # seconds before re-alerting same metric
SUSTAINED_COUNT = int(os.environ.get("SYSMON_SUSTAINED", "2"))    # consecutive high readings before alert

THRESHOLDS = {
    "cpu":    float(os.environ.get("SYSMON_CPU_PCT",   "80")),   # %
    "memory": float(os.environ.get("SYSMON_MEM_PCT",   "75")),   # %
    "swap":   float(os.environ.get("SYSMON_SWAP_PCT",  "50")),   # %
    "disk":   float(os.environ.get("SYSMON_DISK_PCT",  "85")),   # %
    "load":   float(os.environ.get("SYSMON_LOAD_MULT", "1.0")),  # × cpu count
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("sysmon")

# ── State ────────────────────────────────────────────────────────────────────
_consecutive: dict[str, int]   = defaultdict(int)
_last_alert:  dict[str, float] = defaultdict(float)

# ── Alert delivery ────────────────────────────────────────────────────────────
def send_alert(metric: str, title: str, body: str, priority: str = "high") -> None:
    now = time.time()
    if now - _last_alert[metric] < ALERT_COOLDOWN:
        log.info("Alert suppressed (cooldown): %s", metric)
        return
    _last_alert[metric] = now
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=body.encode(),
            headers={
                "Title": title,
                "Priority": priority,
                "Tags": "warning,computer",
            },
            timeout=8,
        )
        log.info("Alert sent: %s", title)
    except Exception as exc:
        log.warning("Failed to send alert: %s", exc)

# ── Process helpers ───────────────────────────────────────────────────────────
def top_by_cpu(n: int = 5) -> str:
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
        try:
            val = p.info["cpu_percent"]
            if val is None:
                continue
            procs.append((val, p.info["pid"], p.info["name"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(reverse=True)
    return "\n".join(
        f"  {name} (pid {pid}): {val:.1f}%"
        for val, pid, name in procs[:n]
    )

def top_by_mem(n: int = 5) -> str:
    procs = []
    for p in psutil.process_iter(["pid", "name", "memory_percent", "memory_info"]):
        try:
            pct = p.info["memory_percent"]
            mb  = p.info["memory_info"].rss / 1024 / 1024
            procs.append((pct, p.info["pid"], p.info["name"], mb))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(reverse=True)
    return "\n".join(
        f"  {name} (pid {pid}): {pct:.1f}% ({mb:.0f} MB)"
        for pct, pid, name, mb in procs[:n]
    )

# ── Checks ────────────────────────────────────────────────────────────────────
def check_cpu() -> None:
    pct = psutil.cpu_percent(interval=None)
    thr = THRESHOLDS["cpu"]
    if pct >= thr:
        _consecutive["cpu"] += 1
        if _consecutive["cpu"] >= SUSTAINED_COUNT:
            top = top_by_cpu()
            body = (
                f"CPU at {pct:.1f}% (threshold {thr:.0f}%)\n\n"
                f"Top processes:\n{top}"
            )
            send_alert("cpu", f"High CPU: {pct:.1f}%", body)
    else:
        _consecutive["cpu"] = 0


def check_memory() -> None:
    vm  = psutil.virtual_memory()
    pct = vm.percent
    thr = THRESHOLDS["memory"]
    if pct >= thr:
        _consecutive["memory"] += 1
        if _consecutive["memory"] >= SUSTAINED_COUNT:
            used_gb  = vm.used  / 1024 ** 3
            total_gb = vm.total / 1024 ** 3
            avail_gb = vm.available / 1024 ** 3
            top = top_by_mem()
            body = (
                f"Memory at {pct:.1f}% (threshold {thr:.0f}%)\n"
                f"Used: {used_gb:.2f} GB / {total_gb:.2f} GB  "
                f"({avail_gb:.2f} GB available)\n\n"
                f"Top processes:\n{top}"
            )
            send_alert("memory", f"High Memory: {pct:.1f}%", body)
    else:
        _consecutive["memory"] = 0


def check_swap() -> None:
    sw = psutil.swap_memory()
    if sw.total == 0:
        return
    pct = sw.percent
    thr = THRESHOLDS["swap"]
    if pct >= thr:
        _consecutive["swap"] += 1
        if _consecutive["swap"] >= SUSTAINED_COUNT:
            used_mb  = sw.used  / 1024 ** 2
            total_mb = sw.total / 1024 ** 2
            body = (
                f"Swap at {pct:.1f}% (threshold {thr:.0f}%)\n"
                f"Used: {used_mb:.0f} MB / {total_mb:.0f} MB\n"
                f"High swap means physical RAM is exhausted."
            )
            send_alert("swap", f"High Swap: {pct:.1f}%", body, priority="urgent")
    else:
        _consecutive["swap"] = 0


def check_disk() -> None:
    usage = psutil.disk_usage("/")
    pct   = usage.percent
    thr   = THRESHOLDS["disk"]
    if pct >= thr:
        _consecutive["disk"] += 1
        if _consecutive["disk"] >= SUSTAINED_COUNT:
            free_gb  = usage.free  / 1024 ** 3
            total_gb = usage.total / 1024 ** 3
            body = (
                f"Disk at {pct:.1f}% (threshold {thr:.0f}%)\n"
                f"Free: {free_gb:.1f} GB of {total_gb:.1f} GB"
            )
            send_alert("disk", f"High Disk: {pct:.1f}%", body, priority="urgent")
    else:
        _consecutive["disk"] = 0


def check_load() -> None:
    cores = psutil.cpu_count() or 1
    load1, load5, load15 = os.getloadavg()
    thr = THRESHOLDS["load"] * cores
    if load5 >= thr:
        _consecutive["load"] += 1
        if _consecutive["load"] >= SUSTAINED_COUNT:
            top = top_by_cpu()
            body = (
                f"Load average: {load1:.2f} / {load5:.2f} / {load15:.2f} "
                f"(1m / 5m / 15m)\n"
                f"Threshold: {thr:.1f} ({THRESHOLDS['load']}× {cores} cores)\n\n"
                f"Top CPU processes:\n{top}"
            )
            send_alert("load", f"High Load: {load5:.2f}", body)
    else:
        _consecutive["load"] = 0


# ── Main loop ─────────────────────────────────────────────────────────────────
def main() -> None:
    log.info(
        "sysmon starting — topic=%s interval=%ds thresholds=%s",
        NTFY_TOPIC, POLL_INTERVAL, THRESHOLDS,
    )
    # Prime cpu_percent so the first reading is meaningful
    psutil.cpu_percent(interval=1)
    for p in psutil.process_iter(["cpu_percent"]):
        try:
            p.cpu_percent()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    time.sleep(POLL_INTERVAL - 1)

    while True:
        try:
            check_memory()
            check_cpu()
            check_swap()
            check_disk()
            check_load()
        except Exception:
            log.exception("Unexpected error in poll loop")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
