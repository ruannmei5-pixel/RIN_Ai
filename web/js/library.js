/**
 * library.js
 *
 * Workspace Library: catatan/referensi pengguna, disimpan di
 * localStorage key "rin_library" (lewat RinStorage — lihat storage.js).
 *
 * Data per note: { id, title, content, tags, pinned, created_at, updated_at }
 *
 * Fitur: create, edit, delete, search, pin, tag — semua bekerja
 * sepenuhnya di sisi client, sesuai spec (belum ada backend Library).
 */
(function () {
  "use strict";

  const page = document.getElementById("page-library");
  if (!page) return;

  const STORAGE_KEY = "library";

  const searchInput = document.getElementById("libSearchInput");
  const newNoteBtn = document.getElementById("libNewNoteBtn");
  const listEl = document.getElementById("libNoteList");
  const emptyState = document.getElementById("libEmptyState");

  const editorPanel = document.getElementById("libEditorPanel");
  const editorTitleEl = document.getElementById("libEditorTitle");
  const titleInput = document.getElementById("libTitleInput");
  const tagsInput = document.getElementById("libTagsInput");
  const contentInput = document.getElementById("libContentInput");
  const saveBtn = document.getElementById("libSaveBtn");
  const cancelBtn = document.getElementById("libCancelBtn");

  let currentEditId = null;
  let hasLoadedOnce = false;

  function loadNotes() {
    const notes = window.RinStorage.get(STORAGE_KEY, []);
    return Array.isArray(notes) ? notes : [];
  }

  function saveNotes(notes) {
    window.RinStorage.set(STORAGE_KEY, notes);
  }

  function uid() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return "note_" + Date.now() + "_" + Math.random().toString(16).slice(2);
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, function (c) {
      return (
        { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
      );
    });
  }

  function formatDate(iso) {
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return "";
      return (
        d.toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" }) +
        " " +
        d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })
      );
    } catch (err) {
      return "";
    }
  }

  function openEditor(note) {
    currentEditId = note ? note.id : null;
    editorTitleEl.textContent = note ? "Edit Catatan" : "Catatan Baru";
    titleInput.value = note ? note.title || "" : "";
    tagsInput.value = note && Array.isArray(note.tags) ? note.tags.join(", ") : "";
    contentInput.value = note ? note.content || "" : "";
    editorPanel.hidden = false;
    titleInput.focus();
    editorPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function closeEditor() {
    editorPanel.hidden = true;
    currentEditId = null;
    titleInput.value = "";
    tagsInput.value = "";
    contentInput.value = "";
  }

  function render() {
    const notes = loadNotes();
    const query = (searchInput.value || "").trim().toLowerCase();

    const filtered = notes.filter(function (note) {
      if (!query) return true;
      const haystack = (
        (note.title || "") +
        " " +
        (note.content || "") +
        " " +
        (Array.isArray(note.tags) ? note.tags.join(" ") : "")
      ).toLowerCase();
      return haystack.indexOf(query) !== -1;
    });

    filtered.sort(function (a, b) {
      const pinDiff = (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0);
      if (pinDiff !== 0) return pinDiff;
      return new Date(b.updated_at || 0) - new Date(a.updated_at || 0);
    });

    listEl.innerHTML = "";

    if (filtered.length === 0) {
      emptyState.hidden = false;
      emptyState.textContent =
        notes.length === 0
          ? "Belum ada catatan. Buat catatan pertamamu untuk menyimpan ide dan referensi."
          : "Tidak ada catatan yang cocok dengan pencarianmu.";
      return;
    }

    emptyState.hidden = true;

    filtered.forEach(function (note) {
      const card = document.createElement("div");
      card.className = "lib-card" + (note.pinned ? " pinned" : "");

      const contentStr = note.content || "";
      const preview = contentStr.slice(0, 140);
      const tagsHtml = (Array.isArray(note.tags) ? note.tags : [])
        .map(function (t) {
          return '<span class="lib-tag">' + escapeHtml(t) + "</span>";
        })
        .join("");

      card.innerHTML =
        '<div class="lib-card-head">' +
        '<h3 class="lib-card-title">' +
        (note.pinned ? "📌 " : "") +
        escapeHtml(note.title || "(Tanpa judul)") +
        "</h3>" +
        '<div class="lib-card-actions">' +
        '<button type="button" class="lib-action-btn" data-action="pin" title="' +
        (note.pinned ? "Lepas pin" : "Pin catatan") +
        '">' +
        (note.pinned ? "📌" : "📍") +
        "</button>" +
        '<button type="button" class="lib-action-btn" data-action="edit" title="Edit">✎</button>' +
        '<button type="button" class="lib-action-btn" data-action="delete" title="Hapus">🗑</button>' +
        "</div>" +
        "</div>" +
        '<p class="lib-card-preview">' +
        escapeHtml(preview) +
        (contentStr.length > 140 ? "…" : "") +
        "</p>" +
        '<div class="lib-card-footer">' +
        '<div class="lib-tags">' +
        tagsHtml +
        "</div>" +
        '<span class="lib-updated">Diperbarui ' +
        formatDate(note.updated_at) +
        "</span>" +
        "</div>";

      card.querySelector('[data-action="pin"]').addEventListener("click", function () {
        togglePin(note.id);
      });
      card.querySelector('[data-action="edit"]').addEventListener("click", function () {
        openEditor(note);
      });
      card.querySelector('[data-action="delete"]').addEventListener("click", function () {
        deleteNote(note.id);
      });

      listEl.appendChild(card);
    });
  }

  function togglePin(id) {
    const notes = loadNotes();
    const note = notes.find(function (n) {
      return n.id === id;
    });
    if (!note) return;
    note.pinned = !note.pinned;
    note.updated_at = new Date().toISOString();
    saveNotes(notes);
    render();
  }

  function deleteNote(id) {
    if (!window.confirm("Hapus catatan ini? Tindakan ini tidak bisa dibatalkan.")) return;
    const notes = loadNotes().filter(function (n) {
      return n.id !== id;
    });
    saveNotes(notes);
    render();
  }

  function handleSave() {
    const title = titleInput.value.trim();
    const content = contentInput.value.trim();

    if (!title && !content) {
      titleInput.focus();
      return;
    }

    const tags = tagsInput.value
      .split(",")
      .map(function (t) {
        return t.trim();
      })
      .filter(Boolean);

    const now = new Date().toISOString();
    const notes = loadNotes();

    if (currentEditId) {
      const note = notes.find(function (n) {
        return n.id === currentEditId;
      });
      if (note) {
        note.title = title;
        note.content = content;
        note.tags = tags;
        note.updated_at = now;
      }
    } else {
      notes.push({
        id: uid(),
        title: title,
        content: content,
        tags: tags,
        pinned: false,
        created_at: now,
        updated_at: now,
      });
    }

    saveNotes(notes);
    closeEditor();
    render();
  }

  newNoteBtn.addEventListener("click", function () {
    openEditor(null);
  });
  saveBtn.addEventListener("click", handleSave);
  cancelBtn.addEventListener("click", closeEditor);
  searchInput.addEventListener("input", render);

  window.addEventListener("rin:page-changed", function (e) {
    if (e.detail.page === "library") {
      hasLoadedOnce = true;
      render();
    }
  });

  // Render sekali di awal juga, supaya data sudah siap kalau user
  // langsung membuka Library lewat reload/deep link di masa depan.
  render();
})();
