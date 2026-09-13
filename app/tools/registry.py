"""
registry.py

Tool Registry & Tool Manager untuk RIN (PHASE 6A).

Tanggung jawab modul ini, dan HANYA modul ini:
- Mendaftarkan tools yang tersedia (satu-satunya "pintu masuk" tool ke
  RIN — lihat ATURAN UTAMA #13: semua tools harus melalui
  registry/allowlist ini).
- Mencari tool berdasarkan nama.
- Memvalidasi bahwa tool ada, aktif, dan argumen berupa dict sebelum
  dijalankan.
- Menjalankan tool dan menangkap SEMUA error dari handler-nya, supaya
  satu tool yang bermasalah tidak pernah membuat RIN crash.
- Mencatat setiap eksekusi tool ke log (PHASE 6I), tanpa pernah
  mencatat isi argumen mentah (bisa saja berisi path/nilai yang tidak
  perlu masuk log).
- Menyediakan schema dalam format tool-calling Ollama, supaya model
  bisa memilih tool secara terstruktur (PHASE 6F), BUKAN dengan
  menebak dari teks bebas.

Modul ini SENGAJA tidak tahu apa-apa tentang isi tool individual
(kalkulator, file, dsb) — implementasi tiap tool ada di file masing-
masing (app/tools/calculator.py, dst) dan hanya mendaftar dirinya ke
sini lewat build_default_tool_manager().
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from app.core.logger import get_logger

logger = get_logger()


# ============================================================
# PERMISSION (PHASE 6J)
#
# Ini adalah fondasi permission MINIMAL untuk Phase 6, khusus untuk
# tools. Ini BERBEDA dan TIDAK menggantikan
# app/security/permissions.py::PermissionLevel, yang merupakan
# kerangka permission umum (READ/WRITE/EXECUTE/SYSTEM) untuk PHASE 10
# dan sengaja belum aktif (masih placeholder). Keduanya akan
# disatukan/diselaraskan nanti pada PHASE 10 jika diperlukan.
# ============================================================

class ToolPermission(str, Enum):
    SAFE = "SAFE"
    READ_ONLY = "READ_ONLY"
    RESTRICTED = "RESTRICTED"


# ============================================================
# ERRORS
# ============================================================

class ToolValidationError(Exception):
    """Input tool tidak valid. Pesan exception ini AMAN ditampilkan ke user."""


class ToolPermissionError(Exception):
    """Tool ditolak karena alasan permission. Pesan ini AMAN ditampilkan ke user."""


# ============================================================
# TOOL & RESULT
# ============================================================

ToolHandler = Callable[[Dict[str, Any]], str]


@dataclass
class Tool:
    name: str
    description: str
    # JSON schema (subset) untuk parameter tool. Dipakai baik untuk
    # tool-calling Ollama maupun sebagai dokumentasi kontrak tool.
    input_schema: Dict[str, Any]
    permission: ToolPermission
    handler: ToolHandler
    # Baris status singkat yang ditampilkan ke UI saat tool ini dipakai
    # (PHASE 6L), mis. "⚙️ RIN menggunakan Calculator...".
    status_message: str = ""
    enabled: bool = True

    def to_ollama_schema(self) -> Dict[str, Any]:
        """Bentuk schema yang dipahami parameter `tools=` client Ollama."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    output: str


# ============================================================
# TOOL MANAGER
# ============================================================

class ToolManager:
    """
    Satu-satunya tempat RIN mendaftarkan, mencari, dan menjalankan
    tools. Assistant TIDAK PERNAH memanggil handler tool secara
    langsung — selalu lewat ToolManager.execute().
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' sudah terdaftar.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def all_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def enabled_tools(self) -> List[Tool]:
        return [tool for tool in self._tools.values() if tool.enabled]

    def set_enabled(self, name: str, enabled: bool) -> None:
        """Menonaktifkan/mengaktifkan tool (ATURAN UTAMA #16)."""
        tool = self._tools.get(name)
        if tool is None:
            logger.warning("Mencoba mengubah status tool yang tidak dikenal: %s", name)
            return
        tool.enabled = enabled

    def ollama_schemas(self) -> List[Dict[str, Any]]:
        """Schema tool AKTIF saja — tool nonaktif tidak pernah ditawarkan ke model."""
        return [tool.to_ollama_schema() for tool in self.enabled_tools()]

    def execute(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        """
        Menjalankan satu tool dengan aman.

        Tidak pernah melempar exception ke caller: semua kegagalan
        (tool tidak dikenal, nonaktif, input tidak valid, error internal)
        dikembalikan sebagai ToolResult(success=False, ...) dengan pesan
        yang aman ditampilkan ke user, dan tetap dicatat ke log.
        """
        tool = self._tools.get(name)

        if tool is None:
            logger.warning("TOOL: %s STATUS: not_found", name)
            return ToolResult(name, False, f"RIN tidak mengenal tool '{name}'.")

        if not tool.enabled:
            logger.info("TOOL: %s STATUS: disabled", name)
            return ToolResult(name, False, f"Tool '{name}' sedang dinonaktifkan.")

        if not isinstance(arguments, dict):
            arguments = {}

        try:
            output = tool.handler(arguments)
            logger.info("TOOL: %s STATUS: success", name)
            return ToolResult(name, True, output)
        except ToolValidationError as exc:
            logger.info("TOOL: %s STATUS: invalid_input", name)
            return ToolResult(name, False, str(exc))
        except ToolPermissionError as exc:
            logger.warning("TOOL: %s STATUS: denied", name)
            return ToolResult(name, False, str(exc))
        except Exception:  # pragma: no cover - jaring pengaman terakhir
            # Sengaja generik: tidak pernah membocorkan detail internal/
            # traceback ke user. Detail lengkap tetap masuk ke log.
            logger.exception("TOOL: %s STATUS: error", name)
            return ToolResult(
                name,
                False,
                "Terjadi kesalahan saat menjalankan tool tersebut.",
            )


# ============================================================
# DEFAULT REGISTRATION
# ============================================================

def build_default_tool_manager() -> ToolManager:
    """
    Membangun ToolManager dengan seluruh tool bawaan Phase 6 terdaftar.

    Import tool individual dilakukan di dalam fungsi ini (bukan di
    top-level module) untuk menghindari kemungkinan circular import,
    karena masing-masing modul tool meng-import Tool/ToolPermission
    dari sini.
    """
    from app.tools.calculator import calculator_tool
    from app.tools.datetime_tool import datetime_tool
    from app.tools.system import system_info_tool
    from app.tools.files import file_reader_tool

    manager = ToolManager()
    manager.register(calculator_tool())
    manager.register(datetime_tool())
    manager.register(system_info_tool())
    manager.register(file_reader_tool())
    return manager
