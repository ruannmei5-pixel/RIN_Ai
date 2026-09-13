"""
system.py

Tool system_info untuk RIN (PHASE 6D).

READ-ONLY: modul ini HANYA membaca informasi sistem (OS, versi Python,
CPU, RAM, disk, hostname). Tidak pernah mengubah apa pun di sistem, dan
tidak pernah menjalankan subprocess/command apa pun (ATURAN UTAMA #9,
#11, #12) — semua informasi diambil lewat library Python standar
(`platform`, `shutil`, `socket`, `sys`) dan `psutil` jika terpasang.
"""

from __future__ import annotations

import platform
import shutil
import socket
import sys
from typing import Any, Dict

from app.tools.registry import Tool, ToolPermission

try:
    import psutil  # opsional: dipakai untuk detail CPU/RAM jika tersedia
except ImportError:  # pragma: no cover - lingkungan tanpa psutil tetap jalan
    psutil = None  # type: ignore[assignment]


def get_system_summary() -> str:
    """Mengembalikan ringkasan informasi sistem (read-only)."""
    lines = []

    lines.append(f"OS: {platform.system()} {platform.release()}")
    lines.append(f"Python: {sys.version.split()[0]}")

    try:
        lines.append(f"Hostname: {socket.gethostname()}")
    except OSError:
        pass

    if psutil is not None:
        try:
            lines.append(f"CPU usage: {psutil.cpu_percent(interval=0.3)}%")
        except Exception:  # pragma: no cover - jaring pengaman
            pass
        try:
            mem = psutil.virtual_memory()
            lines.append(
                "RAM: {used:.1f} GB terpakai dari {total:.1f} GB ({percent}%)".format(
                    used=mem.used / (1024 ** 3),
                    total=mem.total / (1024 ** 3),
                    percent=mem.percent,
                )
            )
        except Exception:  # pragma: no cover - jaring pengaman
            pass
    else:
        lines.append("CPU/RAM: detail tidak tersedia (psutil belum terpasang).")

    try:
        usage = shutil.disk_usage("/")
        lines.append(
            "Disk: {used:.1f} GB terpakai dari {total:.1f} GB".format(
                used=usage.used / (1024 ** 3),
                total=usage.total / (1024 ** 3),
            )
        )
    except OSError:  # pragma: no cover - jaring pengaman
        pass

    return "\n".join(lines)


def _handle(arguments: Dict[str, Any]) -> str:
    return get_system_summary()


def system_info_tool() -> Tool:
    return Tool(
        name="system_info",
        description=(
            "Mengambil informasi dasar sistem tempat RIN berjalan: OS, versi "
            "Python, hostname, penggunaan CPU/RAM, dan disk. Read-only, tidak "
            "pernah mengubah sistem atau menjalankan command apa pun."
        ),
        input_schema={
            "type": "object",
            "properties": {},
        },
        permission=ToolPermission.READ_ONLY,
        handler=_handle,
        status_message="⚙️ RIN mengecek informasi sistem...",
    )
