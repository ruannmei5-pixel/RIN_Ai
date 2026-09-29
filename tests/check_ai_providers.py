import sys, os, json, threading
sys.path.insert(0, '.venv/Lib/site-packages'); sys.path.insert(0, '.')
import types
fake=types.ModuleType('ollama')
class _E(Exception): pass
class _C:
    def __init__(self,**k): pass
fake.Client=_C; fake.ResponseError=_E
sys.modules['ollama']=fake
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        if self.headers.get("Authorization")!="Bearer good": self.send_response(401); self.end_headers(); return
        b=json.dumps({"data":[{"id":"m1"},{"id":"m2"}]}).encode(); self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        n=int(self.headers["Content-Length"]); body=json.loads(self.rfile.read(n))
        if self.headers.get("Authorization")!="Bearer good": self.send_response(401); self.end_headers(); self.wfile.write(b'{"e":"bad good"}'); return
        if body["model"]=="boom": self.send_response(503); self.end_headers(); return
        if body["stream"]:
            self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.end_headers()
            for t in ["Hai ","dunia"]:
                self.wfile.write(("data: "+json.dumps({"choices":[{"delta":{"content":t}}]})+"\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            b=json.dumps({"choices":[{"message":{"content":"halo "+body["model"]}}]}).encode(); self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(b)
srv=HTTPServer(("127.0.0.1",0),H); port=srv.server_port
threading.Thread(target=srv.serve_forever,daemon=True).start()
base=f"http://127.0.0.1:{port}/v1"

from app.core.config import AppConfig, OllamaConfig, AIRouterConfig, NvidiaConfig, OpenRouterConfig
from app.llm.base import ChatMessage, ProviderError, ProviderAuthError, ProviderNotConfiguredError
from app.llm.router import AIProviderRouter
from app.llm import ollama_client as oc

oc.OllamaClient.chat=lambda self,m,model=None:"dari ollama"
oc.OllamaClient.chat_stream=lambda self,m,model=None:iter(["ol","lama"])

def mk(nkey="good", fb=True, nmodel="m1"):
    cfg=AppConfig("RIN","R","id",OllamaConfig("http://localhost:1","qwen3:4b"),
        ai=AIRouterConfig("nvidia",fb,"ollama"),
        nvidia=NvidiaConfig(nkey,base,nmodel),
        openrouter=OpenRouterConfig("",base,""))
    return AIProviderRouter(cfg)
msgs=[ChatMessage("user","hi")]
r=mk()
print("chat", r.chat(msgs)[0:2][0], r.chat(msgs)[1])
print("override model", r.chat(msgs,model="m2")[0])
s,o=r.chat_stream(msgs); print("stream", "".join(s), o)
print("models", r.get("nvidia").get_models(), "health", r.get("nvidia").health_check())
r=mk(nkey="bad"); print("badkey->fallback", r.chat(msgs)); s,o=r.chat_stream(msgs); print("stream fb","".join(s),o)
print("health bad", r.get("nvidia").health_check())
r=mk(nkey=""); print("unconfigured->fallback", r.chat(msgs)[1]); print("openrouter health", r.get("openrouter").health_check())
r=mk(nmodel="boom"); print("503->fallback", r.chat(msgs)[1])
r=mk(nkey="bad",fb=False)
try: r.chat(msgs)
except ProviderAuthError as e: print("no fallback raises:", e, "| key leaked:", "bad" in str(e).replace("bad ","",0) and "Bearer" in str(e))
r=mk(fb=True); r.config.ai.provider="ollama"; print("ollama direct", r.chat(msgs)[1])
r.config.ai.fallback_provider="nvidia"
