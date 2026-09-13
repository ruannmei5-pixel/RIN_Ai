# RIN — Responsive Intelligent Navigator

RIN adalah AI personal assistant lokal untuk Windows yang berjalan di atas
**Ollama** (local LLM runtime) dengan model **Qwen3 4B**. Project ini
dibangun secara bertahap (phase-by-phase). **Dokumen ini mencakup PHASE 1:
Basic RIN CLI + Ollama + Qwen3 4B + Configuration + Logging.**

Memory (SQLite), tools (system/file/application/terminal), dan security
(permission layer) sudah memiliki struktur modul, tetapi isinya masih
placeholder dan akan diimplementasikan pada phase-phase berikutnya.

---

## 1. Overview

- **Nama**: RIN (Responsive Intelligent Navigator)
- **Bahasa**: Python (target 3.14+, minimum 3.10)
- **LLM runtime**: Ollama (lokal, tidak butuh API key/internet untuk inferensi)
- **Model**: `qwen3:4b`
- **Target hardware**: ASUS TUF A15, Ryzen 5 7000, RTX 2050, RAM 8 GB
- **Fase saat ini**: Phase 1 — percakapan teks dasar via CLI

Karena RAM terbatas (8 GB), gunakan model kelas ~4B seperti Qwen3 4B dan
hindari menjalankan banyak model sekaligus di Ollama.

---

## 2. Requirements

| Kebutuhan | Versi | Keterangan |
|---|---|---|
| Python | 3.10+ (target 3.14+) | |
| Ollama | Versi terbaru | Harus mendukung model Qwen3 |
| Git | Versi terbaru | Version control |

---

## 3. Installation

### 3.1 Python

1. Unduh dari https://www.python.org/downloads/
2. Saat instalasi, centang **"Add Python to PATH"**.
3. Cek instalasi di PowerShell:

```powershell
python --version
```

### 3.2 Ollama

1. Unduh dari https://ollama.com/download
2. Install seperti aplikasi Windows biasa.
3. Cek instalasi:

```powershell
ollama --version
```

### 3.3 Git

1. Unduh dari https://git-scm.com/download/win
2. Cek instalasi:

```powershell
git --version
```

### 3.4 Checklist Environment

```text
[ ] Python terpasang dan terdeteksi di PATH
[ ] Ollama terpasang
[ ] Git terpasang
[ ] Virtual environment (.venv) dibuat
[ ] Model qwen3:4b sudah di-pull
[ ] Folder project RIN siap
```

---

## 4. Virtual Environment

Dari root folder project (`RIN/`), jalankan di PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

> Jika muncul error "execution of scripts is disabled", jalankan PowerShell
> sebagai Administrator lalu:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

Install dependency:

```powershell
pip install -r requirements.txt
```

Untuk keperluan development/testing (opsional, tidak dibutuhkan untuk
menjalankan RIN secara normal):

```powershell
pip install -r requirements-dev.txt
```

---

## 5. Ollama Setup

### 5.1 Menjalankan Ollama

Setelah diinstall, Ollama biasanya berjalan otomatis di background (ada
ikon di system tray). Pastikan API-nya aktif:

```powershell
ollama list
```

Jika perintah ini berhasil menampilkan daftar model, Ollama sudah berjalan
dan API-nya bisa diakses di `http://localhost:11434`.

Jika belum berjalan, jalankan manual:

```powershell
ollama serve
```

### 5.2 Qwen3 4B Setup

Pull model:

```powershell
ollama pull qwen3:4b
```

Verifikasi model sudah tersedia:

```powershell
ollama list
```

Pastikan `qwen3:4b` muncul di daftar.

**Catatan tentang Qwen3 (thinking model):** Qwen3 punya kemampuan
"thinking" (reasoning internal) yang secara default bisa membuat model
mengeluarkan blok reasoning bersama jawabannya. `app/llm/ollama_client.py`
sudah secara eksplisit meminta `think=False` ke Ollama, dan sebagai lapisan
pengaman tambahan tetap membersihkan tag `<think>...</think>` jika entah
bagaimana masih muncul (mis. versi Ollama yang lebih lama).

**Model tidak di-hardcode di Python.** Ganti model yang dipakai RIN cukup
dengan mengedit `config/config.json`.

---

## 6. Project Structure

```text
RIN/
├── .venv/                     # Virtual environment (tidak di-commit)
│
├── app/
│   ├── __init__.py
│   ├── main.py                 # Entry point CLI: load config, banner, loop
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── assistant.py        # Orchestration layer (User -> LLM -> Response)
│   │   ├── config.py           # Loader config/config.json
│   │   └── logger.py           # Setup logging (console + logs/rin.log)
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   └── ollama_client.py    # Komunikasi ke Ollama via official `ollama` client
│   │
│   ├── memory/                 # PLACEHOLDER — diisi pada PHASE 4
│   │   ├── __init__.py
│   │   ├── database.py         # Koneksi SQLite (data/rin_memory.db)
│   │   ├── conversation.py     # Conversation history
│   │   └── long_term.py        # save/get/search/delete/list_memories
│   │
│   ├── tools/                  # PLACEHOLDER — diisi mulai PHASE 5
│   │   ├── __init__.py
│   │   ├── system.py           # System info (PHASE 5, read-only)
│   │   ├── files.py            # File assistant sandbox workspace/ (PHASE 6)
│   │   ├── applications.py     # Buka aplikasi whitelist (PHASE 7)
│   │   └── terminal.py         # Command whitelist (PHASE 8)
│   │
│   └── security/               # PLACEHOLDER — diisi pada PHASE 10
│       ├── __init__.py
│       └── permissions.py      # Level READ/WRITE/EXECUTE/SYSTEM
│
├── config/
│   └── config.json             # Konfigurasi RIN (nama, bahasa, host+model Ollama)
│
├── data/
│   └── .gitkeep                # Untuk data/rin_memory.db pada PHASE 4
│
├── logs/
│   └── .gitkeep                # rin.log (dan nanti actions.log) dibuat otomatis
│
├── workspace/
│   └── README.md                # Sandbox file assistant (PHASE 6)
│
├── tests/
│   ├── __init__.py
│   ├── test_config.py          # Test loading konfigurasi
│   └── test_ollama.py          # Test konektivitas, model availability, respons dasar
│
├── .env.example
├── .gitignore
├── requirements.txt             # Dependency runtime (ollama)
├── requirements-dev.txt         # Dependency tambahan untuk testing (pytest)
├── README.md
└── run.py                       # Jalankan RIN dari sini
```

---

## 7. Running RIN

Pastikan:
1. Ollama sudah berjalan (`ollama list` berhasil).
2. Virtual environment sudah aktif.
3. Model `qwen3:4b` sudah di-pull.

Jalankan:

```powershell
python run.py
```

### Expected Output

```text
================================
 RIN
 Responsive Intelligent Navigator
================================

RIN siap membantu.

You: hai rin

RIN: [jawaban dari Qwen3 4B]

You: exit

RIN: Sampai jumpa!
```

Ketik `exit`, `quit`, atau `keluar` untuk mengakhiri sesi.

---

## 8. Configuration

File: `config/config.json`

```json
{
    "assistant_name": "RIN",
    "assistant_full_name": "Responsive Intelligent Navigator",
    "language": "id",
    "ollama": {
        "host": "http://localhost:11434",
        "model": "qwen3:4b",
        "timeout_seconds": 60
    }
}
```

- `ollama.host`: alamat API Ollama lokal. Biasanya tidak perlu diubah.
- `ollama.model`: nama model yang sudah di-pull via `ollama pull <model>`.
  **Ganti field ini saja** untuk berpindah model, tanpa mengubah kode.
- `ollama.timeout_seconds`: batas waktu tunggu balasan model (opsional,
  default 60 detik jika tidak diisi).

Tidak ada credential/API key yang disimpan di file ini karena Ollama
berjalan lokal dan tidak membutuhkan API key. `.env.example` disiapkan
untuk phase mendatang jika ada environment variable yang benar-benar
diperlukan (belum digunakan pada Phase 1).

---

## 9. Memory

**Belum diimplementasikan (placeholder saja).** Modul `app/memory/database.py`,
`conversation.py`, dan `long_term.py` sudah ada sebagai kerangka, dan akan
diisi pada **PHASE 4** menggunakan SQLite (`data/rin_memory.db`), dengan
pemisahan conversation history dan long-term memory yang hanya disimpan
saat user eksplisit meminta ("RIN, ingat bahwa ...").

Pada Phase 1, riwayat percakapan hanya disimpan sementara di memory proses
(`app/core/assistant.py`), hilang setiap kali RIN ditutup.

---

## 10. Tools

**Belum diimplementasikan (placeholder saja).** Struktur modul sudah
disiapkan di `app/tools/` dan akan diisi bertahap mulai:
- PHASE 5: `system.py` — System information (read-only, pakai `psutil`)
- PHASE 6: `files.py` — File assistant (sandbox `workspace/`, cegah path traversal)
- PHASE 7: `applications.py` — Application control (whitelist + konfirmasi)
- PHASE 8: `terminal.py` — Terminal tool (whitelist command + konfirmasi + logging)
- PHASE 9: Tool calling architecture terpadu (tool registry)

Pada Phase 1, RIN hanya melakukan percakapan teks murni — tidak ada akses
file, sistem, atau eksekusi apa pun.

---

## 11. Security

**Belum diimplementasikan (placeholder saja).** `app/security/permissions.py`
sudah mendefinisikan enum `PermissionLevel` (READ/WRITE/EXECUTE/SYSTEM) dan
default policy-nya, tetapi logika konfirmasi penuh baru diimplementasikan
pada **PHASE 10**:

```text
READ    = allowed
WRITE   = confirmation
EXECUTE = confirmation
SYSTEM  = confirmation
```

Prinsip yang akan dipegang: AI menyarankan → Tool memvalidasi → Permission
layer → User confirmation jika diperlukan → Tool execution → Logging.

---

## 12. Logging

- `logs/rin.log` — log utama (startup, shutdown, error), dibuat otomatis
  saat RIN dijalankan pertama kali.
- `logs/actions.log` — akan ditambahkan pada **PHASE 11** untuk mencatat
  tool usage, command execution, dan memory changes secara terpisah.

Password, API key, secret, dan credential **tidak pernah** dicatat ke log.

---

## 13. Dependency

`requirements.txt` (runtime):

| Package | Fungsi | Kenapa diperlukan |
|---|---|---|
| `ollama` | Official Python client untuk Ollama | Komunikasi ke `http://localhost:11434` (chat, list model) tanpa perlu implementasi HTTP manual. Membawa `httpx` sebagai dependency transitif, yang juga dipakai untuk deteksi error koneksi/timeout secara spesifik. |

`requirements-dev.txt` (opsional, hanya untuk development):

| Package | Fungsi | Kenapa diperlukan |
|---|---|---|
| `pytest` | Test runner | Menjalankan `tests/test_config.py` dan `tests/test_ollama.py` |

**Dependency yang DIHAPUS saat audit:** `requests` — sebelumnya dipakai
untuk memanggil REST API Ollama secara manual. Setelah refactor ke
official `ollama` Python client, `requests` tidak lagi diperlukan.

**Belum ditambahkan** (akan ditambahkan hanya saat modul terkait benar-benar
diimplementasikan, bukan sekarang): `psutil` (PHASE 5, system info),
`python-dotenv` (jika environment variable benar-benar dipakai di phase
mendatang).

---

## 14. Testing

Install dependency testing:

```powershell
pip install -r requirements-dev.txt
```

Jalankan seluruh test:

```powershell
pytest
```

- `tests/test_config.py` — menguji `load_config()`: config valid, file
  hilang, JSON tidak valid, field wajib hilang. Test ini memakai file
  konfigurasi sementara (`tmp_path`), **tidak menyentuh** `config/config.json`
  production.
- `tests/test_ollama.py` — menguji konektivitas Ollama, ketersediaan model
  `qwen3:4b`, dan respons dasar `Assistant.ask()`. Test ini butuh Ollama
  yang benar-benar berjalan; jika Ollama tidak aktif atau model belum
  di-pull, test akan **di-skip** (bukan gagal), sehingga aman dijalankan
  di lingkungan mana pun. Test ini tidak menyentuh database production
  karena memory SQLite baru ada di PHASE 4.

---

## 15. Troubleshooting

| Gejala | Kemungkinan Penyebab | Solusi |
|---|---|---|
| `RIN: Maaf, saya tidak bisa terhubung ke Ollama` | Ollama belum berjalan | Jalankan `ollama serve` atau buka aplikasi Ollama, cek dengan `ollama list` |
| `RIN: Maaf, model yang dikonfigurasi tidak ditemukan` | Model belum di-pull, atau nama model salah di config | Jalankan `ollama pull qwen3:4b`, cocokkan dengan `config/config.json` |
| `RIN: Maaf, permintaan ke model terlalu lama (timeout)` | Model terlalu berat untuk RAM 8 GB, atau laptop sedang berat beban | Naikkan `timeout_seconds`, tutup aplikasi lain yang berat |
| Jawaban RIN berisi teks aneh dalam tag `<think>` | Versi Ollama lama yang tidak mendukung parameter `think` | Update Ollama ke versi terbaru; sebagai fallback, tag tetap dibersihkan otomatis oleh `ollama_client.py` |
| `Gagal memuat konfigurasi` | `config/config.json` hilang atau rusak formatnya | Pastikan file ada di `config/config.json` dan JSON valid |
| `execution of scripts is disabled` saat aktivasi venv | PowerShell execution policy default | Jalankan `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` di PowerShell Administrator |
| Error tidak terduga lainnya | Bermacam-macam | Cek detail lengkap di `logs/rin.log` |

---

## 16. Development Roadmap

```text
[x] PHASE 1  — Basic RIN CLI + Ollama + Qwen3 4B + Configuration + Logging
[ ] PHASE 2  — Configuration (lanjutan)
[ ] PHASE 3  — Personality (system prompt lengkap)
[ ] PHASE 4  — Memory (SQLite: database.py, conversation.py, long_term.py)
[ ] PHASE 5  — System information (read-only, tools/system.py)
[ ] PHASE 6  — File assistant (sandbox workspace/, tools/files.py)
[ ] PHASE 7  — Application control (tools/applications.py)
[ ] PHASE 8  — Terminal tool (tools/terminal.py)
[ ] PHASE 9  — Tool calling architecture
[ ] PHASE 10 — Security / permission layer (security/permissions.py)
[ ] PHASE 11 — Logging lanjutan (rin.log + actions.log terpisah)
[ ] PHASE 12 — GUI
[ ] PHASE 13 — Web capability
[ ] PHASE 14 — Voice interface
```

Tunggu instruksi **"LANJUT PHASE 2"** sebelum melanjutkan.
