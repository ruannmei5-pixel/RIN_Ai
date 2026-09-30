/**
 * markdown-ext.js
 *
 * Ekstensi untuk window.RinMarkdown (dimuat SETELAH markdown.js):
 *  1. Fenced ```svg ... ``` -> diagram SVG yang DISANITASI (allowlist).
 *  2. Task list "- [ ] item" / "- [x] item" -> checkbox read-only.
 *  3. Tabel yang dikirim model dalam SATU baris
 *     ("| A | B | |---|---| | 1 | 2 | |") dipulihkan menjadi baris-baris
 *     tabel yang benar sebelum dirender.
 *
 * markdown.js sendiri tidak diubah; fungsi render() dibungkus.
 *
 * KEAMANAN SVG (allowlist, bukan blocklist):
 *  - hanya elemen grafis dasar; script, style, foreignObject, image,
 *    a, use, iframe, animate/set dsb. DIBUANG.
 *  - hanya atribut presentasi/geometri; semua on*, href, xlink:href,
 *    style, class DIBUANG.
 *  - nilai atribut yang berisi javascript:, data:, expression, atau
 *    url(...) yang bukan referensi internal (#id) ditolak.
 *  - DOCTYPE/ENTITY ditolak. Semua id di-prefix unik per diagram supaya
 *    tidak bisa menimpa id elemen halaman (DOM clobbering) dan tidak
 *    bentrok antar diagram.
 *  - SVG tidak valid / terlalu besar -> ditampilkan sebagai code block.
 *  - Fence svg yang belum tertutup (masih streaming) tampil sebagai
 *    code block, lalu berubah jadi diagram begitu fence ditutup.
 */
(function () {
  "use strict";

  const RM = window.RinMarkdown;
  if (!RM || typeof RM.render !== "function") return;

  const baseRender = RM.render;
  const MAX_SVG_CHARS = 60000;

  const ALLOWED_EL = new Set([
    "svg", "g", "defs", "title", "desc", "path", "rect", "circle", "ellipse",
    "line", "polyline", "polygon", "text", "tspan", "marker",
    "lineargradient", "radialgradient", "stop",
  ]);

  const ALLOWED_ATTR = new Set([
    "xmlns", "viewbox", "preserveaspectratio", "id", "x", "y", "x1", "x2", "y1", "y2",
    "cx", "cy", "r", "rx", "ry", "fx", "fy", "width", "height", "d", "points",
    "transform", "fill", "stroke", "stroke-width", "stroke-dasharray",
    "stroke-linecap", "stroke-linejoin", "fill-opacity", "stroke-opacity", "opacity",
    "fill-rule", "text-anchor", "dominant-baseline", "font-size", "font-weight",
    "font-family", "font-style", "letter-spacing", "dx", "dy", "marker-start",
    "marker-end", "marker-mid", "markerwidth", "markerheight", "refx", "refy",
    "orient", "markerunits", "offset", "stop-color", "stop-opacity",
    "gradientunits", "gradienttransform",
  ]);

  function safeValue(v) {
    if (/javascript:|data:|expression|@import|[<>]|&#/i.test(v)) return false;
    // url(...) hanya boleh menunjuk ke #id internal
    const urls = v.match(/url\(([^)]*)\)/gi) || [];
    return urls.every((u) => /^url\(\s*['"]?#[\w-]+['"]?\s*\)$/i.test(u));
  }

  function cleanNode(node) {
    Array.from(node.childNodes).forEach((child) => {
      if (child.nodeType === 3) return; // teks
      if (child.nodeType !== 1) { node.removeChild(child); return; } // komentar, PI, dll
      const name = (child.localName || "").toLowerCase();
      if (!ALLOWED_EL.has(name)) { node.removeChild(child); return; }
      Array.from(child.attributes).forEach((a) => {
        const an = a.name.toLowerCase();
        if (!ALLOWED_ATTR.has(an) || !safeValue(a.value)) child.removeAttribute(a.name);
      });
      cleanNode(child);
    });
  }

  // Beri prefix unik pada semua id dan perbarui referensi url(#id).
  function scopeIds(root, prefix) {
    const map = {};
    const all = [root].concat(Array.from(root.getElementsByTagName("*")));

    all.forEach((el) => {
      const old = el.getAttribute("id");
      if (old) {
        map[old] = prefix + old;
        el.setAttribute("id", prefix + old);
      }
    });

    all.forEach((el) => {
      Array.from(el.attributes).forEach((a) => {
        if (!/url\(/i.test(a.value)) return;
        el.setAttribute(
          a.name,
          a.value.replace(/url\(\s*['"]?#([\w-]+)['"]?\s*\)/gi, function (m, id) {
            return "url(#" + (map[id] || id) + ")";
          })
        );
      });
    });
  }

  function sanitizeSvg(src, index) {
    if (!src || src.length > MAX_SVG_CHARS) return null;
    if (/<!(?:DOCTYPE|ENTITY)/i.test(src)) return null;
    try {
      const doc = new DOMParser().parseFromString(src.trim(), "image/svg+xml");
      const root = doc.documentElement;
      if (!root || doc.getElementsByTagName("parsererror").length) return null;
      if ((root.localName || "").toLowerCase() !== "svg") return null;

      Array.from(root.attributes).forEach((a) => {
        const an = a.name.toLowerCase();
        if (!ALLOWED_ATTR.has(an) || !safeValue(a.value)) root.removeAttribute(a.name);
      });
      cleanNode(root);
      scopeIds(root, "rinsvg" + (index || 0) + "-");

      // Responsive: butuh viewBox; jika tidak ada, turunkan dari width/height.
      if (!root.getAttribute("viewBox")) {
        const w = parseFloat(root.getAttribute("width"));
        const h = parseFloat(root.getAttribute("height"));
        if (!(w > 0 && h > 0)) return null;
        root.setAttribute("viewBox", "0 0 " + w + " " + h);
      }
      root.removeAttribute("width");
      root.removeAttribute("height");
      root.setAttribute("xmlns", "http://www.w3.org/2000/svg");
      root.setAttribute("role", "img");

      return new XMLSerializer().serializeToString(root);
    } catch (err) {
      return null;
    }
  }

  // ---------------------------------------------------------
  // Tabel yang tergabung dalam satu baris
  //   "| A | B | |---|---| | 1 | 2 | |"
  // Antar baris ada sel kosong ("| |"), sehingga bila jumlah kolom n
  // diketahui dari baris pemisah, sel dapat dikelompokkan per (n+1).
  // Baris tabel normal (satu baris per record) TIDAK disentuh.
  // ---------------------------------------------------------
  const SEP_CELL = /^:?-{3,}:?$/;

  function fixCollapsedTables(text) {
    let inFence = false;

    return text
      .split("\n")
      .map(function (line) {
        if (/^\s*(`{3,}|~{3,})/.test(line)) {
          inFence = !inFence;
          return line;
        }
        if (inFence) return line;

        const t = line.trim();
        if (t.charAt(0) !== "|" || t.length < 12) return line;

        const cells = t.split("|").map(function (c) { return c.trim(); });
        cells.shift(); // sel kosong sebelum "|" pertama
        if (t.charAt(t.length - 1) === "|") cells.pop(); // sisa setelah "|" terakhir

        const sepAt = cells.findIndex(function (c) { return SEP_CELL.test(c); });
        if (sepAt < 1) return line; // tidak ada pemisah, atau baris pemisah biasa

        let n = 0;
        while (SEP_CELL.test(cells[sepAt + n] || "")) n++;

        // header (n sel) + 1 sel kosong pemisah baris harus tepat sebelum pemisah
        if (n < 1 || sepAt !== n + 1 || cells[n] !== "") return line;
        // Baris terakhir biasanya tidak diikuti sel kosong pemisah.
        if (cells.length % (n + 1) === n) cells.push("");
        if (cells.length % (n + 1) !== 0) return line;

        const rows = [];
        for (let i = 0; i < cells.length; i += n + 1) {
          rows.push("| " + cells.slice(i, i + n).join(" | ") + " |");
        }
        return rows.join("\n");
      })
      .join("\n");
  }

  const SVG_FENCE_RE = /(^|\n)[ \t]*(`{3,}|~{3,})[ \t]*svg[ \t]*\n([\s\S]*?)\n[ \t]*\2[ \t]*(?=\n|$)/gi;

  function render(raw) {
    let text = String(raw || "").replace(/\r\n?/g, "\n");
    const svgs = [];

    text = text.replace(SVG_FENCE_RE, function (m, lead, marker, body) {
      svgs.push(body);
      return lead + "\n\nRINSVG" + (svgs.length - 1) + "X\n\n";
    });

    text = fixCollapsedTables(text);

    let html = baseRender(text);

    const figure = function (i) {
      const src = svgs[+i];
      const clean = sanitizeSvg(src, +i);
      if (clean) return '<figure class="svg-figure">' + clean + "</figure>";
      return baseRender("```xml\n" + src + "\n```"); // fallback aman
    };

    html = html.replace(/<p>RINSVG(\d+)X<\/p>/g, function (m, i) { return figure(i); });
    // Placeholder yang terjebak di dalam list/blockquote
    html = html.replace(/RINSVG(\d+)X/g, function (m, i) { return figure(i); });

    // Task list -> checkbox read-only (sisa yang belum ditangani markdown.js)
    // Model kecil sering menulis "[]" (tanpa spasi) -> dianggap belum dicentang.
    html = html.replace(/<li>\[( |x|X)?\]\s*/g, function (m, c) {
      const checked = c === "x" || c === "X";
      return '<li class="task"><input type="checkbox" disabled' +
        (checked ? " checked" : "") + ' aria-hidden="true"> ';
    });

    return html;
  }

  RM.render = render;
  RM.sanitizeSvg = sanitizeSvg;
})();
