"""
files.py

Tool file_reader & workspace_list untuk RIN (PHASE 6E, diperluas PHASE 7).

KEAMANAN (ATURAN UTAMA #12 & instruksi PHASE 6E/7):
- Hanya boleh membaca file teks dengan ekstensi yang ada di
  `_ALLOWED_EXTENSIONS` (PHASE 7 menambah .py, .js, .html, .css, .yaml,
  .yml, .log di atas .txt/.md/.json/.csv Phase 6).
- Hanya boleh membaca file di dalam WORKSPACE_DIR (folder `workspace/`
  di root project) — TIDAK ADA akses bebas ke seluruh filesystem.
- Path traversal (../, ..\\, path absolut, path dengan drive letter)
  ditolak secara eksplisit SEBELUM maupun SETELAH resolve(), lewat
  pengecekan bahwa hasil akhir path benar-benar berada di dalam
  WORKSPACE_DIR.
- Nama file yang mengindikasikan data sensitif (password, credential,
  private key, .env, token, dst.) ditolak, sesuai instruksi ("kecuali
  nanti dibuat permission system khusus").
- File dengan ekstensi biner yang dikenal (gambar, executable, arsip,
  dst.) ditolak dengan pesan khusus ("RIN belum mendukung pembacaan
  file tersebut"), bukan pesan "ekstensi tidak diizinkan" yang generik,
  sesuai instruksi PHASE 7.
- `list_workspace_entries()` (PHASE 7) hanya membaca STRUKTUR
  (nama file/folder), tidak pernah membaca ISI file di luar
  ekstensi yang diizinkan.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.tools.registry import Tool, ToolPermission, ToolValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_DIR = PROJECT_ROOT / "workspace"

# PHASE 7: Phase 6 hanya mendukung .txt/.md/.json/.csv. Phase 7 menambah
# beberapa ekstensi teks umum lain, tetap TIDAK PERNAH file biner.
_ALLOWED_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".csv",
    ".py",
    ".js",
    ".html",
    ".css",
    ".yaml",
    ".yml",
    ".log",
}

# Ekstensi biner yang dikenal — dipakai HANYA untuk memberi pesan error
# yang lebih ramah ("RIN belum mendukung pembacaan file tersebut")
# dibanding pesan generik "ekstensi tidak diizinkan". Tidak pernah
# dibaca sebagai teks dalam kondisi apa pun.
_KNOWN_BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".exe", ".dll", ".so", ".bin", ".msi",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".db", ".sqlite", ".sqlite3",
}

_MAX_FILE_SIZE_BYTES = 2_000_000  # 2 MB (PHASE 7); Phase 6 sebelumnya 200 KB
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

    suffix = candidate.suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        if suffix in _KNOWN_BINARY_EXTENSIONS:
            raise ToolValidationError(
                "RIN belum mendukung pembacaan file tersebut."
            )
        raise ToolValidationError(
            "RIN hanya dapat membaca file dengan ekstensi: "
            + ", ".join(sorted(_ALLOWED_EXTENSIONS))
        )

    return candidate


# ============================================================
# WORKSPACE LISTING (PHASE 7)
# ============================================================

def list_workspace_entries() -> List[Dict[str, Any]]:
    """
    Mengembalikan daftar file & folder di dalam WORKSPACE_DIR secara
    rekursif, sebagai list of dict:

        [{"path": "catatan.txt", "type": "file"},
         {"path": "dokumen", "type": "dir"},
         {"path": "dokumen/laporan.txt", "type": "file"}, ...]

    `path` selalu relatif terhadap WORKSPACE_DIR dan memakai forward
    slash ("/") agar konsisten di Windows maupun platform lain. Hanya
    membaca STRUKTUR direktori (nama), tidak pernah membaca isi file.
    Read-only dan tidak pernah keluar dari WORKSPACE_DIR karena hanya
    melakukan `iterdir`/`rglob` di dalamnya.
    """
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    workspace_resolved = WORKSPACE_DIR.resolve()

    entries: List[Dict[str, Any]] = []
    for path in sorted(workspace_resolved.rglob("*")):
        relative = path.relative_to(workspace_resolved).as_posix()
        entries.append({"path": relative, "type": "dir" if path.is_dir() else "file"})

    return entries


def _format_workspace_listing(entries: List[Dict[str, Any]]) -> str:
    if not entries:
        return "Folder workspace RIN saat ini masih kosong."

    files_only = [entry for entry in entries if entry["type"] == "file"]
    lines = [f"Di workspace RIN saat ini ada {len(files_only)} file:"]
    for entry in entries:
        icon = "📁" if entry["type"] == "dir" else "📄"
        lines.append(f"{icon} {entry['path']}")
    return "\n".join(lines)


def _handle_list(arguments: Dict[str, Any]) -> str:
    return _format_workspace_listing(list_workspace_entries())


def workspace_list_tool() -> Tool:
    return Tool(
        name="workspace_list",
        description=(
            "Menampilkan daftar file dan folder yang ada di dalam folder "
            "workspace/ milik project RIN (read-only, hanya nama, tidak "
            "membaca isi file)."
        ),
        input_schema={
            "type": "object",
            "properties": {},
        },
        permission=ToolPermission.READ_ONLY,
        handler=_handle_list,
        status_message="📁 RIN memeriksa isi workspace...",
    )


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
            "Membaca isi file teks (.txt, .md, .json, .csv, .py, .js, .html, "
            ".css, .yaml, .yml, .log) yang berada di dalam folder workspace/ "
            "milik project RIN. Tidak dapat mengakses file di luar folder ini "
            "maupun file biner."
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
