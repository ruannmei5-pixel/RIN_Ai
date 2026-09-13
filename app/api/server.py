"""
server.py

Entry point FastAPI untuk RIN (PHASE 5A).

Tanggung jawab file ini HANYA:
- Membuat instance FastAPI.
- Membangun satu instance Assistant bersama ("default session") saat
  server start, memakai SQLite memory yang SAMA dengan CLI (tidak ada
  database baru untuk API).
- Memasang CORS middleware (khusus development, lihat catatan di bawah).
- Mendaftarkan router dari app/api/routes.py.

TIDAK ada logic Ollama di file ini. Semua logic percakapan tetap ada di
app/core/assistant.py + app/llm/ollama_client.py, dipanggil lewat
Assistant yang sama persis dengan yang dipakai CLI (app/main.py).

CLI lama sama sekali tidak terpengaruh oleh file ini: `python run.py`
tetap berjalan seperti biasa.

Cara menjalankan server (development, dapat diakses dari perangkat lain
di jaringan lokal seperti HP):

    python -m uvicorn app.api.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.assistant import Assistant
from app.core.config import ConfigError, load_config
from app.core.logger import get_logger

# Direktori frontend statis (PHASE 5B). Dihitung relatif terhadap file ini
# (app/api/server.py -> ../../web) supaya tidak bergantung pada current
# working directory saat uvicorn dijalankan.
_WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"

logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Startup/shutdown FastAPI (menggantikan @app.on_event yang deprecated).

    Saat startup:
    - Memuat config/config.json (sumber konfigurasi yang sama dengan CLI).
    - Membangun satu Assistant bersama. Assistant ini memuat riwayat dari
      SQLite (data/rin_memory.db) persis seperti CLI, dan setiap turn
      yang berhasil akan tersimpan kembali ke SQLite yang sama.
    - Membuat threading.Lock() untuk menyerialkan akses ke Assistant.
      Ini PENTING karena Assistant menyimpan riwayat percakapan
      in-memory (_history) yang tidak aman diakses oleh beberapa
      request/thread secara bersamaan. Untuk PHASE 5A (satu default
      session), ini cukup; multi-session sungguhan (satu Assistant/lock
      per session_id) adalah pekerjaan phase berikutnya.
    """
    try:
        config = load_config()
    except ConfigError:
        logger.exception("Gagal memuat konfigurasi saat startup RIN API.")
        raise

    app.state.config = config
    app.state.assistant = Assistant(config)
    app.state.assistant_lock = threading.Lock()

    logger.info(
        "RIN API siap. assistant=%s model=%s host=%s",
        config.assistant_name,
        config.ollama.model,
        config.ollama.host,
    )

    yield

    logger.info("RIN API berhenti.")


app = FastAPI(
    title="RIN API",
    description="Responsive Intelligent Navigator API",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------
# CORS
#
# PENTING: allow_origins=["*"] di bawah ini HANYA untuk development di
# jaringan lokal (PHASE 5A: laptop + HP di jaringan WiFi yang sama).
#
# TODO (sebelum RIN API dibuka ke internet / dipakai di luar LAN):
# - Ganti allow_origins=["*"] menjadi daftar origin spesifik yang
#   dipercaya.
# - Tambahkan autentikasi (mis. API key atau JWT).
# - Jalankan di belakang HTTPS (reverse proxy seperti nginx/Caddy).
# - Pertimbangkan rate limiting.
# ---------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# ---------------------------------------------------------------------
# Frontend statis (PHASE 5B: Web UI RIN)
#
# PENTING: mount ini HARUS berada SETELAH app.include_router(router) dan
# setelah route bawaan FastAPI (/docs, /openapi.json, /redoc) terdaftar
# (route-route tersebut otomatis terdaftar saat objek FastAPI dibuat, di
# atas). Starlette mencocokkan path berdasarkan urutan pendaftaran route,
# sehingga /api/*, /docs, /openapi.json, dan /redoc tetap diproses oleh
# handler aslinya masing-masing, TIDAK diambil alih oleh static files ini.
#
# html=True membuat StaticFiles otomatis menyajikan web/index.html untuk
# "/" maupun untuk path yang tidak dikenali (SPA-style fallback), jadi
# http://localhost:8000/ dan http://IP-LAPTOP:8000/ langsung membuka UI
# RIN, bukan Swagger.
# ---------------------------------------------------------------------
if _WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
else:  # pragma: no cover - jaring pengaman jika folder web/ belum ada
    logger.warning(
        "Folder frontend web/ tidak ditemukan di %s; UI RIN tidak akan tersedia.",
        _WEB_DIR,
    )
