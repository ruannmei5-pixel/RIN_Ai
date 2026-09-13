"""
schemas.py

Model request/response (Pydantic) untuk RIN API (PHASE 5A).

Skema di sini sengaja dibuat sederhana dan generik, tidak spesifik ke
Ollama atau ke satu endpoint saja, supaya mudah dipakai ulang antara
endpoint /api/chat (non-streaming) dan /api/chat/stream (streaming).
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """Body request untuk POST /api/chat dan POST /api/chat/stream."""

    message: str = Field(
        ...,
        min_length=1,
        description="Pesan dari user untuk RIN. Tidak boleh kosong.",
        examples=["hei rin"],
    )
    session_id: Optional[str] = Field(
        default=None,
        description=(
            "ID sesi percakapan (opsional). BELUM digunakan pada PHASE 5A: "
            "RIN saat ini masih memakai satu memory/session default "
            "(SQLite yang sama dengan CLI). Field ini sudah disediakan dari "
            "sekarang supaya kontrak API tidak perlu berubah ketika "
            "multi-session diimplementasikan pada phase berikutnya."
        ),
        examples=[None],
    )

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        """Validasi tambahan: pesan tidak boleh berisi whitespace saja."""
        if not value.strip():
            raise ValueError("message tidak boleh kosong.")
        return value


class ChatResponse(BaseModel):
    """Body response untuk POST /api/chat (non-streaming)."""

    response: str = Field(..., description="Balasan final dari RIN.")


class HealthResponse(BaseModel):
    """Body response untuk GET /api/health."""

    status: str = Field(..., examples=["ok"])
    assistant: str = Field(..., examples=["RIN"])
    model: str = Field(..., examples=["qwen3:4b"])


class NetworkInterfaceInfo(BaseModel):
    """Satu interface jaringan lokal (PHASE 7)."""

    name: str
    address: str


class SystemInfoResponse(BaseModel):
    """Body response untuk GET /api/system/info (PHASE 7, read-only)."""

    os: str
    os_version: Optional[str] = None
    architecture: Optional[str] = None
    processor: Optional[str] = None
    python_version: str
    hostname: Optional[str] = None
    local_ip: Optional[str] = None
    cpu_cores_logical: Optional[int] = None
    cpu_cores_physical: Optional[int] = None
    cpu_percent: Optional[float] = None
    ram_total_gb: Optional[float] = None
    ram_used_gb: Optional[float] = None
    ram_percent: Optional[float] = None
    disk_total_gb: Optional[float] = None
    disk_used_gb: Optional[float] = None
    disk_percent: Optional[float] = None
    network_interfaces: List[NetworkInterfaceInfo] = Field(default_factory=list)


class WorkspaceEntry(BaseModel):
    """Satu entri (file/folder) dalam workspace RIN (PHASE 7)."""

    path: str
    type: str = Field(..., description="'file' atau 'dir'")


class FileListResponse(BaseModel):
    """Body response untuk GET /api/files (PHASE 7)."""

    workspace: str = Field(..., description="Path workspace RIN (relatif ke project root).")
    entries: List[WorkspaceEntry]


class FileReadResponse(BaseModel):
    """Body response untuk GET /api/files/read (PHASE 7)."""

    path: str
    content: str
    truncated: bool = False


class ErrorResponse(BaseModel):
    """
    Bentuk body error yang dikirim ke client saat terjadi kegagalan.

    Dipakai sebagai `detail` pada HTTPException, sehingga client selalu
    menerima `{"detail": {"error": "..."}}` yang konsisten, tanpa
    traceback internal.
    """

    error: str
