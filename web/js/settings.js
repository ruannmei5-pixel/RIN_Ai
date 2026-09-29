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
 * chosen provider/model, and temperature — see the notes below each field.
 *
 * TAHAP 3 — MULTI AI PROVIDER:
 * `aiProvider`/`aiModel` are now populated from the REAL backend
 * (GET /api/ai/providers, GET /api/ai/models?provider=...) instead of
 * being a free-text Ollama-only field. app.js reads
 * RinSettings.get('aiProvider') / RinSettings.get('aiModel') and sends
 * them as `provider`/`model` in the /api/chat/stream request body
 * (both optional — empty means "use server default").
 *
 * Data shape:
 *   {
 *     compactMode, chatEnterToSend, chatShowTimestamps, chatAutoScroll,
 *     voiceEnabled, voiceAutoSpeak, aiProvider, aiModel, aiTemperature
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
    aiProvider: "",
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
    aiProvider: document.getElementById("settingAiProvider"),
    aiModel: document.getElementById("settingAiModel"),
    aiTemperature: document.getElementById("settingAiTemperature"),
    aiTemperatureValue: document.getElementById("settingTemperatureValue"),
    aiFallbackEnabled: document.getElementById("settingAiFallbackEnabled"),
    aiFallbackProvider: document.getElementById("settingAiFallbackProvider"),
    backendDot: document.getElementById("settingBackendDot"),
    backendLabel: document.getElementById("settingBackendLabel"),
    ollamaStatus: document.getElementById("settingOllamaStatus"),
    nvidiaStatus: document.getElementById("settingNvidiaStatus"),
    openRouterStatus: document.getElementById("settingOpenRouterStatus"),
    webSearchStatus: document.getElementById("settingWebSearchStatus"),
  };

  const PROVIDER_LABELS = { ollama: "Ollama", nvidia: "NVIDIA AI", openrouter: "OpenRouter" };

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
    if (els.aiProvider && settings.aiProvider) els.aiProvider.value = settings.aiProvider;
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
  if (els.compactMode) {
    els.compactMode.addEventListener("change", () => set("compactMode", els.compactMode.checked));
  }

  if (els.enterToSend) {
    els.enterToSend.addEventListener("change", () => set("chatEnterToSend", els.enterToSend.checked));
  }

  if (els.showTimestamps) {
    els.showTimestamps.addEventListener("change", () => set("chatShowTimestamps", els.showTimestamps.checked));
  }

  if (els.autoScroll) {
    els.autoScroll.addEventListener("change", () => set("chatAutoScroll", els.autoScroll.checked));
  }

  if (els.voiceEnabled) {
    els.voiceEnabled.addEventListener("change", () => set("voiceEnabled", els.voiceEnabled.checked));
  }

  if (els.autoSpeak) {
    els.autoSpeak.addEventListener("change", () => set("voiceAutoSpeak", els.autoSpeak.checked));
  }

  // TAHAP 3: provider berubah -> muat ulang daftar model UNTUK provider
  // itu (dynamic model discovery lewat GET /api/ai/models), lalu
  // persist pilihan provider. Model lama di-reset karena kemungkinan
  // tidak valid untuk provider baru.
  if (els.aiProvider) {
    els.aiProvider.addEventListener("change", () => {
      const providerId = els.aiProvider.value;
      set("aiProvider", providerId);
      set("aiModel", "");
      loadModelsForProvider(providerId);
    });
  }

  // app.js needs to send this as the `model` field in its chat request
  // payload for it to actually switch models.
  if (els.aiModel) {
    els.aiModel.addEventListener("change", () => set("aiModel", els.aiModel.value));
  }

  if (els.aiTemperature) {
    els.aiTemperature.addEventListener("input", () => {
      const v = parseFloat(els.aiTemperature.value);
      if (els.aiTemperatureValue) els.aiTemperatureValue.textContent = v.toFixed(1);
      set("aiTemperature", v);
    });
  }

  // ---------------------------------------------------------
  // AI Provider discovery (TAHAP 3)
  // ---------------------------------------------------------
  //
  // Fallback (AI_FALLBACK_ENABLED / AI_FALLBACK_PROVIDER) dikontrol
  // lewat environment variable backend (lihat .env.example), BUKAN
  // per-request dari frontend. Kontrol di bawah karena itu bersifat
  // read-only: menampilkan konfigurasi server apa adanya, tidak pernah
  // mengklaim bisa diubah dari sini.

  function statusPillText(info) {
    if (!info.configured) return "Belum dikonfigurasi";
    return info.available ? "Terhubung" : "Tidak dapat dihubungi";
  }

  function loadProviders() {
    fetch("/api/ai/providers")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data || !Array.isArray(data.providers)) return;

        data.providers.forEach((info) => {
          const pillMap = { ollama: els.ollamaStatus, nvidia: els.nvidiaStatus, openrouter: els.openRouterStatus };
          const pill = pillMap[info.id];
          if (pill) pill.textContent = statusPillText(info);
        });

        // Pilih provider default dari settings tersimpan, atau dari
        // AI_PROVIDER server jika user belum pernah memilih.
        if (els.aiProvider && !settings.aiProvider) {
          const defaultProvider = data.providers.find((p) => p.is_default);
          if (defaultProvider) {
            settings.aiProvider = defaultProvider.id;
            els.aiProvider.value = defaultProvider.id;
          }
        }

        if (els.aiFallbackEnabled) {
          els.aiFallbackEnabled.checked = !!data.fallback_enabled;
          els.aiFallbackEnabled.disabled = true; // read-only, diatur via env
        }
        if (els.aiFallbackProvider) {
          const fallbackProvider = data.providers.find((p) => p.is_fallback);
          if (fallbackProvider) els.aiFallbackProvider.value = fallbackProvider.id;
          els.aiFallbackProvider.disabled = true; // read-only, diatur via env
        }

        loadModelsForProvider(settings.aiProvider || (els.aiProvider ? els.aiProvider.value : "ollama"));
      })
      .catch(() => {
        /* leave the honest "Tidak diketahui" pill text in place */
      });
  }

  function loadModelsForProvider(providerId) {
    if (!els.aiModel || !providerId) return;

    fetch("/api/ai/models?provider=" + encodeURIComponent(providerId))
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        els.aiModel.innerHTML = "";

        const defaultOption = document.createElement("option");
        defaultOption.value = "";
        defaultOption.textContent = "(default server)";
        els.aiModel.appendChild(defaultOption);

        const models = data && Array.isArray(data.models) ? data.models : [];
        models.forEach((modelName) => {
          if (!modelName) return;
          const opt = document.createElement("option");
          opt.value = modelName;
          opt.textContent = modelName;
          els.aiModel.appendChild(opt);
        });

        if (settings.aiModel && models.indexOf(settings.aiModel) !== -1) {
          els.aiModel.value = settings.aiModel;
        } else {
          els.aiModel.value = "";
        }
      })
      .catch(() => {
        /* leave whatever options already exist */
      });
  }

  // ---------------------------------------------------------
  // Connection status
  // ---------------------------------------------------------

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

  // Web search: status NYATA dari GET /api/plugins (Tool Registry +
  // connections, sudah ada — bukan endpoint baru).
  function loadWebSearchStatus() {
    fetch("/api/plugins")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data || !Array.isArray(data.connections)) return;
        const webSearch = data.connections.find((c) => /web search/i.test(c.name || ""));
        if (els.webSearchStatus && webSearch) {
          const map = { connected: "Terhubung", not_configured: "Belum dikonfigurasi", disabled: "Nonaktif" };
          els.webSearchStatus.textContent = map[webSearch.status] || webSearch.status;
        }
      })
      .catch(() => {
        /* leave the honest fallback text in place */
      });
  }

  applyToForm();
  loadProviders();
  loadWebSearchStatus();

  window.RinSettings = {
    get: function (key) {
      return settings[key];
    },
    getAll: getAll,
    set: set,
  };
})();
