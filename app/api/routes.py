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

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.logger import get_logger
from app.llm.ollama_client import (
    OllamaConnectionError,
    OllamaError,
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaTimeoutError,
)
from app.tools.files import list_workspace_entries, read_workspace_file
from app.tools.registry import ToolValidationError
from app.tools.system import get_system_info_dict

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    FileListResponse,
    FileReadResponse,
    HealthResponse,
    SystemInfoResponse,
)

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


# ============================================================
# SYSTEM / FILES (PHASE 7)
#
# Endpoint di bawah ini SENGAJA tidak melalui Assistant/Ollama sama
# sekali — keduanya read-only dan murni memanggil fungsi tool yang
# sama persis dipakai lewat chat (app/tools/system.py,
# app/tools/files.py), supaya Web UI bisa menampilkan panel System
# Info dan File Workspace tanpa perlu menunggu keputusan LLM, dan
# tanpa pernah menyentuh assistant_lock/riwayat percakapan.
# ============================================================

@router.get("/system/info", response_model=SystemInfoResponse)
def system_info() -> SystemInfoResponse:
    """
    Informasi sistem read-only (OS, hardware dasar, CPU, RAM, disk,
    network). Data diambil langsung dari sistem nyata setiap request,
    tidak pernah di-cache atau dikarang.
    """
    return SystemInfoResponse(**get_system_info_dict())


@router.get("/files", response_model=FileListResponse)
def list_files() -> FileListResponse:
    """
    Daftar file & folder di dalam folder workspace/ RIN (read-only).
    Tidak pernah menampilkan apa pun di luar workspace.
    """
    entries = list_workspace_entries()
    return FileListResponse(workspace="workspace/", entries=entries)


@router.get("/files/read", response_model=FileReadResponse)
def read_file(path: str = Query(..., description="Path relatif di dalam folder workspace/.")):
    """
    Membaca isi satu file teks di dalam workspace/ RIN.

    Menggunakan validasi keamanan yang sama persis dengan tool
    `file_reader` (path traversal, ekstensi, ukuran, nama sensitif —
    lihat app/tools/files.py::resolve_safe_path). Error validasi
    dikembalikan sebagai 400 dengan pesan ramah, bukan stack trace.
    """
    try:
        content = read_workspace_file(path)
    except ToolValidationError as exc:
        message = str(exc)
        status_code = 404 if "tidak ditemukan" in message.lower() else 400
        return JSONResponse(status_code=status_code, content={"error": message})
    except Exception as exc:  # pragma: no cover - jaring pengaman
        logger.exception("Kesalahan tak terduga pada /api/files/read: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Terjadi kesalahan internal saat membaca file."},
        )

    truncated = False
    if len(content) > 20_000:
        content = content[:20_000]
        truncated = True

    return FileReadResponse(path=path, content=content, truncated=truncated)
