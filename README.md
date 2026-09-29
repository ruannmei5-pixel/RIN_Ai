# RIN — Responsive Intelligent Navigator

RIN adalah AI personal assistant untuk Windows dengan antarmuka CLI dan
Web UI (workspace). Provider AI utama adalah **NVIDIA AI**; **Ollama**
(lokal, model `qwen3:4b`) dipakai sebagai **fallback per-request**.
Ada juga tools bawaan (calculator, datetime, system_info, file_reader)
dan web search otomatis lewat Tavily.

---

## 1. Arsitektur singkat

```text
User (CLI / Web UI)
   ↓
FastAPI (app/api)  ──►  Assistant (app/core/assistant.py)
                           ├── router system_info  ──► ToolManager
                           ├── search_router ──► Tavily (web search)
                           └── AI Provider Router (app/llm/router.py)
                                  ├── NVIDIA AI  (selalu dicoba pertama)
                                  └── Ollama     (fallback jika NVIDIA gagal)
```

- Fallback hanya berlaku untuk **request yang gagal**. Request berikutnya
  tetap mencoba NVIDIA dulu.
- Fallback tidak pernah diam-diam: response menyertakan header
  `X-Provider-Used`, `X-Provider-Requested`, `X-Fallback-Used`,
  `X-Model-Used` (stream) atau field `provider_used`,
  `provider_requested`, `fallback_used` (non-stream).
- Memory percakapan disimpan di SQLite `data/rin_memory.db`.

## 2. Requirements

- Python 3.10+
- Ollama (untuk fallback lokal) dengan model `qwen3:4b`
- (Opsional) API key NVIDIA dan Tavily

## 3. Instalasi

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
ollama pull qwen3:4b
copy .env.example .env
```

Isi `.env` (jangan di-commit):

| Variabel | Fungsi |
|---|---|
| `NVIDIA_API_KEY` | API key NVIDIA (provider utama) |
| `NVIDIA_BASE_URL` | Default `https://integrate.api.nvidia.com/v1` |
| `NVIDIA_MODEL` | Model NVIDIA yang dipakai |
| `NVIDIA_TIMEOUT_SECONDS` | Batas tunggu token pertama (default 25) |
| `NVIDIA_CONNECT_TIMEOUT_SECONDS` | Batas membuka koneksi (default 5) |
| `AI_PROVIDER` | `nvidia` (default) atau `ollama` |
| `AI_FALLBACK_ENABLED` | `true` / `false` |
| `AI_FALLBACK_PROVIDER` | Default `ollama` |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | Opsional, menimpa `config.json` |
| `TAVILY_API_KEY` | Untuk web search otomatis |
| `SEARCH_ROUTER_LLM_CLASSIFIER` | Default `false` (keputusan search lewat rule lokal) |

Tanpa `NVIDIA_API_KEY`, RIN otomatis memakai Ollama. Tanpa
`TAVILY_API_KEY`, RIN menjawab tanpa web search.

## 4. Menjalankan

CLI:

```powershell
python run.py
```

Web UI + API (bisa diakses dari HP di jaringan yang sama):

```powershell
python -m uvicorn app.api.server:app --host 0.0.0.0 --port 8000
```

Buka `http://localhost:8000/`. Dokumentasi API ada di `/docs`.

## 5. Endpoint API

| Method | Path | Fungsi |
|---|---|---|
| GET | `/api/health` | Status server |
| POST | `/api/chat` | Chat non-streaming |
| POST | `/api/chat/stream` | Chat streaming (teks) |
| GET | `/api/plugins` | Daftar tool + status koneksi |
| POST | `/api/plugins/{name}/toggle` | Aktif/nonaktifkan tool |
| GET | `/api/ai/providers` | Status provider (health check nyata) |
| GET | `/api/ai/models?provider=` | Daftar model provider |

## 6. Struktur project

```text
RIN/
├── app/
│   ├── main.py                 # Entry point CLI
│   ├── api/                    # FastAPI: server, routes, schemas
│   ├── core/
│   │   ├── assistant.py        # Orkestrator utama
│   │   ├── config.py           # Loader config.json + environment
│   │   ├── memory.py           # Memory SQLite
│   │   ├── personality.py      # System prompt
│   │   ├── router.py           # Router system_info
│   │   ├── search_router.py    # Deteksi kebutuhan web search
│   │   └── logger.py
│   ├── llm/
│   │   ├── base.py             # Interface AIProvider + error
│   │   ├── router.py           # AI Provider Router (fallback)
│   │   ├── ollama_client.py    # Client Ollama + filter <think>
│   │   └── providers/          # nvidia, ollama, openai_compatible
│   ├── services/web_search.py  # Tavily
│   ├── tools/                  # calculator, datetime, system, files, registry
│   ├── memory/, security/      # Placeholder (PHASE 4 / 10)
├── web/                        # Web UI (index.html, css, js)
├── config/config.json
├── workspace/                  # Sandbox untuk tool file_reader
├── tests/
├── .env.example
└── run.py
```

## 7. Tools

| Tool | Keterangan |
|---|---|
| `calculator` | Aritmatika aman (tanpa `eval`) |
| `datetime` | Tanggal/jam server |
| `system_info` | OS, CPU, RAM, disk (read-only, `psutil` opsional) |
| `file_reader` | Baca `.txt/.md/.json/.csv` di `workspace/` saja |

`system_info` dijalankan langsung lewat router keyword, tanpa meminta
model memilih tool.

## 8. Testing

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

- `test_provider_fallback.py`, `test_nvidia_streaming.py`,
  `test_latency_fastpath.py`, `test_tools.py`, `test_config.py`: offline.
- `test_ollama.py`: butuh Ollama aktif, jika tidak akan di-skip.

## 9. Keamanan

- API key hanya dibaca dari environment/`.env`, tidak pernah di-log.
- `file_reader` dibatasi ke `workspace/`, path traversal ditolak.
- **CORS `allow_origins=["*"]` hanya untuk development LAN.** Sebelum
  dibuka ke internet: batasi origin, tambahkan autentikasi, gunakan HTTPS.
- Permission layer penuh (`app/security`) masih placeholder.

## 10. Troubleshooting

| Gejala | Solusi |
|---|---|
| Selalu memakai Ollama | Cek `NVIDIA_API_KEY` dan `NVIDIA_MODEL`; lihat `GET /api/ai/providers` |
| Jawaban NVIDIA lambat lalu pindah ke Ollama | Timeout tercapai; atur `NVIDIA_TIMEOUT_SECONDS` |
| Tidak bisa terhubung ke Ollama | Jalankan `ollama serve`, cek `ollama list` |
| Web search tidak jalan | Isi `TAVILY_API_KEY` |
| Error tak terduga | Lihat `logs/rin.log` |

## 11. Roadmap

```text
[x] Basic CLI + Ollama
[x] Personality, Memory SQLite, Web UI
[x] Tools (calculator, datetime, system_info, file_reader)
[x] Web search otomatis (Tavily)
[x] Multi provider: NVIDIA utama + Ollama fallback
[ ] Multi-session (session_id belum dipakai backend)
[ ] Application control, Terminal tool
[ ] Permission layer (PHASE 10), logging aksi (PHASE 11)
[ ] Codex workspace, voice lanjutan
```
