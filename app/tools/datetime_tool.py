"""
datetime_tool.py

Tool datetime untuk RIN (PHASE 6C).

Selalu membaca waktu sistem SAAT dipanggil (tidak pernah hardcode
tanggal/jam). Memberikan hari, tanggal, dan jam menurut waktu lokal
server tempat RIN berjalan.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from app.tools.registry import Tool, ToolPermission

_HARI_INDONESIA = {
    0: "Senin",
    1: "Selasa",
    2: "Rabu",
    3: "Kamis",
    4: "Jumat",
    5: "Sabtu",
    6: "Minggu",
}


def get_current_datetime_info() -> str:
    """Mengembalikan ringkasan hari/tanggal/jam saat ini (waktu lokal server)."""
    now = datetime.now()
    hari = _HARI_INDONESIA[now.weekday()]
    return (
        f"Sekarang hari {hari}, tanggal {now.strftime('%d-%m-%Y')}, "
        f"pukul {now.strftime('%H:%M:%S')} (waktu lokal server)."
    )


def _handle(arguments: Dict[str, Any]) -> str:
    return get_current_datetime_info()


def datetime_tool() -> Tool:
    return Tool(
        name="datetime",
        description=(
            "Memberikan tanggal, hari, dan jam saat ini menurut waktu lokal "
            "server tempat RIN berjalan."
        ),
        input_schema={
            "type": "object",
            "properties": {},
        },
        permission=ToolPermission.SAFE,
        handler=_handle,
        status_message="⚙️ RIN mengecek waktu...",
    )
