/**
 * storage.js
 *
 * Helper localStorage TUNGGAL untuk RIN workspace (Projects, Schedule,
 * Library, Settings). Tujuannya seperti diminta di spec: JANGAN
 * menyebarkan JSON.parse/localStorage.setItem secara acak ke seluruh
 * file — semua page workspace lewat window.RinStorage.get/set/remove.
 *
 * Semua key otomatis diberi prefix "rin_", jadi RinStorage.get("library")
 * benar-benar membaca/menulis key localStorage "rin_library".
 */
(function () {
  "use strict";

  const PREFIX = "rin_";

  function fullKey(key) {
    return PREFIX + key;
  }

  /**
   * Membaca dan JSON.parse nilai tersimpan. Mengembalikan `fallback`
   * jika key belum ada ATAU jika data tersimpan rusak/tidak valid JSON
   * (tidak pernah melempar exception ke caller).
   */
  function get(key, fallback) {
    try {
      const raw = window.localStorage.getItem(fullKey(key));
      if (raw === null || raw === undefined) return fallback;
      return JSON.parse(raw);
    } catch (err) {
      console.warn("RinStorage.get gagal untuk key:", key, err);
      return fallback;
    }
  }

  /**
   * JSON.stringify lalu simpan. Mengembalikan true/false, tidak pernah
   * melempar (mis. localStorage penuh/disabled tidak akan membuat
   * halaman crash).
   */
  function set(key, value) {
    try {
      window.localStorage.setItem(fullKey(key), JSON.stringify(value));
      return true;
    } catch (err) {
      console.warn("RinStorage.set gagal untuk key:", key, err);
      return false;
    }
  }

  function remove(key) {
    try {
      window.localStorage.removeItem(fullKey(key));
    } catch (err) {
      console.warn("RinStorage.remove gagal untuk key:", key, err);
    }
  }

  window.RinStorage = { get: get, set: set, remove: remove };
})();
