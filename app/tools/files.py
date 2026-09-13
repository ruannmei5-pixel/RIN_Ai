"""
files.py

Tool file_reader untuk RIN (PHASE 6E).

KEAMANAN (ATURAN UTAMA #12 & instruksi PHASE 6E):
- Hanya boleh membaca file dengan ekstensi .txt, .md, .json, .csv.
- Hanya boleh membaca file di dalam WORKSPACE_DIR (folder `workspace/`
  di root project) — TIDAK ADA akses bebas ke seluruh filesystem.
- Path traversal (../, ..\\, path absolut, path dengan drive letter)
  ditolak secara eksplisit SEBELUM maupun SETELAH resolve(), lewat
  pengecekan bahwa hasil akhir path benar-benar berada di dalam
  WORKSPACE_DIR.
- Nama file yang mengindikasikan data sensitif (password, credential,
  private key, .env, token, dst.) ditolak untuk Phase 6 ini, sesuai
  instruksi ("kecuali nanti dibuat permission system khusus").
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from app.tools.registry import Tool, ToolPermission, ToolValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_DIR = PROJECT_ROOT / "workspace"

_ALLOWED_EXTENSIONS = {".txt", ".md", ".json", ".csv"}
_MAX_FILE_SIZE_BYTES = 200_000  # ~200 KB — cukup untuk catatan/teks biasa
_MAX_PREVIEW_CHARS = 4000

_SENSITIVE_KEYWORDS = (
    "password",
    "passwd",
    "credential",
    "secret",
    "private_key",
    "privatekey",
    "id_rsa",
    ".env",
    "token",
    "apikey",
    "api_key",
)


def resolve_safe_path(relative_path: str) -> Path:
    """
    Menggabungkan `relative_path` dengan WORKSPACE_DIR, me-resolve-nya,
    dan menolak (raise ToolValidationError) jika hasilnya:
    - berada di luar WORKSPACE_DIR (path traversal / path absolut), atau
    - namanya mengindikasikan file sensitif, atau
    - ekstensinya tidak diizinkan.
    """
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ToolValidationError("Nama file tidak boleh kosong.")

    relative_path = relative_path.strip()

    # Tolak path absolut / drive letter Windows / traversal secara
    # eksplisit dahulu (string-level, TIDAK bergantung pada bagaimana
    # `pathlib` mem-parsing separator di OS tertentu — mis. backslash
    # tidak dianggap separator oleh PurePosixPath di Linux, jadi
    # ".." tetap harus dicek langsung sebagai substring juga).
    if relative_path.startswith(("/", "\\")) or ":" in relative_path:
        raise ToolValidationError("RIN hanya dapat membaca file di dalam folder workspace.")

    if ".." in relative_path or ".." in Path(relative_path).parts:
        raise ToolValidationError("RIN hanya dapat membaca file di dalam folder workspace.")

    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    workspace_resolved = WORKSPACE_DIR.resolve()
    candidate = (WORKSPACE_DIR / relative_path).resolve()

    try:
        candidate.relative_to(workspace_resolved)
    except ValueError as exc:
        raise ToolValidationError(
            "RIN hanya dapat membaca file di dalam folder workspace."
        ) from exc

    lowered_name = candidate.name.lower()
    if any(keyword in lowered_name for keyword in _SENSITIVE_KEYWORDS):
        raise ToolValidationError(
            "RIN tidak diizinkan membaca file yang tampak berisi data sensitif."
        )

    if candidate.suffix.lower() not in _ALLOWED_EXTENSIONS:
        raise ToolValidationError(
            "RIN hanya dapat membaca file dengan ekstensi: "
            + ", ".join(sorted(_ALLOWED_EXTENSIONS))
        )

    return candidate


def read_workspace_file(relative_path: str) -> str:
    """Membaca isi file di dalam workspace/ dengan aman. Lihat resolve_safe_path()."""
    path = resolve_safe_path(relative_path)

    if not path.exists():
        raise ToolValidationError(
            f"File '{relative_path.strip()}' tidak ditemukan di folder workspace."
        )
    if not path.is_file():
        raise ToolValidationError(f"'{relative_path.strip()}' bukan file.")
    if path.stat().st_size > _MAX_FILE_SIZE_BYTES:
        raise ToolValidationError("File terlalu besar untuk dibaca (maksimum 200 KB).")

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ToolValidationError("RIN gagal membaca file tersebut.") from exc

    return content


def _handle(arguments: Dict[str, Any]) -> str:
    filename = arguments.get("filename", "")

    try:
        content = read_workspace_file(filename)
    except ToolValidationError as exc:
        return str(exc)

    if len(content) > _MAX_PREVIEW_CHARS:
        content = content[:_MAX_PREVIEW_CHARS] + "\n... (dipotong, file terlalu panjang)"

    return f"Isi file '{str(filename).strip()}':\n\n{content}"


def file_reader_tool() -> Tool:
    return Tool(
        name="file_reader",
        description=(
            "Membaca isi file teks (.txt, .md, .json, .csv) yang berada di "
            "dalam folder workspace/ milik project RIN. Tidak dapat mengakses "
            "file di luar folder ini."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": (
                        "Nama atau path relatif file di dalam folder workspace, "
                        "contoh: 'catatan.txt'."
                    ),
                }
            },
            "required": ["filename"],
        },
        permission=ToolPermission.READ_ONLY,
        handler=_handle,
        status_message="📁 RIN membaca file...",
    )
