/**
 * settings.js
 *
 * Settings workspace panel.
 *
 * Persists to localStorage under `rin_settings` (via storage.js) and
 * applies what it can apply by itself (compact mode). For everything
 * that actually needs to change chat/voice/AI behaviour, this file
 * cannot reach into app.js (not part of this change), so it exposes
 * `window.RinSettings.get()/getAll()` and fires a `rin:settings-changed`
 * CustomEvent on every change. app.js needs to read from these to
 * actually honour "Enter to send", "Auto scroll", "Auto speak", the
 * chosen model, and temperature — see the notes below each field.
 *
 * Data shape:
 *   {
 *     compactMode, chatEnterToSend, chatShowTimestamps, chatAutoScroll,
 *     voiceEnabled, voiceAutoSpeak, aiModel, aiTemperature
 *   }
 */
(function () {
  "use strict";

  const STORAGE_KEY = "rin_settings";
  const DEFAULTS = {
    compactMode: false,
    chatEnterToSend: true,
    chatShowTimestamps: false,
    chatAutoScroll: true,
    voiceEnabled: false,
    voiceAutoSpeak: false,
    aiModel: "",
    aiTemperature: 0.7,
  };

  const els = {
    compactMode: document.getElementById("settingCompactMode"),
    enterToSend: document.getElementById("settingEnterToSend"),
    showTimestamps: document.getElementById("settingShowTimestamps"),
    autoScroll: document.getElementById("settingAutoScroll"),
    voiceEnabled: document.getElementById("settingVoiceEnabled"),
    autoSpeak: document.getElementById("settingAutoSpeak"),
    aiModel: document.getElementById("settingAiModel"),
    aiTemperature: document.getElementById("settingAiTemperature"),
    aiTemperatureValue: document.getElementById("settingTemperatureValue"),
    backendDot: document.getElementById("settingBackendDot"),
    backendLabel: document.getElementById("settingBackendLabel"),
    ollamaStatus: document.getElementById("settingOllamaStatus"),
    webSearchStatus: document.getElementById("settingWebSearchStatus"),
  };

  // Settings markup not present in this build (e.g. older index.html) —
  // nothing to wire up, bail out quietly like schedule.js/projects.js do.
  if (!els.compactMode && !els.enterToSend && !els.aiModel) return;

  let settings = loadSettings();

  function loadSettings() {
    const stored = window.RinStorage.get(STORAGE_KEY, {});
    return Object.assign({}, DEFAULTS, stored && typeof stored === "object" ? stored : {});
  }

  function persist() {
    window.RinStorage.set(STORAGE_KEY, settings);
    document.body.classList.toggle("compact", !!settings.compactMode);
    window.dispatchEvent(new CustomEvent("rin:settings-changed", { detail: { settings: getAll() } }));
  }

  function set(key, value) {
    settings[key] = value;
    persist();
  }

  function getAll() {
    return Object.assign({}, settings);
  }

  function applyToForm() {
    if (els.compactMode) els.compactMode.checked = !!settings.compactMode;
    if (els.enterToSend) els.enterToSend.checked = !!settings.chatEnterToSend;
    if (els.showTimestamps) els.showTimestamps.checked = !!settings.chatShowTimestamps;
    if (els.autoScroll) els.autoScroll.checked = !!settings.chatAutoScroll;
    if (els.voiceEnabled) els.voiceEnabled.checked = !!settings.voiceEnabled;
    if (els.autoSpeak) els.autoSpeak.checked = !!settings.voiceAutoSpeak;
    if (els.aiModel) els.aiModel.value = settings.aiModel || "";
    if (els.aiTemperature) els.aiTemperature.value = settings.aiTemperature;
    if (els.aiTemperatureValue) els.aiTemperatureValue.textContent = Number(settings.aiTemperature).toFixed(1);
    document.body.classList.toggle("compact", !!settings.compactMode);
  }

  // ---------------------------------------------------------
  // Wiring — each of these actually persists. Whether it actually
  // changes behaviour elsewhere depends on app.js reading it (noted
  // per field below).
  // ---------------------------------------------------------

  // Applies immediately by itself: toggles `.compact` on <body>.
  // Needs matching `.compact` CSS rules (not included — no style.css
  // was provided) to have a visible effect.
  if (els.compactMode) {
    els.compactMode.addEventListener("change", () => set("compactMode", els.compactMode.checked));
  }

  // app.js needs to check RinSettings.get('chatEnterToSend') in its
  // textarea keydown handler for this to actually change send behaviour.
  if (els.enterToSend) {
    els.enterToSend.addEventListener("change", () => set("chatEnterToSend", els.enterToSend.checked));
  }

  // app.js needs to check this when rendering each chat message.
  if (els.showTimestamps) {
    els.showTimestamps.addEventListener("change", () => set("chatShowTimestamps", els.showTimestamps.checked));
  }

  // app.js needs to check this before it force-scrolls on new chunks.
  if (els.autoScroll) {
    els.autoScroll.addEventListener("change", () => set("chatAutoScroll", els.autoScroll.checked));
  }

  // app.js needs to check this to show/hide the mic button + voice controls.
  if (els.voiceEnabled) {
    els.voiceEnabled.addEventListener("change", () => set("voiceEnabled", els.voiceEnabled.checked));
  }

  // This mirrors the same intent as the 🔇/🔊 button in the Chat header
  // (voiceToggleButton in app.js) — it does NOT currently sync with it,
  // since app.js wasn't part of this change. Treat this as the default
  // to read on load; keep them in sync in app.js if you want one source
  // of truth.
  if (els.autoSpeak) {
    els.autoSpeak.addEventListener("change", () => set("voiceAutoSpeak", els.autoSpeak.checked));
  }

  // app.js needs to send this as the `model` field in its chat request
  // payload for it to actually switch models.
  if (els.aiModel) {
    els.aiModel.addEventListener("change", () => set("aiModel", els.aiModel.value.trim()));
  }

  // app.js needs to send this as the `temperature` field in its chat
  // request payload for it to actually take effect.
  if (els.aiTemperature) {
    els.aiTemperature.addEventListener("input", () => {
      const v = parseFloat(els.aiTemperature.value);
      if (els.aiTemperatureValue) els.aiTemperatureValue.textContent = v.toFixed(1);
      set("aiTemperature", v);
    });
  }

  // ---------------------------------------------------------
  // Connection status
  // ---------------------------------------------------------

  // Mirror the overall backend status app.js already maintains on
  // #statusDot / #statusLabel — same pattern workspace.js uses for
  // the sidebar status card. This is real, not hardcoded.
  const headerDot = document.getElementById("statusDot");
  const headerLabel = document.getElementById("statusLabel");
  if (headerDot && headerLabel && els.backendDot && els.backendLabel) {
    const mirror = function () {
      els.backendDot.className = headerDot.className;
      els.backendLabel.textContent = headerLabel.textContent;
    };
    const observer = new MutationObserver(mirror);
    observer.observe(headerDot, { attributes: true, attributeFilter: ["class"] });
    observer.observe(headerLabel, { childList: true, characterData: true, subtree: true });
    mirror();
  }

  // Ollama / Web search: unlike overall backend status, there's no
  // confirmed endpoint exposing per-service state for this build. We
  // try a couple of common /health response shapes; if none match we
  // leave the honest "Tidak diketahui" label already in the HTML
  // rather than hardcoding "Connected".
  function loadServiceDetail() {
    fetch("/health")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data || typeof data !== "object") return;
        const ollama = data.ollama_status || data.ollama || (data.services && data.services.ollama);
        const webSearch =
          data.web_search_status || data.web_search || data.tavily || (data.services && data.services.web_search);
        if (els.ollamaStatus && ollama) els.ollamaStatus.textContent = String(ollama);
        if (els.webSearchStatus && webSearch) els.webSearchStatus.textContent = String(webSearch);
      })
      .catch(() => {
        /* leave the honest fallback text in place */
      });
  }

  applyToForm();
  loadServiceDetail();

  window.RinSettings = {
    get: function (key) {
      return settings[key];
    },
    getAll: getAll,
    set: set,
  };
})();
