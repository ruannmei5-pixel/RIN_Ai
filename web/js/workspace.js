/**
 * workspace.js
 *
 * SPA router sederhana untuk RIN workspace: mengganti page yang aktif
 * (Chat/Projects/Schedule/Library/Plugins/Codex/Settings) tanpa reload
 * penuh, plus perilaku sidebar (active state, mobile drawer).
 *
 * Halaman lain (library.js, plugins.js, dst) mendengarkan event custom
 * "rin:page-changed" untuk memuat/refresh datanya sendiri saat pertama
 * kali dibuka — workspace.js sengaja tidak tahu apa-apa tentang isi
 * page tersebut (pemisahan tanggung jawab).
 */
(function () {
  "use strict";

  const sidebar = document.getElementById("sidebar");
  const sidebarOverlay = document.getElementById("sidebarOverlay");
  const mobileMenuBtn = document.getElementById("mobileMenuBtn");
  const headerSubtitle = document.getElementById("headerSubtitle");
  const newChatButton = document.getElementById("newChatButton");
  const voiceToggleButton = document.getElementById("voiceToggleButton");
  const sidebarStatusDot = document.getElementById("sidebarStatusDot");
  const sidebarStatusLabel = document.getElementById("sidebarStatusLabel");
  const statusDot = document.getElementById("statusDot");
  const statusLabel = document.getElementById("statusLabel");

  const navItems = Array.prototype.slice.call(
    document.querySelectorAll(".nav-item[data-page]")
  );
  const pagePanels = Array.prototype.slice.call(
    document.querySelectorAll(".page-panel[data-page-panel]")
  );

  // Label header + apakah kontrol chat (New Chat, Voice toggle) relevan
  // untuk page tersebut. Page yang belum diimplementasikan tetap punya
  // entri di sini supaya header/subtitle-nya tetap jujur (bukan diam
  // menampilkan subtitle chat lama).
  const PAGE_META = {
    chat: {
      label: "Responsive Intelligent Navigator",
      showChatControls: true,
    },
    projects: { label: "Projects", showChatControls: false },
    schedule: { label: "Schedule", showChatControls: false },
    library: { label: "Library — catatan & referensi kamu", showChatControls: false },
    plugins: { label: "Plugins — tools yang terhubung ke RIN", showChatControls: false },
    codex: { label: "Codex", showChatControls: false },
    settings: { label: "Settings", showChatControls: false },
  };

  let currentPage = "chat";

  function closeDrawer() {
    if (sidebar) sidebar.classList.remove("open");
    if (sidebarOverlay) sidebarOverlay.classList.remove("visible");
  }

  function openDrawer() {
    if (sidebar) sidebar.classList.add("open");
    if (sidebarOverlay) sidebarOverlay.classList.add("visible");
  }

  function toggleDrawer() {
    if (sidebar && sidebar.classList.contains("open")) {
      closeDrawer();
    } else {
      openDrawer();
    }
  }

  function setActivePage(page) {
    const meta = PAGE_META[page] ? page : "chat";
    currentPage = meta;

    navItems.forEach(function (btn) {
      btn.classList.toggle("active", btn.dataset.page === meta);
    });

    pagePanels.forEach(function (panel) {
      panel.classList.toggle("active", panel.dataset.pagePanel === meta);
    });

    if (headerSubtitle) {
      headerSubtitle.textContent = PAGE_META[meta].label;
    }

    const showChatControls = PAGE_META[meta].showChatControls;
    if (newChatButton) newChatButton.style.display = showChatControls ? "" : "none";
    if (voiceToggleButton) voiceToggleButton.style.display = showChatControls ? "" : "none";

    closeDrawer();

    window.dispatchEvent(
      new CustomEvent("rin:page-changed", { detail: { page: meta } })
    );
  }

  navItems.forEach(function (btn) {
    btn.addEventListener("click", function () {
      setActivePage(btn.dataset.page);
    });
  });

  if (mobileMenuBtn) {
    mobileMenuBtn.addEventListener("click", toggleDrawer);
  }

  if (sidebarOverlay) {
    sidebarOverlay.addEventListener("click", closeDrawer);
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeDrawer();
  });

  // Sidebar "New Chat" (di footer atas) memicu tombol New Chat header
  // yang sudah ada di app.js, supaya logic-nya tetap satu tempat.
  const sidebarNewChatBtn = document.getElementById("sidebarNewChatBtn");
  if (sidebarNewChatBtn && newChatButton) {
    sidebarNewChatBtn.addEventListener("click", function () {
      setActivePage("chat");
      newChatButton.click();
    });
  }

  // Cerminkan status online/offline header (diisi oleh app.js lewat
  // checkHealth()) ke kartu status di sidebar, tanpa mendefinisikan
  // ulang polling-nya di sini.
  if (statusDot && sidebarStatusDot && statusLabel && sidebarStatusLabel) {
    const mirrorStatus = function () {
      sidebarStatusDot.className = statusDot.className;
      sidebarStatusLabel.textContent = statusLabel.textContent;
    };
    const observer = new MutationObserver(mirrorStatus);
    observer.observe(statusDot, { attributes: true, attributeFilter: ["class"] });
    observer.observe(statusLabel, { childList: true, characterData: true, subtree: true });
    mirrorStatus();
  }

  setActivePage("chat");

  window.RinWorkspace = {
    setActivePage: setActivePage,
    getCurrentPage: function () {
      return currentPage;
    },
  };
})();
