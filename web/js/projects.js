/**
 * projects.js
 *
 * Projects workspace panel.
 *
 * No backend endpoint exists for Projects yet — everything here is
 * persisted to localStorage under the `rin_projects` key via
 * storage.js, exactly like schedule.js / library.js.
 *
 * "Open" does NOT open a real per-project workspace (Chat/Codex are
 * not scoped to a project yet) — it only marks the project as the
 * current "active project" (stored under `rin_active_project`) and
 * fires a `rin:project-opened` event so other scripts can react to
 * it later. We say this honestly in the UI instead of pretending
 * project-scoped chat/codex already exists.
 *
 * Data shape (one entry per project):
 *   { id, name, description, created_at, updated_at }
 */
(function () {
  "use strict";

  const STORAGE_KEY = "rin_projects";
  const ACTIVE_KEY = "rin_active_project";

  const grid = document.getElementById("projectGrid");
  const emptyState = document.getElementById("projectEmptyState");
  const newBtn = document.getElementById("projectNewBtn");
  const srStatus = document.getElementById("srStatus");

  const modalOverlay = document.getElementById("projectModalOverlay");
  const modalTitle = document.getElementById("projectModalTitle");
  const nameInput = document.getElementById("projectNameInput");
  const descInput = document.getElementById("projectDescInput");
  const modalError = document.getElementById("projectModalError");
  const modalCancel = document.getElementById("projectModalCancel");
  const modalSave = document.getElementById("projectModalSave");

  if (!grid || !newBtn || !modalOverlay) return;

  let projects = loadProjects();
  let editingId = null;

  function announce(text) {
    if (srStatus) srStatus.textContent = text;
  }

  function loadProjects() {
    const data = window.RinStorage.get(STORAGE_KEY, []);
    return Array.isArray(data) ? data : [];
  }

  function persist() {
    const ok = window.RinStorage.set(STORAGE_KEY, projects);
    if (!ok) announce("Gagal menyimpan project — penyimpanan browser tidak tersedia.");
    return ok;
  }

  function getActiveId() {
    return window.RinStorage.get(ACTIVE_KEY, null);
  }

  function setActiveId(id) {
    window.RinStorage.set(ACTIVE_KEY, id);
  }

  function makeId() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "proj_" + Date.now() + "_" + Math.random().toString(16).slice(2, 8);
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function formatDate(iso) {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });
    } catch (err) {
      return "";
    }
  }

  // ---------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------
  function render() {
    const activeId = getActiveId();
    const sorted = projects.slice().sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));

    if (sorted.length === 0) {
      emptyState.hidden = false;
      grid.hidden = true;
      grid.innerHTML = "";
      return;
    }

    emptyState.hidden = true;
    grid.hidden = false;

    grid.innerHTML = sorted
      .map((p) => {
        const isActive = p.id === activeId;
        return (
          '<div class="project-card' +
          (isActive ? " active" : "") +
          '" data-id="' +
          escapeHtml(p.id) +
          '">' +
          (isActive ? '<span class="project-active-badge">Aktif</span>' : "") +
          '<div class="project-card-name">' +
          escapeHtml(p.name) +
          "</div>" +
          (p.description
            ? '<p class="project-card-desc">' + escapeHtml(p.description) + "</p>"
            : '<p class="project-card-desc project-card-desc-empty">Tanpa deskripsi</p>') +
          '<div class="project-card-meta">Diperbarui ' +
          formatDate(p.updated_at) +
          "</div>" +
          '<div class="project-card-actions">' +
          '<button type="button" class="task-action-btn" data-action="open">Open</button>' +
          '<button type="button" class="task-action-btn" data-action="edit">Edit</button>' +
          '<button type="button" class="task-action-btn danger" data-action="delete">Hapus</button>' +
          "</div>" +
          "</div>"
        );
      })
      .join("");
  }

  // ---------------------------------------------------------
  // Modal
  // ---------------------------------------------------------
  function openModal(mode, project) {
    editingId = mode === "edit" && project ? project.id : null;
    modalTitle.textContent = mode === "edit" ? "Edit Project" : "New Project";
    nameInput.value = mode === "edit" && project ? project.name : "";
    descInput.value = mode === "edit" && project ? project.description || "" : "";
    modalError.hidden = true;
    modalOverlay.hidden = false;
    document.body.classList.add("modal-open");
    nameInput.focus();
  }

  function closeModal() {
    modalOverlay.hidden = true;
    document.body.classList.remove("modal-open");
    editingId = null;
  }

  function saveModal() {
    const name = nameInput.value.trim();
    if (!name) {
      modalError.hidden = false;
      nameInput.focus();
      return;
    }
    const description = descInput.value.trim();

    if (editingId) {
      const p = projects.find((x) => x.id === editingId);
      if (p) {
        p.name = name;
        p.description = description;
        p.updated_at = nowIso();
        announce("Project " + name + " diperbarui.");
      }
    } else {
      const ts = nowIso();
      projects.push({ id: makeId(), name: name, description: description, created_at: ts, updated_at: ts });
      announce("Project " + name + " dibuat.");
    }

    persist();
    render();
    closeModal();
  }

  newBtn.addEventListener("click", () => openModal("create"));
  modalCancel.addEventListener("click", closeModal);
  modalSave.addEventListener("click", saveModal);
  modalOverlay.addEventListener("click", (e) => {
    if (e.target === modalOverlay) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modalOverlay.hidden) closeModal();
  });
  nameInput.addEventListener("input", () => {
    if (nameInput.value.trim()) modalError.hidden = true;
  });

  // ---------------------------------------------------------
  // Card actions (delegated)
  // ---------------------------------------------------------
  grid.addEventListener("click", (e) => {
    const actionBtn = e.target.closest("[data-action]");
    if (!actionBtn) return;
    const card = actionBtn.closest(".project-card");
    if (!card) return;
    const id = card.getAttribute("data-id");
    const project = projects.find((p) => p.id === id);
    if (!project) return;

    const action = actionBtn.getAttribute("data-action");
    if (action === "open") {
      setActiveId(project.id);
      render();
      announce("Project " + project.name + " dijadikan project aktif.");
      window.dispatchEvent(new CustomEvent("rin:project-opened", { detail: { project: project } }));
    } else if (action === "edit") {
      openModal("edit", project);
    } else if (action === "delete") {
      const confirmed = window.confirm('Hapus project "' + project.name + '"? Tindakan ini tidak dapat dibatalkan.');
      if (!confirmed) return;
      projects = projects.filter((p) => p.id !== id);
      if (getActiveId() === id) setActiveId(null);
      persist();
      render();
      announce("Project " + project.name + " dihapus.");
    }
  });

  render();
})();
