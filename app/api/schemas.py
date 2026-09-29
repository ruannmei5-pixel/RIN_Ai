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
    provider: Optional[str] = Field(
        default=None,
        description=(
            "TAHAP 3: override AI provider untuk request ini saja "
            "('ollama' | 'nvidia'). Opsional — jika kosong, "
            "dipakai AI_PROVIDER dari environment. Endpoint lama yang "
            "tidak mengirim field ini tetap kompatibel."
        ),
        examples=[None],
    )
    model: Optional[str] = Field(
        default=None,
        description=(
            "TAHAP 3: override nama model untuk request ini saja. "
            "Opsional — jika kosong, dipakai model default provider yang "
            "dipilih (dari environment/configuration)."
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
    provider_used: Optional[str] = Field(
        default=None,
        description="TAHAP 3: id provider yang benar-benar menjawab (mis. 'ollama').",
    )
    provider_requested: Optional[str] = Field(
        default=None,
        description="TAHAP 3: id provider yang diminta (bisa beda dari provider_used jika fallback dipakai).",
    )
    fallback_used: bool = Field(
        default=False,
        description="TAHAP 3: True jika provider_requested gagal dan RIN memakai AI_FALLBACK_PROVIDER.",
    )


class HealthResponse(BaseModel):
    """Body response untuk GET /api/health."""

    status: str = Field(..., examples=["ok"])
    assistant: str = Field(..., examples=["RIN"])
    model: str = Field(..., examples=["qwen3:4b"])


class PluginInfo(BaseModel):
    """
    Satu entri tool dari Tool Registry (app/tools/registry.py), apa
    adanya — tidak ada status yang dikarang di sini. `enabled`
    mencerminkan ToolManager._tools[name].enabled secara langsung.
    """

    name: str = Field(..., examples=["calculator"])
    description: str
    permission: str = Field(..., examples=["SAFE", "READ_ONLY", "RESTRICTED"])
    enabled: bool
    status_message: str = ""


class ConnectionInfo(BaseModel):
    """
    Satu koneksi/servis eksternal yang dipakai RIN (Ollama, Web Search).

    `status` HANYA salah satu dari: "configured", "connected",
    "not_configured", "disabled" — dipilih berdasarkan kondisi
    backend sungguhan, TIDAK PERNAH di-hardcode "connected" begitu
    saja (lihat routes.py::plugins()).
    """

    name: str = Field(..., examples=["Ollama"])
    status: str = Field(..., examples=["configured", "connected", "not_configured", "disabled"])
    detail: str = ""


class PluginsResponse(BaseModel):
    """Body response untuk GET /api/plugins."""

    tools: list[PluginInfo]
    connections: list[ConnectionInfo]


class PluginToggleRequest(BaseModel):
    """Body request untuk POST /api/plugins/{name}/toggle."""

    enabled: bool = Field(..., description="True untuk mengaktifkan tool, False untuk menonaktifkan.")


class PluginToggleResponse(BaseModel):
    """Body response untuk POST /api/plugins/{name}/toggle."""

    name: str
    enabled: bool


class ErrorResponse(BaseModel):
    """
    Bentuk body error yang dikirim ke client saat terjadi kegagalan.

    Dipakai sebagai `detail` pada HTTPException, sehingga client selalu
    menerima `{"detail": {"error": "..."}}` yang konsisten, tanpa
    traceback internal.
    """

    error: str


# ============================================================
# TAHAP 3 — MULTI AI PROVIDER
# ============================================================

class AIProviderInfo(BaseModel):
    """Satu entri provider untuk GET /api/ai/providers. TIDAK PERNAH berisi API key."""

    id: str = Field(..., examples=["nvidia"])
    name: str = Field(..., examples=["NVIDIA AI"])
    configured: bool = Field(..., description="True jika kredensial minimal (API key/model) sudah diset.")
    available: bool = Field(..., description="True jika health check nyata ke provider berhasil.")
    is_default: bool = Field(default=False, description="True jika ini AI_PROVIDER saat ini.")
    is_fallback: bool = Field(default=False, description="True jika ini AI_FALLBACK_PROVIDER saat ini.")
    active_model: str = Field(default="", description="Model default provider ini (dari environment).")
    detail: str = Field(default="", description="Keterangan singkat status, aman ditampilkan ke user.")


class AIProvidersResponse(BaseModel):
    """Body response untuk GET /api/ai/providers."""

    providers: list[AIProviderInfo]
    fallback_enabled: bool


class AIModelsResponse(BaseModel):
    """Body response untuk GET /api/ai/models?provider=..."""

    provider: str
    models: list[str]
    source: str = Field(
        ...,
        description=(
            "'dynamic' jika daftar diambil langsung dari API provider, "
            "'configured' jika dynamic discovery tidak tersedia dan hanya "
            "model dari environment/configuration yang dikembalikan."
        ),
        examples=["dynamic", "configured"],
    )
