"""
app.api

Layer FastAPI RIN (PHASE 5A).

Package ini HANYA berisi wiring HTTP (server, routes, schemas). Semua
logic percakapan/Ollama tetap ada di app.core.assistant dan
app.llm.ollama_client; tidak ada logic Ollama baru di sini.
"""
