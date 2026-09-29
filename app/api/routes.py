"""
routes.py

Endpoint HTTP RIN API (PHASE 5A).

PENTING: file ini TIDAK berisi logic Ollama apa pun. Setiap endpoint
hanya memanggil method yang sudah ada pada `Assistant`
(app/core/assistant.py), yang pada gilirannya memanggil `OllamaClient`
(app/llm/ollama_client.py). Alur tetap:

    FastAPI route -> Assistant -> OllamaClient -> Ollama -> qwen3:4b

Assistant dan lock-nya diambil dari `request.app.state`, dibuat sekali
saat startup server (lihat app/api/server.py) sehingga seluruh request
berbagi satu memory/session default yang sama dengan CLI (SQLite yang
sama, TIDAK ada database baru untuk API).

Semua endpoint didefinisikan sebagai fungsi biasa (`def`, bukan
`async def`). Ini disengaja: Assistant.ask() / Assistant.ask_stream()
bersifat blocking (memanggil Ollama secara sinkron), dan FastAPI/Starlette
otomatis menjalankan path operation function biasa di threadpool
terpisah, sehingga request lain (mis. /api/health) tidak ikut terblokir.
"""

from __future__ import annotations

import threading
from typing import Iterator, Tuple

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.logger import get_logger
from app.llm.base import (
    ProviderAuthError,
    ProviderConnectionError,
    ProviderError,
    ProviderModelNotFoundError,
    ProviderNotConfiguredError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.llm.ollama_client import (
    OllamaConnectionError,
    OllamaError,
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaTimeoutError,
)

from app.api.schemas import (
    AIModelsResponse,
    AIProviderInfo,
    AIProvidersResponse,
    ChatRequest,
    ChatResponse,
    ConnectionInfo,
    HealthResponse,
    PluginInfo,
    PluginsResponse,
    PluginToggleRequest,
    PluginToggleResponse,
)
from app.services.web_search import is_configured as web_search_is_configured

logger = get_logger()

router = APIRouter(prefix="/api")


def _map_ollama_error(exc: OllamaError) -> Tuple[int, str]:
    """
    Memetakan exception Ollama yang sudah ada (app/llm/ollama_client.py)
    ke (status_code HTTP, pesan untuk client) yang masuk akal.

    Detail teknis lengkap tetap dicatat oleh caller ke logger; pesan yang
    dikembalikan di sini adalah pesan singkat yang aman ditampilkan ke
    client (tidak ada traceback).
    """
    if isinstance(exc, OllamaModelNotFoundError):
        return 404, str(exc)
    if isinstance(exc, OllamaTimeoutError):
        return 504, str(exc)
    if isinstance(exc, OllamaConnectionError):
        return 503, str(exc)
    if isinstance(exc, OllamaResponseError):
        return 502, str(exc)
    # OllamaError generik lain yang belum punya subclass spesifik.
    return 500, "Terjadi kesalahan saat menghubungi Ollama."


def _map_provider_error(exc: ProviderError) -> Tuple[int, str]:
    """
    TAHAP 3: sama seperti _map_ollama_error() di atas, tapi untuk
    ProviderError yang dinormalisasi lintas provider (Ollama/NVIDIA/
    — lihat app/llm/base.py). Dipakai supaya /api/chat dan
    /api/chat/stream memetakan status HTTP dengan cara yang SAMA untuk
    provider mana pun yang dipakai.
    """
    if isinstance(exc, ProviderNotConfiguredError):
        return 503, str(exc)
    if isinstance(exc, ProviderAuthError):
        return 401, str(exc)
    if isinstance(exc, ProviderModelNotFoundError):
        return 404, str(exc)
    if isinstance(exc, ProviderTimeoutError):
        return 504, str(exc)
    if isinstance(exc, ProviderConnectionError):
        return 503, str(exc)
    if isinstance(exc, ProviderUnavailableError):
        return 503, str(exc)
    if isinstance(exc, ProviderResponseError):
        return 502, str(exc)
    return 500, "Terjadi kesalahan saat menghubungi AI provider."


def _map_ai_error(exc: Exception) -> Tuple[int, str]:
    """Titik tunggal pemetaan error AI (OllamaError lama + ProviderError baru)."""
    if isinstance(exc, ProviderError):
        return _map_provider_error(exc)
    if isinstance(exc, OllamaError):
        return _map_ollama_error(exc)
    return 500, "Terjadi kesalahan internal pada server."


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """
    Health check sederhana. TIDAK memanggil Ollama/model sama sekali,
    hanya melaporkan bahwa API server hidup dan konfigurasi apa yang
    sedang dipakai.
    """
    config = request.app.state.config
    return HealthResponse(
        status="ok",
        assistant=config.assistant_name,
        model=config.ollama.model,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, request: Request):
    """
    Chat non-streaming: kirim satu pesan, tunggu balasan final RIN
    sekaligus.

    TAHAP 3: `payload.provider`/`payload.model` opsional — jika diisi,
    override AI_PROVIDER/model default untuk request ini saja. Response
    menyertakan provider_used/provider_requested/fallback_used supaya
    client tahu jika fallback dipakai (TIDAK PERNAH diam-diam).
    """
    assistant = request.app.state.assistant
    lock: threading.Lock = request.app.state.assistant_lock

    with lock:
        try:
            reply = assistant.ask(
                payload.message,
                provider=payload.provider,
                model=payload.model,
            )
        except (OllamaError, ProviderError) as exc:
            logger.error("Error pada /api/chat: %s", exc)
            status_code, message = _map_ai_error(exc)
            return JSONResponse(status_code=status_code, content={"error": message})
        except Exception as exc:  # pragma: no cover - jaring pengaman
            logger.exception("Kesalahan tak terduga pada /api/chat: %s", exc)
            return JSONResponse(
                status_code=500,
                content={"error": "Terjadi kesalahan internal pada server."},
            )

        outcome = assistant.last_chat_outcome

    return ChatResponse(
        response=reply,
        provider_used=outcome.provider_used if outcome else None,
        provider_requested=outcome.provider_requested if outcome else None,
        fallback_used=bool(outcome and outcome.fallback_used),
    )


@router.post("/chat/stream")
def chat_stream(payload: ChatRequest, request: Request):
    """
    Chat streaming: balasan RIN dikirim sedikit demi sedikit begitu
    tersedia (menggunakan Assistant.ask_stream() yang sudah memfilter
    <think>/reasoning), tanpa menunggu seluruh jawaban selesai.

    Strategi error handling:
    - Error yang terjadi SEBELUM chunk pertama berhasil didapat (mis.
      Ollama mati, model tidak ditemukan, timeout) masih bisa dilaporkan
      sebagai response HTTP error biasa dengan status code yang sesuai,
      karena belum ada byte response yang terkirim ke client.
    - Error yang terjadi DI TENGAH streaming (setelah sebagian jawaban
      terkirim) tidak bisa lagi mengubah status HTTP (sudah 200 OK).
      Untuk kasus ini, stream dihentikan dengan aman dan error dicatat
      ke logger; client cukup melihat stream berakhir lebih awal dari
      yang diharapkan.
    """
    assistant = request.app.state.assistant
    lock: threading.Lock = request.app.state.assistant_lock

    lock.acquire()

    try:
        generator: Iterator[str] = assistant.ask_stream(
            payload.message,
            provider=payload.provider,
            model=payload.model,
        )
        # Memicu eksekusi generator sampai chunk pertama. Di sinilah
        # koneksi ke AI provider sebenarnya terjadi, sehingga error
        # koneksi/model/timeout akan muncul di sini, SEBELUM response
        # streaming dibuka ke client.
        first_chunk = next(generator)
    except (OllamaError, ProviderError) as exc:
        lock.release()
        logger.error("Error pada /api/chat/stream (sebelum streaming dimulai): %s", exc)
        status_code, message = _map_ai_error(exc)
        return JSONResponse(status_code=status_code, content={"error": message})
    except StopIteration:
        lock.release()
        logger.error("AI provider tidak menghasilkan chunk apa pun pada /api/chat/stream.")
        return JSONResponse(
            status_code=502,
            content={"error": "AI provider tidak menghasilkan jawaban."},
        )
    except Exception as exc:  # pragma: no cover - jaring pengaman
        lock.release()
        logger.exception("Kesalahan tak terduga pada /api/chat/stream: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Terjadi kesalahan internal pada server."},
        )

    # TAHAP 3: metadata provider sudah final di titik ini (chunk pertama
    # sudah ditarik di atas), sehingga aman dikirim sebagai response
    # header SEBELUM body streaming mulai. Header dipilih (bukan field
    # di body) supaya kontrak body /api/chat/stream (teks mentah) TIDAK
    # berubah dan tetap kompatibel dengan frontend lama.
    outcome = assistant.last_chat_outcome
    stream_headers = {}
    if outcome is not None:
        stream_headers["X-Provider-Used"] = outcome.provider_used
        stream_headers["X-Provider-Requested"] = outcome.provider_requested
        stream_headers["X-Fallback-Used"] = "true" if outcome.fallback_used else "false"
        used_provider = assistant.ai_router.get(outcome.provider_used)
        used_model = (payload.model if (payload.model and not outcome.fallback_used) else None) or (
            used_provider.active_model if used_provider else ""
        )
        # Header HTTP hanya boleh ASCII tanpa newline.
        stream_headers["X-Model-Used"] = used_model.encode("ascii", "ignore").decode().replace("\n", "")

    def _stream() -> Iterator[str]:
        try:
            yield first_chunk
            for chunk in generator:
                yield chunk
        except (OllamaError, ProviderError) as exc:
            # 200 OK + beberapa chunk sudah terkirim; tidak bisa lagi
            # mengubah status HTTP. Catat ke logger dan sudahi stream.
            logger.error("Stream /api/chat/stream terputus di tengah jalan: %s", exc)
        except Exception as exc:  # pragma: no cover - jaring pengaman
            logger.exception("Kesalahan tak terduga di tengah stream: %s", exc)
        finally:
            lock.release()

    return StreamingResponse(
        _stream(),
        media_type="text/plain; charset=utf-8",
        headers=stream_headers,
    )


@router.get("/plugins", response_model=PluginsResponse)
def plugins(request: Request) -> PluginsResponse:
    """
    Membaca Tool Registry (app/tools/registry.py) yang SUDAH ADA — tidak
    ada plugin system baru di sini, hanya jendela baca ke ToolManager
    yang sama persis dipakai Assistant untuk decide_tool_call.

    `connections` melaporkan status Ollama/Web Search apa adanya:
    - Ollama: "configured" (host+model dari config.json). Endpoint ini
      TIDAK memanggil Ollama, jadi tidak pernah mengklaim "connected"
      tanpa benar-benar mengetesnya (konsisten dengan /api/health yang
      juga tidak memanggil Ollama).
    - Web Search: "connected" jika TAVILY_API_KEY diset DAN
      config.web_search.enabled True; "not_configured" jika API key
      belum diset; "disabled" jika sengaja dimatikan di config.json.
    """
    assistant = request.app.state.assistant
    config = request.app.state.config

    tools = [
        PluginInfo(
            name=tool.name,
            description=tool.description,
            permission=tool.permission.value,
            enabled=tool.enabled,
            status_message=tool.status_message,
        )
        for tool in assistant.tools.all_tools()
    ]

    if not config.web_search.enabled:
        web_search_status = "disabled"
        web_search_detail = "Web search dimatikan di config.json (web_search.enabled=false)."
    elif web_search_is_configured():
        web_search_status = "connected"
        web_search_detail = f"Tavily aktif, maks {config.web_search.max_results} hasil per pencarian."
    else:
        web_search_status = "not_configured"
        web_search_detail = "TAVILY_API_KEY belum diset (lihat .env.example)."

    connections = [
        ConnectionInfo(
            name="Ollama",
            status="configured",
            detail=f"{config.ollama.model} @ {config.ollama.host}",
        ),
        ConnectionInfo(
            name="Web Search (Tavily)",
            status=web_search_status,
            detail=web_search_detail,
        ),
    ]

    return PluginsResponse(tools=tools, connections=connections)


@router.post("/plugins/{name}/toggle", response_model=PluginToggleResponse)
def toggle_plugin(name: str, payload: PluginToggleRequest, request: Request):
    """
    Enable/disable satu tool lewat ToolManager.set_enabled() yang SUDAH
    ADA (registry.py). Tidak membuat mekanisme enable/disable baru.

    Diserialkan lewat assistant_lock yang sama dengan /api/chat, supaya
    tidak ada race condition dengan request chat yang sedang membaca
    daftar tool aktif (ToolManager.ollama_schemas()).
    """
    assistant = request.app.state.assistant
    lock: threading.Lock = request.app.state.assistant_lock

    with lock:
        tool = assistant.tools.get(name)
        if tool is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"Tool '{name}' tidak ditemukan di Tool Registry."},
            )
        assistant.tools.set_enabled(name, payload.enabled)

    return PluginToggleResponse(name=name, enabled=payload.enabled)


# ============================================================
# TAHAP 3 — MULTI AI PROVIDER: endpoint discovery
# ============================================================

_PROVIDER_DISPLAY_NAMES = {
    "ollama": "Ollama",
    "nvidia": "NVIDIA AI",
}


@router.get("/ai/providers", response_model=AIProvidersResponse)
def list_ai_providers(request: Request) -> AIProvidersResponse:
    """
    GET /api/ai/providers

    Melaporkan ketiga provider (Ollama/NVIDIA/) apa adanya:
    - `configured`: kredensial minimal (API key untuk cloud, host+model
      untuk Ollama) sudah diset.
    - `available`: hasil health check NYATA (bukan diasumsikan "online"
      hanya karena dipilih/dikonfigurasi — lihat BATASAN TAHAP 3).

    TIDAK PERNAH menyertakan API key dalam response.
    """
    assistant = request.app.state.assistant
    config = request.app.state.config
    ai_router = assistant.ai_router

    providers = []
    for provider_id in ("ollama", "nvidia", ):
        provider = ai_router.get(provider_id)
        health = provider.health_check()
        providers.append(
            AIProviderInfo(
                id=provider_id,
                name=_PROVIDER_DISPLAY_NAMES[provider_id],
                configured=health.configured,
                available=health.available,
                is_default=(provider_id == config.ai.provider),
                is_fallback=(provider_id == config.ai.fallback_provider),
                active_model=provider.active_model,
                detail=health.detail,
            )
        )

    return AIProvidersResponse(
        providers=providers,
        fallback_enabled=config.ai.fallback_enabled,
    )


@router.get("/ai/models", response_model=AIModelsResponse)
def list_ai_models(provider: str, request: Request):
    """
    GET /api/ai/models?provider=nvidi|ollama

    Dynamic model discovery jika provider mendukungnya (GET .../models
    untuk NVIDIA/, GET .../api/tags untuk Ollama). Jika
    dynamic discovery gagal/tidak tersedia, fallback ke SATU model dari
    environment/configuration (source="configured"), BUKAN daftar yang
    di-hardcode di kode.
    """
    assistant = request.app.state.assistant
    ai_router = assistant.ai_router

    provider_id = (provider or "").strip().lower()
    ai_provider = ai_router.get(provider_id)

    if ai_provider is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": f"Provider '{provider}' tidak dikenal. "
                f"Gunakan salah satu: ollama, nvidia."
            },
        )

    models = ai_provider.get_models()

    if models:
        return AIModelsResponse(provider=provider_id, models=models, source="dynamic")

    configured_model = ai_provider.active_model
    fallback_models = [configured_model] if configured_model else []

    return AIModelsResponse(provider=provider_id, models=fallback_models, source="configured")
