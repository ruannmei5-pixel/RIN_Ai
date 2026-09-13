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
from app.llm.ollama_client import (
    OllamaConnectionError,
    OllamaError,
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaTimeoutError,
)

from app.api.schemas import ChatRequest, ChatResponse, HealthResponse

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
    """
    assistant = request.app.state.assistant
    lock: threading.Lock = request.app.state.assistant_lock

    with lock:
        try:
            reply = assistant.ask(payload.message)
        except OllamaError as exc:
            logger.error("Error pada /api/chat: %s", exc)
            status_code, message = _map_ollama_error(exc)
            return JSONResponse(status_code=status_code, content={"error": message})
        except Exception as exc:  # pragma: no cover - jaring pengaman
            logger.exception("Kesalahan tak terduga pada /api/chat: %s", exc)
            return JSONResponse(
                status_code=500,
                content={"error": "Terjadi kesalahan internal pada server."},
            )

    return ChatResponse(response=reply)


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
        generator: Iterator[str] = assistant.ask_stream(payload.message)
        # Memicu eksekusi generator sampai chunk pertama. Di sinilah
        # koneksi ke Ollama sebenarnya terjadi, sehingga error koneksi/
        # model/timeout akan muncul di sini, SEBELUM response streaming
        # dibuka ke client.
        first_chunk = next(generator)
    except OllamaError as exc:
        lock.release()
        logger.error("Error pada /api/chat/stream (sebelum streaming dimulai): %s", exc)
        status_code, message = _map_ollama_error(exc)
        return JSONResponse(status_code=status_code, content={"error": message})
    except StopIteration:
        lock.release()
        logger.error("Ollama tidak menghasilkan chunk apa pun pada /api/chat/stream.")
        return JSONResponse(
            status_code=502,
            content={"error": "Ollama tidak menghasilkan jawaban."},
        )
    except Exception as exc:  # pragma: no cover - jaring pengaman
        lock.release()
        logger.exception("Kesalahan tak terduga pada /api/chat/stream: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Terjadi kesalahan internal pada server."},
        )

    def _stream() -> Iterator[str]:
        try:
            yield first_chunk
            for chunk in generator:
                yield chunk
        except OllamaError as exc:
            # 200 OK + beberapa chunk sudah terkirim; tidak bisa lagi
            # mengubah status HTTP. Catat ke logger dan sudahi stream.
            logger.error("Stream /api/chat/stream terputus di tengah jalan: %s", exc)
        except Exception as exc:  # pragma: no cover - jaring pengaman
            logger.exception("Kesalahan tak terduga di tengah stream: %s", exc)
        finally:
            lock.release()

    return StreamingResponse(_stream(), media_type="text/plain; charset=utf-8")
