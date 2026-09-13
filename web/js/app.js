(function () {
  "use strict";

  // ---------------------------------------------------------
  // Elements
  // ---------------------------------------------------------
  const chatArea = document.getElementById("chatArea");
  const welcomeScreen = document.getElementById("welcomeScreen");
  const messagesEl = document.getElementById("messages");
  const chatForm = document.getElementById("chatForm");
  const messageInput = document.getElementById("messageInput");
  const sendButton = document.getElementById("sendButton");
  const statusDot = document.getElementById("statusDot");
  const statusLabel = document.getElementById("statusLabel");
  const quickActions = document.getElementById("quickActions");
  const newChatButton = document.getElementById("newChatButton");
  const srStatus = document.getElementById("srStatus");
  const micButton = document.getElementById("micButton");
  const voiceToggleButton = document.getElementById("voiceToggleButton");
  const voiceStatusBar = document.getElementById("voiceStatusBar");
  const voiceStatusText = document.getElementById("voiceStatusText");
  const voiceStatusStopBtn = document.getElementById("voiceStatusStopBtn");

  let isSending = false;
  let activeController = null; // AbortController for the in-flight stream, if any

  // Raw (pre-markdown-render) text behind each assistant bubble, kept
  // so Text-to-Speech can read clean prose instead of the rendered
  // HTML or raw ```code```/**bold** syntax.
  const rawTextMap = new WeakMap();

  // PHASE 5D — client-side "chat session" id.
  //
  // LIMITATION (documented, not hidden): the backend (app/api/server.py)
  // builds exactly ONE shared Assistant instance at startup, with one
  // in-memory history and one SQLite-backed memory store. It does not
  // yet branch behaviour on `session_id` (see schemas.py: the field is
  // accepted but unused). So this id is purely a local UI concept for
  // now — it lets the frontend tell chat threads apart later without
  // requiring a backend change today, exactly per the brief. "New Chat"
  // therefore clears the on-screen conversation only; RIN's underlying
  // memory (SQLite + in-memory history) is untouched and keeps growing
  // across every chat the user starts.
  let sessionId = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());

  function announce(text) {
    if (srStatus) srStatus.textContent = text;
  }

  // ===========================================================
  // PHASE 5E — Voice interaction
  //
  // Everything here is additive and optional: RIN's text chat works
  // exactly as before if the browser supports neither API (req #16).
  // No audio is ever sent to the server — the browser's own Speech
  // Recognition turns speech into text locally, and only that text is
  // ever transmitted (req #13).
  // ===========================================================
  const SpeechRecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition || null;
  const ttsSupported = "speechSynthesis" in window;

  let recognition = null;
  let isListening = false;

  // Shared status slot for "listening" / "speaking" / short error
  // toasts, so at most one voice-related message is visible at once.
  let voiceStatusMode = null; // 'listening' | 'speaking' | 'error' | null
  let voiceStatusTimer = null;

  function showVoiceStatus(text, mode, opts) {
    opts = opts || {};
    voiceStatusMode = mode;
    voiceStatusText.textContent = text;
    voiceStatusBar.hidden = false;
    voiceStatusBar.classList.toggle("is-error", mode === "error");
    voiceStatusStopBtn.hidden = !opts.withStop;
    clearTimeout(voiceStatusTimer);
    if (opts.temporary) {
      voiceStatusTimer = setTimeout(() => {
        if (voiceStatusMode === mode) hideVoiceStatus();
      }, opts.duration || 4000);
    }
  }

  function hideVoiceStatus() {
    voiceStatusBar.hidden = true;
    voiceStatusStopBtn.hidden = true;
    voiceStatusMode = null;
    clearTimeout(voiceStatusTimer);
  }

  voiceStatusStopBtn.addEventListener("click", stopSpeaking);

  // -----------------------------------------------------------
  // Text-to-Speech
  // -----------------------------------------------------------

  // Turn RIN's raw (markdown) reply into plain speech-friendly text.
  // Simple and deliberately non-exhaustive (req #5): strips the
  // symbols so **bold**, `code`, and code fences aren't read aloud
  // literally. Fenced code blocks are summarised, not read in full.
  function toSpeechText(raw) {
    let t = raw || "";
    t = t.replace(/```[\s\S]*?```/g, " (ada cuplikan kode) ");
    t = t.replace(/```[\s\S]*$/g, " (ada cuplikan kode) "); // unclosed fence
    t = t.replace(/`([^`]+)`/g, "$1");
    t = t.replace(/\*\*([^*]+)\*\*/g, "$1");
    t = t.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1$2");
    t = t.replace(/^\s{0,3}#{1,6}\s+/gm, "");
    t = t.replace(/^\s*[-*]\s+/gm, "");
    t = t.replace(/^\s*\d+[.)]\s+/gm, "");
    t = t.replace(/[ \t]+/g, " ").replace(/\n{2,}/g, ". ").replace(/\n/g, " ").trim();
    return t;
  }

  function pickIndonesianVoice() {
    if (!ttsSupported) return null;
    const voices = window.speechSynthesis.getVoices() || [];
    return voices.find((v) => v.lang && v.lang.toLowerCase().startsWith("id")) || null;
  }

  let currentSpeakButton = null;

  function onSpeechEnded() {
    document.body.classList.remove("rin-speaking");
    if (currentSpeakButton) {
      currentSpeakButton.classList.remove("speaking");
      currentSpeakButton.setAttribute("aria-label", "Bacakan pesan ini");
    }
    currentSpeakButton = null;
    if (voiceStatusMode === "speaking") hideVoiceStatus();
  }

  // Reads `rawText` aloud. `button`, if given, is the per-message 🔊
  // button that should visually reflect "currently speaking" and
  // toggle back when done (req #9). Only one utterance ever plays at
  // a time (req #4) — any previous one is cancelled first.
  function speakRin(rawText, button) {
    if (!ttsSupported) {
      showVoiceStatus("Browser ini belum mendukung pembacaan suara RIN.", "error", { temporary: true });
      return;
    }
    const plain = toSpeechText(rawText);
    if (!plain) return;

    window.speechSynthesis.cancel();

    const utter = new SpeechSynthesisUtterance(plain);
    utter.lang = "id-ID";
    const voice = pickIndonesianVoice();
    if (voice) utter.voice = voice; // else: let the browser pick its own default

    utter.onstart = () => {
      document.body.classList.add("rin-speaking");
      currentSpeakButton = button || null;
      if (button) {
        button.classList.add("speaking");
        button.setAttribute("aria-label", "Hentikan pembacaan");
      }
      showVoiceStatus("🔊 RIN sedang berbicara...", "speaking", { withStop: true });
    };
    utter.onend = onSpeechEnded;
    utter.onerror = () => {
      onSpeechEnded();
      showVoiceStatus("Terjadi masalah saat membacakan jawaban RIN.", "error", { temporary: true });
    };

    window.speechSynthesis.speak(utter);
  }

  function stopSpeaking() {
    if (ttsSupported) window.speechSynthesis.cancel();
    onSpeechEnded();
  }

  function addSpeakButtonToMessage(bubbleEl, rawText) {
    if (!ttsSupported) return null;
    const col = bubbleEl.parentElement;
    if (!col) return null;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "speak-button";
    btn.setAttribute("aria-label", "Bacakan pesan ini");
    btn.title = "Bacakan pesan ini";
    btn.textContent = "🔊";
    btn.addEventListener("click", () => {
      if (btn.classList.contains("speaking")) {
        stopSpeaking();
      } else {
        speakRin(rawTextMap.get(bubbleEl) || rawText, btn);
      }
    });
    col.appendChild(btn);
    return btn;
  }

  // Auto-speak ("🔊 Voice" toggle). OFF by default per the brief;
  // persisted locally purely as a UX nicety, never sent anywhere.
  let autoVoiceEnabled = ttsSupported && localStorage.getItem("rinVoiceEnabled") === "1";

  function updateVoiceToggleUI() {
    voiceToggleButton.classList.toggle("active", autoVoiceEnabled);
    voiceToggleButton.setAttribute("aria-pressed", String(autoVoiceEnabled));
    voiceToggleButton.textContent = autoVoiceEnabled ? "🔊" : "🔇";
    voiceToggleButton.setAttribute(
      "aria-label",
      autoVoiceEnabled ? "Voice otomatis: aktif" : "Voice otomatis: mati"
    );
    voiceToggleButton.title = autoVoiceEnabled
      ? "Voice: ON (jawaban RIN otomatis dibacakan)"
      : "Voice: OFF (jawaban RIN tidak dibacakan otomatis)";
  }

  if (!ttsSupported) {
    voiceToggleButton.disabled = true;
    voiceToggleButton.title = "Browser ini belum mendukung pembacaan suara RIN.";
    voiceToggleButton.setAttribute("aria-label", "Voice otomatis tidak tersedia di browser ini");
    voiceToggleButton.textContent = "🔇";
  } else {
    updateVoiceToggleUI();
    voiceToggleButton.addEventListener("click", () => {
      autoVoiceEnabled = !autoVoiceEnabled;
      localStorage.setItem("rinVoiceEnabled", autoVoiceEnabled ? "1" : "0");
      updateVoiceToggleUI();
    });
  }

  // -----------------------------------------------------------
  // Speech-to-Text (voice input)
  // -----------------------------------------------------------
  if (!SpeechRecognitionImpl) {
    micButton.classList.add("unsupported");
  }

  function initRecognitionIfNeeded() {
    if (recognition || !SpeechRecognitionImpl) return;

    recognition = new SpeechRecognitionImpl();
    recognition.lang = "id-ID";
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onstart = () => {
      isListening = true;
      micButton.classList.add("listening");
      micButton.setAttribute("aria-label", "Berhenti mendengarkan");
      showVoiceStatus("🔴 Mendengarkan...", "listening");
    };

    recognition.onresult = (event) => {
      let interim = "";
      let final = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) final += transcript;
        else interim += transcript;
      }

      if (final.trim()) {
        // Final result goes straight into the input — never auto-sent,
        // the user can still edit before pressing Send (req #1).
        const existing = messageInput.value.trim();
        messageInput.value = existing ? existing + " " + final.trim() : final.trim();
        autoResizeInput();
        updateSendButtonState();
      } else if (interim.trim()) {
        showVoiceStatus('🔴 Mendengarkan... "' + interim.trim() + '"', "listening");
      }
    };

    recognition.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "permission-denied") {
        showVoiceStatus(
          "RIN tidak mendapatkan izin microphone. Silakan izinkan microphone di pengaturan browser.",
          "error",
          { temporary: true, duration: 6000 }
        );
      } else if (event.error === "no-speech" || event.error === "aborted") {
        // Benign — user simply didn't say anything or stopped early.
        if (voiceStatusMode === "listening") hideVoiceStatus();
      } else {
        showVoiceStatus("Terjadi masalah pada input suara RIN.", "error", { temporary: true });
      }
    };

    recognition.onend = () => {
      isListening = false;
      micButton.classList.remove("listening");
      micButton.setAttribute("aria-label", "Mulai input suara");
      if (voiceStatusMode === "listening") hideVoiceStatus();
    };
  }

  micButton.addEventListener("click", () => {
    if (!SpeechRecognitionImpl) {
      showVoiceStatus("Browser ini belum mendukung input suara RIN.", "error", { temporary: true, duration: 5000 });
      return;
    }
    initRecognitionIfNeeded();
    if (isListening) {
      recognition.stop();
      return;
    }
    try {
      recognition.start();
    } catch (err) {
      showVoiceStatus("Tidak dapat memulai input suara RIN.", "error", { temporary: true });
    }
  });

  // ---------------------------------------------------------
  // Minimal Markdown renderer (self-contained, no CDN dependency
  // so RIN keeps working fully offline on the local network).
  // Supports: headings, code blocks, inline code, bold, italic,
  // bullet lists, numbered lists, paragraphs.
  // ---------------------------------------------------------
  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function renderInline(text) {
    let out = escapeHtml(text);
    out = out.replace(/`([^`]+?)`/g, (m, code) => `<code>${code}</code>`);
    out = out.replace(/\*\*([^*]+?)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/(^|[^*])\*([^*\n]+?)\*(?!\*)/g, "$1<em>$2</em>");
    return out;
  }

  function renderMarkdown(raw) {
    const text = raw || "";
    const blocks = text.split(/```/);
    let html = "";

    for (let i = 0; i < blocks.length; i++) {
      const block = blocks[i];
      if (i % 2 === 1) {
        let content = block;
        const firstNewline = content.indexOf("\n");
        if (firstNewline !== -1 && content.slice(0, firstNewline).trim().length < 20) {
          content = content.slice(firstNewline + 1);
        }
        html += `<pre><code>${escapeHtml(content.replace(/\n$/, ""))}</code></pre>`;
        continue;
      }

      const lines = block.split("\n");
      let i2 = 0;
      let paragraphBuf = [];

      const flushParagraph = () => {
        if (paragraphBuf.length) {
          const joined = paragraphBuf.join(" ").trim();
          if (joined) html += `<p>${renderInline(joined)}</p>`;
          paragraphBuf = [];
        }
      };

      while (i2 < lines.length) {
        const line = lines[i2];

        if (/^\s*$/.test(line)) {
          flushParagraph();
          i2++;
          continue;
        }

        const headingMatch = line.match(/^\s*(#{1,6})\s+(.*)$/);
        if (headingMatch) {
          flushParagraph();
          const level = Math.min(headingMatch[1].length, 6);
          html += `<h${level}>${renderInline(headingMatch[2].trim())}</h${level}>`;
          i2++;
          continue;
        }

        if (/^\s*[-*]\s+/.test(line)) {
          flushParagraph();
          const items = [];
          while (i2 < lines.length && /^\s*[-*]\s+/.test(lines[i2])) {
            items.push(lines[i2].replace(/^\s*[-*]\s+/, ""));
            i2++;
          }
          html += "<ul>" + items.map((it) => `<li>${renderInline(it)}</li>`).join("") + "</ul>";
          continue;
        }

        if (/^\s*\d+[.)]\s+/.test(line)) {
          flushParagraph();
          const items = [];
          while (i2 < lines.length && /^\s*\d+[.)]\s+/.test(lines[i2])) {
            items.push(lines[i2].replace(/^\s*\d+[.)]\s+/, ""));
            i2++;
          }
          html += "<ol>" + items.map((it) => `<li>${renderInline(it)}</li>`).join("") + "</ol>";
          continue;
        }

        paragraphBuf.push(line.trim());
        i2++;
      }
      flushParagraph();
    }

    return html;
  }

  // ---------------------------------------------------------
  // Safety net: strip any accidental thinking/reasoning content
  // or Ollama metadata that might slip through, even though the
  // backend (Assistant.ask_stream) already filters <think> tags.
  // This is a defensive second layer on the frontend only.
  // ---------------------------------------------------------
  function stripThinking(text) {
    if (!text) return text;
    let out = text;
    out = out.replace(/<think>[\s\S]*?<\/think>/gi, "");
    out = out.replace(/<reasoning>[\s\S]*?<\/reasoning>/gi, "");
    // Unclosed opening tag still streaming in — hide until it closes.
    out = out.replace(/<think>[\s\S]*$/gi, "");
    out = out.replace(/<reasoning>[\s\S]*$/gi, "");
    return out;
  }

  // ---------------------------------------------------------
  // Health check — polls GET /api/health for real status.
  // ---------------------------------------------------------
  async function checkHealth() {
    try {
      const res = await fetch("/api/health");
      if (!res.ok) throw new Error("bad status");
      await res.json();
      statusDot.className = "status-dot online";
      statusLabel.textContent = "Online";
    } catch (err) {
      statusDot.className = "status-dot offline";
      statusLabel.textContent = "Offline";
    }
  }

  checkHealth();
  setInterval(checkHealth, 15000);

  // ---------------------------------------------------------
  // Message rendering helpers
  // ---------------------------------------------------------
  function hideWelcome() {
    if (welcomeScreen && welcomeScreen.parentNode) {
      welcomeScreen.style.display = "none";
    }
  }

  // Auto-scroll, but don't yank the view away if the user has scrolled
  // up to read earlier messages. `autoScrollEnabled` tracks whether the
  // user is currently near the bottom of the chat.
  let autoScrollEnabled = true;
  const NEAR_BOTTOM_PX = 96;

  chatArea.addEventListener("scroll", () => {
    const distanceFromBottom =
      chatArea.scrollHeight - chatArea.scrollTop - chatArea.clientHeight;
    autoScrollEnabled = distanceFromBottom < NEAR_BOTTOM_PX;
  });

  function scrollToBottom(force) {
    if (force) autoScrollEnabled = true;
    if (autoScrollEnabled) {
      chatArea.scrollTop = chatArea.scrollHeight;
    }
  }

  function addUserMessage(text) {
    const row = document.createElement("div");
    row.className = "message-row user";

    const col = document.createElement("div");
    col.className = "message-col";

    const label = document.createElement("div");
    label.className = "sender-label";
    label.textContent = "Anda";

    const bubble = document.createElement("div");
    bubble.className = "bubble user";
    bubble.textContent = text;

    col.appendChild(label);
    col.appendChild(bubble);
    row.appendChild(col);
    messagesEl.appendChild(row);
    // The user just acted — always snap to their own new message.
    scrollToBottom(true);
  }

  function typingIndicatorHtml() {
    return (
      '<span class="typing-indicator">' +
      '<span class="dots"><span></span><span></span><span></span></span>' +
      "RIN sedang mengetik...</span>"
    );
  }

  function addAssistantPlaceholder() {
    const row = document.createElement("div");
    row.className = "message-row assistant";

    const avatar = document.createElement("div");
    avatar.className = "avatar";

    const avatarImg = document.createElement("img");
    avatarImg.src = "/assets/rin-icon.png";
    avatarImg.alt = "RIN";

    avatar.appendChild(avatarImg);

    const col = document.createElement("div");
    col.className = "message-col";

    const label = document.createElement("div");
    label.className = "sender-label";
    label.textContent = "RIN";

    const bubble = document.createElement("div");
    bubble.className = "bubble assistant";
    bubble.innerHTML = typingIndicatorHtml();

    col.appendChild(label);
    col.appendChild(bubble);
    row.appendChild(avatar);
    row.appendChild(col);
    messagesEl.appendChild(row);
    scrollToBottom();
    return bubble;
  }

  function setAssistantContent(bubbleEl, text) {
    rawTextMap.set(bubbleEl, text);
    bubbleEl.innerHTML = renderMarkdown(stripThinking(text));
    scrollToBottom();
  }

  function setAssistantError(bubbleEl, message, onRetry) {
    bubbleEl.classList.add("error");
    bubbleEl.innerHTML = "";

    const msgEl = document.createElement("div");
    msgEl.textContent = message;
    bubbleEl.appendChild(msgEl);

    if (onRetry) {
      const retryBtn = document.createElement("button");
      retryBtn.type = "button";
      retryBtn.className = "retry-button";
      retryBtn.textContent = "Coba lagi";
      retryBtn.addEventListener("click", () => {
        retryBtn.disabled = true;
        onRetry();
      });
      bubbleEl.appendChild(retryBtn);
    }

    scrollToBottom();
  }

  // ---------------------------------------------------------
  // Error message mapping — distinct, friendly messages depending
  // on what actually failed, without ever exposing a traceback.
  // ---------------------------------------------------------
  function friendlyErrorForStatus(status) {
    // Backend (routes.py) maps Ollama-side failures to these codes:
    // 503 connection error, 504 timeout, 404 model not found,
    // 502 bad response from Ollama.
    if (status === 503 || status === 504 || status === 404 || status === 502) {
      return "RIN tidak dapat terhubung ke mesin AI.";
    }
    return "Maaf, terjadi masalah saat memproses pesan.";
  }

  // ---------------------------------------------------------
  // Sending messages (streaming via POST /api/chat/stream)
  // ---------------------------------------------------------
  function setSendingState(sending) {
    isSending = sending;
    sendButton.classList.toggle("loading", sending);
    sendButton.setAttribute("aria-label", sending ? "Hentikan respons" : "Kirim pesan");
    // Lock the input while a response is in flight (req #8); it's
    // re-enabled here for every exit path (done / error / stop) since
    // this always runs via sendMessage()'s finally block or stopGeneration().
    messageInput.disabled = sending;
    updateSendButtonState();
  }

  async function sendMessage(text) {
    if (isSending) return;
    const trimmed = text.trim();
    if (!trimmed) return;

    setSendingState(true);
    hideWelcome();
    addUserMessage(trimmed);

    messageInput.value = "";
    autoResizeInput();

    const bubble = addAssistantPlaceholder();
    let accumulated = "";
    let receivedAny = false;

    const controller = new AbortController();
    activeController = controller;

    const retry = () => {
      bubble.classList.remove("error");
      bubble.innerHTML = typingIndicatorHtml();
      setSendingState(false);
      sendMessage(trimmed);
    };

    announce("RIN sedang mengetik...");

    try {
      const res = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // `session_id` is sent for forward-compatibility only — the
        // current backend accepts and ignores it (see schemas.py).
        // It has no effect on memory/session behaviour today.
        body: JSON.stringify({ message: trimmed, session_id: sessionId }),
        signal: controller.signal,
      });

      if (!res.ok) {
        setAssistantError(bubble, friendlyErrorForStatus(res.status), retry);
        announce("Terjadi kesalahan saat menghubungi RIN.");
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        if (chunk) {
          receivedAny = true;
          accumulated += chunk;
          setAssistantContent(bubble, accumulated);
        }
      }

      if (!receivedAny) {
        setAssistantError(bubble, "Maaf, terjadi masalah saat memproses pesan.", retry);
        announce("Terjadi kesalahan saat menghubungi RIN.");
      } else {
        announce("RIN telah membalas.");
        // Streaming is done — attach the per-message speak button now
        // (req #9), and read the FINAL text once, never per chunk
        // (req #10). Whichever button is relevant (this message's, if
        // auto-voice is on) reflects the "currently speaking" state.
        const speakBtn = addSpeakButtonToMessage(bubble, accumulated);
        if (autoVoiceEnabled && ttsSupported) {
          speakRin(accumulated, speakBtn);
        }
      }
    } catch (err) {
      if (err && err.name === "AbortError") {
        // User pressed Stop. Keep whatever text already arrived intact
        // (req #3: "jangan merusak UI, jangan membuat chat state kacau").
        // If nothing had arrived yet, replace the typing indicator with
        // a small neutral note instead of leaving it spinning forever.
        if (!receivedAny) {
          bubble.innerHTML = '<span class="stopped-note">Dihentikan.</span>';
        } else {
          // Partial reply is still worth letting the user hear back
          // manually — just never auto-read a response that was cut short.
          addSpeakButtonToMessage(bubble, accumulated);
        }
        announce("Respons dihentikan.");
      } else {
        // fetch() itself threw: FastAPI server tidak dapat dihubungi sama sekali.
        setAssistantError(bubble, "RIN sedang tidak dapat terhubung ke server.", retry);
        announce("RIN sedang tidak dapat terhubung ke server.");
      }
    } finally {
      if (activeController === controller) activeController = null;
      setSendingState(false);
    }
  }

  function stopGeneration() {
    if (!isSending || !activeController) return;
    activeController.abort();
  }

  // ---------------------------------------------------------
  // New Chat
  //
  // Clears the on-screen conversation and starts a fresh local
  // session id. Per the brief: no backend change was made, so RIN's
  // actual memory (in-memory history + SQLite in app/core/memory.py /
  // app/memory/database.py) is shared across every chat and is NOT
  // reset by this button — only the visible thread is.
  // ---------------------------------------------------------
  function newChat() {
    if (isSending) stopGeneration();
    stopSpeaking();

    messagesEl.innerHTML = "";
    if (welcomeScreen) welcomeScreen.style.display = "";
    messageInput.value = "";
    autoResizeInput();
    autoScrollEnabled = true;
    sessionId = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());

    announce("Chat baru dimulai. Memori RIN di server tetap tersimpan.");
    messageInput.focus();
  }

  newChatButton.addEventListener("click", newChat);

  // ---------------------------------------------------------
  // Input handling
  // ---------------------------------------------------------
  function autoResizeInput() {
    messageInput.style.height = "auto";
    messageInput.style.height = Math.min(messageInput.scrollHeight, 140) + "px";
  }

  function updateSendButtonState() {
    // While sending, the button stays enabled so it can act as Stop.
    sendButton.disabled = isSending ? false : messageInput.value.trim().length === 0;
  }

  messageInput.addEventListener("input", () => {
    autoResizeInput();
    updateSendButtonState();
  });

  messageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      chatForm.requestSubmit();
    }
  });

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    if (isSending) {
      stopGeneration();
      return;
    }
    const text = messageInput.value;
    if (!text.trim()) return;
    sendMessage(text);
  });

  quickActions.addEventListener("click", (e) => {
    const btn = e.target.closest(".quick-action");
    if (!btn) return;
    const prompt = btn.getAttribute("data-prompt");
    if (prompt) sendMessage(prompt);
  });

  updateSendButtonState();
})();