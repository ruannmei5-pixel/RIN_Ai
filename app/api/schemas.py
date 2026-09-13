"""
schemas.py

Model request/response (Pydantic) untuk RIN API (PHASE 5A).

Skema di sini sengaja dibuat sederhana dan generik, tidak spesifik ke
Ollama atau ke satu endpoint saja, supaya mudah dipakai ulang antara
endpoint /api/chat (non-streaming) dan /api/chat/stream (streaming).
"""

from __future__ import annotations

from typing import Optional

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


class ErrorResponse(BaseModel):
    """
    Bentuk body error yang dikirim ke client saat terjadi kegagalan.

    Dipakai sebagai `detail` pada HTTPException, sehingga client selalu
    menerima `{"detail": {"error": "..."}}` yang konsisten, tanpa
    traceback internal.
    """

    error: str
