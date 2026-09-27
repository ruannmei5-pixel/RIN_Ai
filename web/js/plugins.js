/**
 * plugins.js
 *
 * Workspace Plugins: HANYA membaca/menulis lewat endpoint baru
 * GET /api/plugins dan POST /api/plugins/{name}/toggle (app/api/routes.py),
 * yang keduanya murni jendela HTTP ke Tool Registry (app/tools/registry.py)
 * yang sudah ada — tidak ada plugin system baru.
 *
 * Status koneksi (Ollama/Web Search) dan status enabled/disabled tool
 * SELALU berasal dari response server, tidak pernah di-hardcode di sini.
 */
(function () {
  "use strict";

  const page = document.getElementById("page-plugins");
  if (!page) return;

  const connectionsEl = document.getElementById("pluginConnections");
  const toolsEl = document.getElementById("pluginToolList");
  const statusEl = document.getElementById("pluginLoadStatus");
  const refreshBtn = document.getElementById("pluginRefreshBtn");

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, function (c) {
      return (
        { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
      );
    });
  }

  function statusMeta(status) {
    switch (status) {
      case "connected":
        return { text: "Connected", cls: "conn-ok" };
      case "configured":
        return { text: "Configured", cls: "conn-ok" };
      case "not_configured":
        return { text: "Not configured", cls: "conn-warn" };
      case "disabled":
        return { text: "Disabled", cls: "conn-off" };
      default:
        return { text: status, cls: "conn-off" };
    }
  }

  function renderConnections(connections) {
    if (!connections || connections.length === 0) {
      connectionsEl.innerHTML = '<p class="empty-state">Tidak ada info koneksi.</p>';
      return;
    }

    connectionsEl.innerHTML = connections
      .map(function (c) {
        const meta = statusMeta(c.status);
        return (
          '<div class="conn-card">' +
          '<div class="conn-card-top">' +
          '<span class="conn-name">' +
          escapeHtml(c.name) +
          "</span>" +
          '<span class="conn-badge ' +
          meta.cls +
          '">' +
          meta.text +
          "</span>" +
          "</div>" +
          '<p class="conn-detail">' +
          escapeHtml(c.detail || "") +
          "</p>" +
          "</div>"
        );
      })
      .join("");
  }

  function renderTools(tools) {
    if (!tools || tools.length === 0) {
      toolsEl.innerHTML =
        '<p class="empty-state">Belum ada tool terdaftar di Tool Registry.</p>';
      return;
    }

    toolsEl.innerHTML = tools
      .map(function (t) {
        return (
          '<div class="tool-card" data-tool="' +
          escapeHtml(t.name) +
          '">' +
          '<div class="tool-card-top">' +
          "<div>" +
          '<div class="tool-name">' +
          escapeHtml(t.name) +
          "</div>" +
          '<div class="tool-permission">' +
          escapeHtml(t.permission) +
          "</div>" +
          "</div>" +
          '<label class="tool-switch" title="Enable/disable tool ini">' +
          '<input type="checkbox" ' +
          (t.enabled ? "checked" : "") +
          ' data-tool-toggle="' +
          escapeHtml(t.name) +
          '">' +
          '<span class="tool-switch-slider"></span>' +
          "</label>" +
          "</div>" +
          '<p class="tool-desc">' +
          escapeHtml(t.description) +
          "</p>" +
          "</div>"
        );
      })
      .join("");

    const toggles = toolsEl.querySelectorAll("[data-tool-toggle]");
    toggles.forEach(function (input) {
      input.addEventListener("change", function () {
        handleToggle(input);
      });
    });
  }

  async function handleToggle(input) {
    const name = input.dataset.toolToggle;
    const enabled = input.checked;
    input.disabled = true;

    try {
      const res = await fetch("/api/plugins/" + encodeURIComponent(name) + "/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: enabled }),
      });

      if (!res.ok) {
        throw new Error("Server mengembalikan status " + res.status);
      }
    } catch (err) {
      input.checked = !enabled; // revert ke status sebelumnya
      window.alert(
        "Gagal mengubah status tool '" +
          name +
          "'. Pastikan server RIN berjalan, lalu coba lagi."
      );
    } finally {
      input.disabled = false;
    }
  }

  async function loadPlugins() {
    statusEl.hidden = false;
    statusEl.className = "plugin-status";
    statusEl.textContent = "Memuat plugins...";

    try {
      const res = await fetch("/api/plugins");
      if (!res.ok) throw new Error("bad status " + res.status);
      const data = await res.json();

      renderConnections(data.connections);
      renderTools(data.tools);
      statusEl.hidden = true;
    } catch (err) {
      statusEl.className = "plugin-status plugin-status-error";
      statusEl.textContent =
        "Tidak dapat memuat data plugins dari server RIN. Pastikan server berjalan lalu coba Refresh.";
      connectionsEl.innerHTML = "";
      toolsEl.innerHTML = "";
    }
  }

  refreshBtn.addEventListener("click", loadPlugins);

  window.addEventListener("rin:page-changed", function (e) {
    if (e.detail.page === "plugins") loadPlugins();
  });
})();
