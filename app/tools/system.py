"""
system.py

Tool system_info untuk RIN (PHASE 6D, diperluas pada PHASE 7).

READ-ONLY: modul ini HANYA membaca informasi sistem (OS, versi Python,
CPU, RAM, disk, hostname, jaringan dasar). Tidak pernah mengubah apa pun
di sistem, dan tidak pernah menjalankan subprocess/command apa pun
(ATURAN UTAMA #9, #11, #12) — semua informasi diambil lewat library
Python standar (`platform`, `shutil`, `socket`, `sys`) dan `psutil` jika
terpasang.

PHASE 7 menambahkan detail hardware (jumlah core CPU, model processor)
dan informasi jaringan dasar (hostname, alamat IP lokal, interface
jaringan), serta `get_system_info_dict()` yang mengembalikan data yang
sama dalam bentuk terstruktur (dict) untuk dipakai oleh endpoint REST
`GET /api/system/info` dan Web UI — tanpa mengubah perilaku tool lama
yang dipakai lewat chat (`get_system_summary()` / `system_info_tool()`).
"""

from __future__ import annotations

import platform
import shutil
import socket
import sys
from typing import Any, Dict, List

from app.tools.registry import Tool, ToolPermission

try:
    import psutil  # opsional: dipakai untuk detail CPU/RAM/network jika tersedia
except ImportError:  # pragma: no cover - lingkungan tanpa psutil tetap jalan
    psutil = None  # type: ignore[assignment]


def _network_interfaces() -> List[Dict[str, str]]:
    """
    Mengambil daftar interface jaringan lokal (nama + alamat IPv4),
    tanpa loopback. Read-only, tidak pernah gagal keras: jika psutil
    tidak tersedia atau terjadi error, mengembalikan list kosong.
    """
    interfaces: List[Dict[str, str]] = []

    if psutil is None:
        return interfaces

    try:
        for name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                # socket.AF_INET == IPv4. Dicek lewat family.name supaya
                # tidak perlu import socket khusus untuk konstanta ini.
                if getattr(addr.family, "name", "") != "AF_INET":
                    continue
                if addr.address.startswith("127."):
                    continue
                interfaces.append({"name": name, "address": addr.address})
    except Exception:  # pragma: no cover - jaring pengaman
        return interfaces

    return interfaces


def get_system_info_dict() -> Dict[str, Any]:
    """
    Mengembalikan informasi sistem sebagai dict terstruktur (read-only),
    untuk dipakai oleh REST API (`GET /api/system/info`) dan Web UI.

    Setiap field diambil langsung dari sistem nyata saat dipanggil.
    Field yang gagal diambil (mis. psutil tidak terpasang) akan bernilai
    None, bukan mengarang data.
    """
    info: Dict[str, Any] = {
        "os": f"{platform.system()} {platform.release()}",
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor() or None,
        "python_version": sys.version.split()[0],
        "hostname": None,
        "local_ip": None,
        "cpu_cores_logical": None,
        "cpu_cores_physical": None,
        "cpu_percent": None,
        "ram_total_gb": None,
        "ram_used_gb": None,
        "ram_percent": None,
        "disk_total_gb": None,
        "disk_used_gb": None,
        "disk_percent": None,
        "network_interfaces": [],
    }

    try:
        hostname = socket.gethostname()
        info["hostname"] = hostname
        try:
            info["local_ip"] = socket.gethostbyname(hostname)
        except OSError:
            info["local_ip"] = None
    except OSError:
        pass

    if psutil is not None:
        try:
            info["cpu_cores_logical"] = psutil.cpu_count(logical=True)
            info["cpu_cores_physical"] = psutil.cpu_count(logical=False)
        except Exception:  # pragma: no cover
            pass
        try:
            info["cpu_percent"] = psutil.cpu_percent(interval=0.3)
        except Exception:  # pragma: no cover
            pass
        try:
            mem = psutil.virtual_memory()
            info["ram_total_gb"] = round(mem.total / (1024 ** 3), 1)
            info["ram_used_gb"] = round(mem.used / (1024 ** 3), 1)
            info["ram_percent"] = mem.percent
        except Exception:  # pragma: no cover
            pass

        info["network_interfaces"] = _network_interfaces()

    try:
        usage = shutil.disk_usage("/")
        info["disk_total_gb"] = round(usage.total / (1024 ** 3), 1)
        info["disk_used_gb"] = round(usage.used / (1024 ** 3), 1)
        info["disk_percent"] = round((usage.used / usage.total) * 100, 1) if usage.total else None
    except OSError:  # pragma: no cover
        pass

    return info


def get_system_summary() -> str:
    """Mengembalikan ringkasan informasi sistem (read-only) sebagai teks natural."""
    info = get_system_info_dict()
    lines: List[str] = []

    lines.append(f"OS: {info['os']}")
    lines.append(f"Arsitektur: {info['architecture']}")
    if info["processor"]:
        lines.append(f"Processor: {info['processor']}")
    lines.append(f"Python: {info['python_version']}")

    if info["hostname"]:
        lines.append(f"Hostname: {info['hostname']}")
    if info["local_ip"]:
        lines.append(f"IP lokal: {info['local_ip']}")

    if info["cpu_cores_logical"] is not None:
        cores_text = f"{info['cpu_cores_logical']} core (logical)"
        if info["cpu_cores_physical"] is not None:
            cores_text += f", {info['cpu_cores_physical']} core (physical)"
        lines.append(f"CPU cores: {cores_text}")
    if info["cpu_percent"] is not None:
        lines.append(f"CPU usage: {info['cpu_percent']}%")

    if info["ram_total_gb"] is not None:
        lines.append(
            "RAM: {used:.1f} GB terpakai dari {total:.1f} GB ({percent}%)".format(
                used=info["ram_used_gb"],
                total=info["ram_total_gb"],
                percent=info["ram_percent"],
            )
        )
    elif psutil is None:
        lines.append("CPU/RAM: detail tidak tersedia (psutil belum terpasang).")

    if info["disk_total_gb"] is not None:
        lines.append(
            "Disk: {used:.1f} GB terpakai dari {total:.1f} GB".format(
                used=info["disk_used_gb"],
                total=info["disk_total_gb"],
            )
        )

    if info["network_interfaces"]:
        iface_text = ", ".join(
            f"{iface['name']} ({iface['address']})" for iface in info["network_interfaces"]
        )
        lines.append(f"Network: {iface_text}")

    return "\n".join(lines)


def _handle(arguments: Dict[str, Any]) -> str:
    return get_system_summary()


def system_info_tool() -> Tool:
    return Tool(
        name="system_info",
        description=(
            "Mengambil informasi dasar sistem tempat RIN berjalan: OS, arsitektur, "
            "processor, versi Python, hostname, IP lokal, jumlah core CPU, "
            "penggunaan CPU/RAM, disk, dan interface jaringan. Read-only, tidak "
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
