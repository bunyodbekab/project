#!/usr/bin/env python3
"""Qt display diagnostics.

This script tests common Qt platform plugins one-by-one and reports:
- which method can open a real screen
- likely missing dependencies when it fails

Usage:
  python3 test_display.py
  python3 test_display.py --launch-main
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

METHODS = ["auto", "xcb", "wayland", "eglfs", "linuxfb", "minimal", "offscreen"]
PROBE_TIMEOUT_SEC = 12


def _parse_keyvals(text: str) -> dict[str, str]:
	out: dict[str, str] = {}
	for line in text.splitlines():
		line = line.strip()
		if "=" not in line:
			continue
		k, v = line.split("=", 1)
		out[k.strip()] = v.strip()
	return out


def _collect_hints(all_text: str) -> list[str]:
	t = all_text.lower()
	hints: list[str] = []

	if "xcb-cursor0" in t or "libxcb-cursor0" in t:
		hints.append(
			"sudo apt install -y libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 "
			"libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-xinerama0 "
			"libxcb-xkb1 libx11-xcb1 libxrender1 libxi6 libxrandr2 libdbus-1-3"
		)

	if "could not connect to display" in t:
		hints.append("DISPLAY/XAUTHORITY noto'g'ri bo'lishi mumkin. Grafik sessiyadan ishga tushiring.")

	if 'could not find the qt platform plugin "eglfs"' in t:
		hints.append("Sizdagi PyQt6 build ichida eglfs plugin yo'q. xcb yoki wayland ishlating.")

	if "platformname=offscreen" in t and "has_screen=0" in t:
		hints.append("Qt offscreen rejimga tushgan. QT_QPA_PLATFORM ni xcb yoki wayland qilib ko'ring.")

	if "qapplication.primaryscreen().geometry" in t or "'nonetype' object has no attribute 'geometry'" in t:
		hints.append("Ekran aniqlanmadi (primaryScreen=None). Avval display backend ni to'g'rilang.")

	dedup: list[str] = []
	for h in hints:
		if h not in dedup:
			dedup.append(h)
	return dedup


def _run_probe(method: str) -> dict[str, str]:
	env = os.environ.copy()
	if method == "auto":
		env.pop("QT_QPA_PLATFORM", None)
	else:
		env["QT_QPA_PLATFORM"] = method

	cmd = [sys.executable, str(Path(__file__).resolve()), "--probe-child"]
	try:
		completed = subprocess.run(
			cmd,
			env=env,
			capture_output=True,
			text=True,
			timeout=PROBE_TIMEOUT_SEC,
		)
	except subprocess.TimeoutExpired:
		return {
			"method": method,
			"ok": "0",
			"rc": "124",
			"platform": "?",
			"screen": "-",
			"raw": "TIMEOUT",
		}

	raw = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
	kv = _parse_keyvals(raw)
	has_screen = kv.get("HAS_SCREEN", "0") == "1"
	qt_platform = kv.get("PLATFORM", "?")
	screen = kv.get("SCREEN", "-")
	ok = completed.returncode == 0 and has_screen

	return {
		"method": method,
		"ok": "1" if ok else "0",
		"rc": str(completed.returncode),
		"platform": qt_platform,
		"screen": screen,
		"raw": raw.strip(),
	}


def _probe_child() -> int:
	try:
		from PyQt6.QtCore import QTimer
		from PyQt6.QtWidgets import QApplication

		app = QApplication(sys.argv)
		platform = app.platformName()
		screen = app.primaryScreen()

		print(f"PLATFORM={platform}")
		print(f"HAS_SCREEN={1 if screen else 0}")

		if screen is not None:
			g = screen.geometry()
			print(f"SCREEN={g.width()}x{g.height()}")

		QTimer.singleShot(1, app.quit)
		app.exec()
		return 0 if screen is not None else 3
	except Exception as exc:
		print(f"EXCEPTION={type(exc).__name__}: {exc}")
		return 2


def _launch_main_with(method: str) -> int:
	main_path = Path(__file__).resolve().with_name("main.py")
	if not main_path.exists():
		print("main.py topilmadi, launch qilinmadi.")
		return 2

	env = os.environ.copy()
	if method == "auto":
		env.pop("QT_QPA_PLATFORM", None)
	else:
		env["QT_QPA_PLATFORM"] = method

	print(f"Launching main.py with method={method}")
	result = subprocess.run([sys.executable, str(main_path)], env=env)
	return int(result.returncode)


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--probe-child", action="store_true", help="Internal child probe mode")
	parser.add_argument("--launch-main", action="store_true", help="Launch main.py using the best method")
	args = parser.parse_args()

	if args.probe_child:
		return _probe_child()

	print("Qt display diagnostics started")
	print(f"DISPLAY={os.environ.get('DISPLAY', '')}")
	print(f"XDG_SESSION_TYPE={os.environ.get('XDG_SESSION_TYPE', '')}")
	print(f"QT_QPA_PLATFORM(current)={os.environ.get('QT_QPA_PLATFORM', '')}")
	print()

	results: list[dict[str, str]] = []
	for method in METHODS:
		res = _run_probe(method)
		results.append(res)
		status = "OK" if res["ok"] == "1" else "FAIL"
		print(
			f"[{status:4}] method={res['method']:<9} rc={res['rc']:<3} "
			f"qt={res['platform']:<10} screen={res['screen']}"
		)

	print()
	best = next((r for r in results if r["ok"] == "1"), None)
	all_raw = "\n".join(r["raw"] for r in results if r.get("raw"))
	hints = _collect_hints(all_raw)

	if best is not None:
		print(f"RESULT=DISPLAY_OK method={best['method']} qt={best['platform']} screen={best['screen']}")
		if best["method"] == "auto":
			print("RUN=python3 main.py")
		else:
			print(f"RUN=QT_QPA_PLATFORM={best['method']} python3 main.py")

		if args.launch_main:
			return _launch_main_with(best["method"])
		return 0

	print("RESULT=DISPLAY_FAIL")
	if hints:
		print("SUGGESTIONS:")
		for hint in hints:
			print(f"- {hint}")
	else:
		print("- Grafik sessiya ichida (desktop terminal) qayta sinab ko'ring.")
	return 1


if __name__ == "__main__":
	raise SystemExit(main())
