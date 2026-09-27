/**
 * schedule.js
 *
 * Schedule workspace panel (phase 3 of the workspace redesign).
 *
 * No backend endpoint exists for Schedule yet — everything here is
 * persisted to localStorage under the `rin_schedule` key via
 * storage.js. Reminders are shown inside the app only: there is no
 * OS-level notification integration, and this file never claims
 * there is one.
 *
 * Data shape (one entry per task):
 *   { id, title, description, date, time, priority, completed,
 *     created_at, updated_at }
 *   - date: "YYYY-MM-DD" or "" if not set
 *   - time: "HH:MM" or "" if not set
 *   - priority: "low" | "medium" | "high"
 */
(function () {
  "use strict";

  const STORAGE_KEY = "rin_schedule";
  const PRIORITY_LABELS = { low: "Rendah", medium: "Sedang", high: "Tinggi" };

  const list = document.getElementById("scheduleList");
  const emptyState = document.getElementById("scheduleEmptyState");
  const emptyTitle = document.getElementById("scheduleEmptyTitle");
  const emptyDesc = document.getElementById("scheduleEmptyDesc");
  const newBtn = document.getElementById("scheduleNewBtn");
  const filterTabs = document.querySelectorAll("#scheduleFilterTabs .filter-tab");
  const srStatus = document.getElementById("srStatus");

  const modalOverlay = document.getElementById("scheduleModalOverlay");
  const modalTitle = document.getElementById("scheduleModalTitle");
  const titleInput = document.getElementById("scheduleTitleInput");
  const descInput = document.getElementById("scheduleDescInput");
  const dateInput = document.getElementById("scheduleDateInput");
  const timeInput = document.getElementById("scheduleTimeInput");
  const priorityInput = document.getElementById("schedulePriorityInput");
  const modalError = document.getElementById("scheduleModalError");
  const modalCancel = document.getElementById("scheduleModalCancel");
  const modalSave = document.getElementById("scheduleModalSave");

  if (!list || !newBtn || !modalOverlay) return;

  let tasks = loadTasks();
  let editingId = null;
  let activeFilter = "all";

  const EMPTY_COPY = {
    all: {
      title: "Belum ada task",
      desc: "Buat task pertamamu untuk mulai mengatur jadwal. Reminder hanya tampil di dalam aplikasi ini, tidak ada notifikasi sistem.",
    },
    today: { title: "Tidak ada task hari ini", desc: "Task dengan tanggal hari ini akan muncul di sini." },
    upcoming: { title: "Tidak ada task mendatang", desc: "Task dengan tanggal setelah hari ini akan muncul di sini." },
    completed: { title: "Belum ada task selesai", desc: "Task yang sudah kamu tandai selesai akan muncul di sini." },
  };

  function announce(text) {
    if (srStatus) srStatus.textContent = text;
  }

  function loadTasks() {
    const data = window.RinStorage.get(STORAGE_KEY, []);
    return Array.isArray(data) ? data : [];
  }

  function persist() {
    const ok = window.RinStorage.set(STORAGE_KEY, tasks);
    if (!ok) announce("Gagal menyimpan task — penyimpanan browser tidak tersedia.");
    return ok;
  }

  function makeId() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "task_" + Date.now() + "_" + Math.random().toString(16).slice(2, 8);
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function todayStr() {
    const d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function formatDate(dateStr) {
    if (!dateStr) return "";
    try {
      const [y, m, d] = dateStr.split("-").map(Number);
      return new Date(y, m - 1, d).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });
    } catch (err) {
      return dateStr;
    }
  }

  function sortKey(task) {
    return (task.date || "9999-99-99") + " " + (task.time || "99:99");
  }

  function matchesFilter(task, filter) {
    if (filter === "completed") return !!task.completed;
    if (filter === "today") return !task.completed && task.date === todayStr();
    if (filter === "upcoming") return !task.completed && !!task.date && task.date > todayStr();
    return true; // "all"
  }

  // ---------------------------------------------------------
  // Rendering
  // ---------------------------------------------------------
  function render() {
    const visible = tasks.filter((t) => matchesFilter(t, activeFilter)).sort((a, b) => {
      const ka = sortKey(a);
      const kb = sortKey(b);
      return ka < kb ? -1 : ka > kb ? 1 : 0;
    });

    if (visible.length === 0) {
      emptyState.hidden = false;
      list.hidden = true;
      list.innerHTML = "";
      const copy = EMPTY_COPY[activeFilter] || EMPTY_COPY.all;
      emptyTitle.textContent = copy.title;
      emptyDesc.textContent = copy.desc;
      return;
    }

    emptyState.hidden = true;
    list.hidden = false;

    list.innerHTML = visible
      .map((t) => {
        const metaParts = [];
        if (t.date) metaParts.push(formatDate(t.date));
        if (t.time) metaParts.push(t.time);
        const meta = metaParts.length ? metaParts.join(" · ") : "Tanpa tanggal";
        const priority = PRIORITY_LABELS[t.priority] ? t.priority : "medium";

        return (
          '<div class="task-item' +
          (t.completed ? " completed" : "") +
          '" data-id="' +
          escapeHtml(t.id) +
          '">' +
          '<button type="button" class="task-checkbox" data-action="toggle" aria-label="' +
          (t.completed ? "Tandai belum selesai" : "Tandai selesai") +
          '">' +
          (t.completed ? "✓" : "") +
          "</button>" +
          '<div class="task-body">' +
          '<div class="task-title-row">' +
          '<span class="task-title">' +
          escapeHtml(t.title) +
          "</span>" +
          '<span class="task-priority priority-' +
          priority +
          '">' +
          PRIORITY_LABELS[priority] +
          "</span>" +
          "</div>" +
          (t.description ? '<p class="task-desc">' + escapeHtml(t.description) + "</p>" : "") +
          '<div class="task-meta">' +
          escapeHtml(meta) +
          "</div>" +
          "</div>" +
          '<div class="task-actions">' +
          '<button type="button" class="task-action-btn" data-action="edit">Edit</button>' +
          '<button type="button" class="task-action-btn danger" data-action="delete">Hapus</button>' +
          "</div>" +
          "</div>"
        );
      })
      .join("");
  }

  // ---------------------------------------------------------
  // Filter tabs
  // ---------------------------------------------------------
  filterTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      activeFilter = tab.getAttribute("data-filter");
      filterTabs.forEach((t) => t.classList.toggle("active", t === tab));
      render();
    });
  });

  // ---------------------------------------------------------
  // Modal
  // ---------------------------------------------------------
  function openModal(mode, task) {
    editingId = mode === "edit" && task ? task.id : null;
    modalTitle.textContent = mode === "edit" ? "Edit Task" : "New Task";
    titleInput.value = mode === "edit" && task ? task.title : "";
    descInput.value = mode === "edit" && task ? task.description || "" : "";
    dateInput.value = mode === "edit" && task ? task.date || "" : "";
    timeInput.value = mode === "edit" && task ? task.time || "" : "";
    priorityInput.value = mode === "edit" && task ? task.priority || "medium" : "medium";
    modalError.hidden = true;
    modalOverlay.hidden = false;
    document.body.classList.add("modal-open");
    titleInput.focus();
  }

  function closeModal() {
    modalOverlay.hidden = true;
    document.body.classList.remove("modal-open");
    editingId = null;
  }

  function saveModal() {
    const title = titleInput.value.trim();
    if (!title) {
      modalError.hidden = false;
      titleInput.focus();
      return;
    }

    const fields = {
      title: title,
      description: descInput.value.trim(),
      date: dateInput.value || "",
      time: timeInput.value || "",
      priority: priorityInput.value || "medium",
    };

    if (editingId) {
      const task = tasks.find((t) => t.id === editingId);
      if (task) {
        Object.assign(task, fields);
        task.updated_at = nowIso();
        announce("Task " + title + " diperbarui.");
      }
    } else {
      const ts = nowIso();
      tasks.push(Object.assign({ id: makeId(), completed: false, created_at: ts, updated_at: ts }, fields));
      announce("Task " + title + " dibuat.");
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
  titleInput.addEventListener("input", () => {
    if (titleInput.value.trim()) modalError.hidden = true;
  });

  // ---------------------------------------------------------
  // Task actions (delegated)
  // ---------------------------------------------------------
  list.addEventListener("click", (e) => {
    const actionBtn = e.target.closest("[data-action]");
    if (!actionBtn) return;
    const item = actionBtn.closest(".task-item");
    if (!item) return;
    const id = item.getAttribute("data-id");
    const task = tasks.find((t) => t.id === id);
    if (!task) return;

    const action = actionBtn.getAttribute("data-action");
    if (action === "toggle") {
      task.completed = !task.completed;
      task.updated_at = nowIso();
      persist();
      render();
      announce(task.completed ? "Task " + task.title + " selesai." : "Task " + task.title + " ditandai belum selesai.");
    } else if (action === "edit") {
      openModal("edit", task);
    } else if (action === "delete") {
      const confirmed = window.confirm('Hapus task "' + task.title + '"? Tindakan ini tidak dapat dibatalkan.');
      if (!confirmed) return;
      tasks = tasks.filter((t) => t.id !== id);
      persist();
      render();
      announce("Task " + task.title + " dihapus.");
    }
  });

  render();
})();
