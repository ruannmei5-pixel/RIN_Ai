/**
 * markdown.js
 *
 * Renderer Markdown RIN: mandiri (tanpa CDN, tetap jalan offline di LAN).
 * Dipanggil ulang pada SETIAP chunk streaming, jadi parser dibuat
 * toleran terhadap teks yang belum selesai (code block belum tertutup,
 * tabel baru setengah jalan, dst) dan tidak pernah melempar exception.
 *
 * Didukung:
 *   heading, paragraf, bullet/numbered list (nested, loose list, nomor awal
 *   dipertahankan), tabel (dengan alignment), blockquote (nested),
 *   fenced code (``` / ~~~) + syntax highlighting ringan + tombol Salin,
 *   diagram topologi jaringan (```topology), inline code, bold, italic,
 *   strikethrough, link (http/https/mailto), bare URL, horizontal rule.
 *
 * KEAMANAN: semua teks di-escape SEBELUM diformat. Link hanya boleh
 * http(s)/mailto. Tidak ada HTML mentah dari model yang pernah lolos.
 *
 * API: window.RinMarkdown.render(text) -> string HTML
 */
(function () {
  "use strict";

  const root = typeof window !== "undefined" ? window : globalThis;

  // ---------------------------------------------------------
  // Util
  // ---------------------------------------------------------
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  const LANG_ALIASES = {
    py: "python", python3: "python",
    js: "javascript", node: "javascript", jsx: "javascript",
    ts: "typescript", tsx: "typescript",
    sh: "bash", shell: "bash", zsh: "bash", console: "bash",
    ps: "powershell", ps1: "powershell", pwsh: "powershell",
    yml: "yaml", htm: "html", xml: "html", svg: "html",
    jsonc: "json",
  };

  function normalizeLang(raw) {
    const l = (raw || "").toLowerCase();
    return LANG_ALIASES[l] || l;
  }

  // ---------------------------------------------------------
  // Syntax highlighting (ringan, berbasis regex)
  // ---------------------------------------------------------
  const STR_DQ = '"(?:\\\\.|[^"\\\\\\n])*"';
  const STR_SQ = "'(?:\\\\.|[^'\\\\\\n])*'";
  const NUM = "\\b\\d+(?:\\.\\d+)?\\b";
  const words = (s) => s.split(/\s+/).filter(Boolean);

  const JS_KW = words(
    "async await break case catch class const continue default delete do else export extends " +
    "finally for from function if import in instanceof let new null of return static super " +
    "switch this throw try typeof undefined var void while yield true false"
  );

  const SPECS = {
    python: {
      extra: [],
      comment: ["#[^\\n]*"],
      string: ['"""[\\s\\S]*?"""', "'''[\\s\\S]*?'''", STR_DQ, STR_SQ],
      keywords: words(
        "and as assert async await break class continue def del elif else except finally for from " +
        "global if import in is lambda None nonlocal not or pass raise return try while with yield " +
        "True False self"
      ),
    },
    javascript: {
      comment: ["//[^\\n]*", "/\\*[\\s\\S]*?\\*/"],
      string: [STR_DQ, STR_SQ, "`(?:\\\\.|[^`\\\\])*`"],
      keywords: JS_KW,
    },
    typescript: {
      comment: ["//[^\\n]*", "/\\*[\\s\\S]*?\\*/"],
      string: [STR_DQ, STR_SQ, "`(?:\\\\.|[^`\\\\])*`"],
      keywords: JS_KW.concat(words("interface type enum implements public private protected readonly")),
    },
    bash: {
      comment: ["(?:^|(?<=\\s))#[^\\n]*"],
      string: [STR_DQ, STR_SQ],
      extra: [["tok-v", "\\$\\{?[A-Za-z_][\\w]*\\}?"]],
      keywords: words("if then else elif fi for while do done case esac function in echo cd export sudo return exit"),
    },
    powershell: {
      comment: ["<#[\\s\\S]*?#>", "#[^\\n]*"],
      string: [STR_DQ, STR_SQ],
      extra: [
        ["tok-v", "\\$[A-Za-z_][\\w:]*"],
        ["tok-f", "\\b[A-Z][a-z]+-[A-Z][A-Za-z]+\\b"],
      ],
      keywords: words("if else elseif foreach for while function param return switch try catch finally throw in break continue"),
    },
    sql: {
      flags: "gi",
      comment: ["--[^\\n]*", "/\\*[\\s\\S]*?\\*/"],
      string: [STR_SQ, STR_DQ],
      keywords: words(
        "select from where insert into values update set delete create table alter drop join left right " +
        "inner outer on group by order having limit as and or not null primary key foreign references " +
        "distinct union like in is count sum avg min max asc desc index database"
      ),
    },
    json: {
      extra: [["tok-p", '"(?:\\\\.|[^"\\\\\\n])*"(?=\\s*:)']],
      comment: [],
      string: [STR_DQ],
      keywords: ["true", "false", "null"],
    },
    yaml: {
      extra: [["tok-p", "^[ \\t-]*[\\w.-]+(?=\\s*:)"]],
      comment: ["(?:^|(?<=\\s))#[^\\n]*"],
      string: [STR_DQ, STR_SQ],
      keywords: ["true", "false", "null"],
      flags: "gm",
    },
    html: {
      extra: [["tok-t", "</?[A-Za-z][^>]*>"]],
      comment: ["<!--[\\s\\S]*?-->"],
      string: [],
      keywords: null,
      noNumbers: true,
    },
    css: {
      extra: [
        ["tok-k", "@[\\w-]+"],
        ["tok-n", "#[0-9a-fA-F]{3,8}\\b"],
        ["tok-p", "[\\w-]+(?=\\s*:)"],
      ],
      comment: ["/\\*[\\s\\S]*?\\*/"],
      string: [STR_DQ, STR_SQ],
      keywords: null,
    },
  };

  const compiled = {};

  function compile(lang) {
    if (compiled[lang] !== undefined) return compiled[lang];
    const spec = SPECS[lang];
    if (!spec) return (compiled[lang] = null);

    const groups = [];
    (spec.extra || []).forEach((e) => groups.push([e[0], e[1]]));
    (spec.comment || []).forEach((s) => groups.push(["tok-c", s]));
    (spec.string || []).forEach((s) => groups.push(["tok-s", s]));
    if (!spec.noNumbers) groups.push(["tok-n", NUM]);
    if (spec.keywords && spec.keywords.length) {
      groups.push(["tok-k", "\\b(?:" + spec.keywords.join("|") + ")\\b"]);
    }

    try {
      const re = new RegExp(groups.map((g) => "(" + g[1] + ")").join("|"), spec.flags || "g");
      return (compiled[lang] = { re: re, classes: groups.map((g) => g[0]) });
    } catch (err) {
      return (compiled[lang] = null);
    }
  }

  function highlight(code, langRaw) {
    const lang = normalizeLang(langRaw);
    const c = compile(lang);
    if (!c) return escapeHtml(code);

    let out = "";
    let last = 0;
    c.re.lastIndex = 0;
    let m;
    while ((m = c.re.exec(code)) !== null) {
      if (m[0] === "") {
        c.re.lastIndex++;
        continue;
      }
      let g = -1;
      for (let k = 1; k < m.length; k++) {
        if (m[k] !== undefined) { g = k - 1; break; }
      }
      out += escapeHtml(code.slice(last, m.index));
      out += '<span class="' + c.classes[g] + '">' + escapeHtml(m[0]) + "</span>";
      last = m.index + m[0].length;
    }
    return out + escapeHtml(code.slice(last));
  }

  // ---------------------------------------------------------
  // Diagram topologi jaringan (```topology)
  //
  // Format:
  //   router R1 "Router Master"
  //   switch SW1 "Switch Core"
  //   R1 -- SW1 "Gi0/1"      (-- biasa, == trunk/tebal, -.- putus-putus)
  // Tipe: router switch firewall server pc cloud ap
  // ---------------------------------------------------------
  const TOPO_TYPES = {
    router: "ROUTER", switch: "SWITCH", firewall: "FIREWALL",
    server: "SERVER", pc: "PC", cloud: "INTERNET", ap: "ACCESS POINT",
  };
  const TOPO_NODE_RE = /^([A-Za-z]+)\s+([\w.-]+)(?:\s+"([^"]*)")?\s*$/;
  const TOPO_LINK_RE = /^([\w.-]+)\s*(--|==|-\.-)\s*([\w.-]+)(?:\s+"([^"]*)")?\s*$/;

  function parseTopology(src) {
    const nodes = [];
    const byId = {};
    const links = [];

    const ensure = (id) => {
      if (!byId[id]) {
        byId[id] = { id: id, type: "pc", label: id, layer: 0, col: 0, x: 0, y: 0 };
        nodes.push(byId[id]);
      }
      return byId[id];
    };

    src.split("\n").forEach((raw) => {
      const line = raw.trim();
      if (!line || line.charAt(0) === "#") return;

      const l = line.match(TOPO_LINK_RE);
      if (l) {
        ensure(l[1]);
        ensure(l[3]);
        links.push({ a: l[1], b: l[3], kind: l[2], label: l[4] || "", off: 0 });
        return;
      }

      const n = line.match(TOPO_NODE_RE);
      if (n && TOPO_TYPES[n[1].toLowerCase()]) {
        const node = ensure(n[2]);
        node.type = n[1].toLowerCase();
        node.label = n[3] || n[2];
      }
    });

    return { nodes: nodes, byId: byId, links: links };
  }

  function topologyHtml(code) {
    const t = parseTopology(code);
    if (!t.nodes.length) return null; // belum ada node (mis. masih streaming)

    const { nodes, byId, links } = t;
    const NW = 124, NH = 52, GX = 40, GY = 78, PAD = 24;

    // --- layer lewat BFS dari node pertama ---
    const adj = {};
    nodes.forEach((n) => { adj[n.id] = []; });
    links.forEach((k) => { adj[k.a].push(k.b); adj[k.b].push(k.a); });

    const seen = {};
    nodes.forEach((start) => {
      if (seen[start.id]) return;
      seen[start.id] = true;
      start.layer = 0;
      const queue = [start];
      while (queue.length) {
        const cur = queue.shift();
        adj[cur.id].forEach((id) => {
          if (!seen[id]) {
            seen[id] = true;
            byId[id].layer = cur.layer + 1;
            queue.push(byId[id]);
          }
        });
      }
    });

    const layers = [];
    nodes.forEach((n) => {
      (layers[n.layer] = layers[n.layer] || []).push(n);
    });
    layers.forEach((arr) => arr.forEach((n, i) => { n.col = i; }));

    const maxCols = Math.max.apply(null, layers.map((a) => a.length));
    const W = maxCols * NW + (maxCols - 1) * GX + PAD * 2;

    layers.forEach((arr, li) => {
      const rowW = arr.length * NW + (arr.length - 1) * GX;
      const startX = PAD + (W - PAD * 2 - rowW) / 2;
      arr.forEach((n) => {
        n.x = startX + n.col * (NW + GX);
        n.y = PAD + li * (NH + GY);
      });
    });

    // --- link paralel (dua garis di pasangan node yang sama) digeser ---
    const groups = {};
    links.forEach((k) => {
      const key = [k.a, k.b].sort().join("|");
      (groups[key] = groups[key] || []).push(k);
    });
    Object.keys(groups).forEach((key) => {
      const g = groups[key];
      g.forEach((k, i) => { k.off = (i - (g.length - 1) / 2) * 16; });
    });

    let hasSameLayer = false;
    let svgLinks = "";

    links.forEach((k) => {
      const A = byId[k.a];
      const B = byId[k.b];
      let d, lx, ly;

      if (A.layer === B.layer) {
        hasSameLayer = true;
        const x1 = A.x + NW / 2 + k.off;
        const x2 = B.x + NW / 2 + k.off;
        const y = A.y + NH;
        const dip = 30 + Math.abs(A.col - B.col) * 6;
        d = "M" + x1 + " " + y + " Q" + (x1 + x2) / 2 + " " + (y + dip * 2) + " " + x2 + " " + y;
        lx = (x1 + x2) / 2;
        ly = y + dip;
      } else {
        const up = A.layer < B.layer ? A : B;
        const lo = A.layer < B.layer ? B : A;
        const x1 = up.x + NW / 2 + k.off;
        const y1 = up.y + NH;
        const x2 = lo.x + NW / 2 + k.off;
        const y2 = lo.y;
        d = "M" + x1 + " " + y1 + " L" + x2 + " " + y2;
        lx = (x1 + x2) / 2;
        ly = (y1 + y2) / 2;
      }

      const cls = "topo-link" + (k.kind === "==" ? " topo-thick" : k.kind === "-.-" ? " topo-dash" : "");
      svgLinks += '<path class="' + cls + '" d="' + d + '"/>';

      if (k.label) {
        const text = k.label.length > 24 ? k.label.slice(0, 23) + "…" : k.label;
        const w = text.length * 6.4 + 12;
        svgLinks +=
          '<rect class="topo-label-bg" x="' + (lx - w / 2) + '" y="' + (ly - 9) +
          '" width="' + w + '" height="18" rx="5"/>' +
          '<text class="topo-label" x="' + lx + '" y="' + ly + '">' + escapeHtml(text) + "</text>";
      }
    });

    let svgNodes = "";
    nodes.forEach((n) => {
      const label = n.label.length > 18 ? n.label.slice(0, 17) + "…" : n.label;
      svgNodes +=
        '<g class="topo-node topo-' + n.type + '">' +
        '<rect x="' + n.x + '" y="' + n.y + '" width="' + NW + '" height="' + NH + '" rx="10"/>' +
        '<text class="topo-name" x="' + (n.x + NW / 2) + '" y="' + (n.y + 21) + '">' + escapeHtml(label) + "</text>" +
        '<text class="topo-type" x="' + (n.x + NW / 2) + '" y="' + (n.y + 39) + '">' + TOPO_TYPES[n.type] + "</text>" +
        "</g>";
    });

    const H = PAD * 2 + layers.length * NH + (layers.length - 1) * GY + (hasSameLayer ? 70 : 8);

    return (
      '<div class="code-block topo-block">' +
      '<div class="code-header"><span class="code-lang">topologi</span></div>' +
      '<div class="topo-scroll">' +
      '<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Diagram topologi jaringan" ' +
      'viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '">' +
      svgLinks + svgNodes +
      "</svg></div></div>"
    );
  }

  function codeBlockHtml(langRaw, code) {
    const lang = normalizeLang(langRaw);
    const label = langRaw ? langRaw.toLowerCase() : "kode";
    return (
      '<div class="code-block">' +
      '<div class="code-header">' +
      '<span class="code-lang">' + escapeHtml(label) + "</span>" +
      '<button type="button" class="code-copy" aria-label="Salin kode">Salin</button>' +
      "</div>" +
      "<pre><code" + (lang ? ' class="language-' + escapeHtml(lang) + '"' : "") + ">" +
      highlight(code, lang) +
      "</code></pre>" +
      "</div>"
    );
  }

  // ---------------------------------------------------------
  // Inline
  // ---------------------------------------------------------
  const TOKEN_RE = /\u0000(\d+)\u0000/g;

  function isSafeUrl(url) {
    return /^(https?:\/\/|mailto:)/i.test(url);
  }

  function fmt(s) {
    s = s.replace(/\*\*(?=\S)([\s\S]*?\S)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^*\w])\*([^\s*](?:[^*\n]*?[^\s*])?)\*(?![*\w])/g, "$1<em>$2</em>");
    s = s.replace(/~~(?=\S)([\s\S]*?\S)~~/g, "<del>$1</del>");
    return s;
  }

  function renderInline(raw) {
    const stash = [];
    const keep = (html) => {
      stash.push(html);
      return "\u0000" + (stash.length - 1) + "\u0000";
    };

    let s = escapeHtml(String(raw).replace(/\u0000/g, ""));

    // 1. inline code (isinya tidak diformat lagi)
    s = s.replace(/`([^`\n]+)`/g, (m, c) => keep("<code>" + c + "</code>"));

    // 2. [teks](url)
    s = s.replace(/\[([^\]\n]+)\]\(([^)\s]+)\)/g, (m, label, url) => {
      if (!isSafeUrl(url)) return m;
      return keep(
        '<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + fmt(label) + "</a>"
      );
    });

    // 3. bare URL
    s = s.replace(/(^|[\s(])(https?:\/\/[^\s<]+[^\s<.,;:!?)\]'"])/g, (m, pre, url) =>
      pre + keep('<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + url + "</a>")
    );

    // 4. bold / italic / strike
    s = fmt(s);

    // 5. kembalikan placeholder
    for (let n = 0; n < 4 && s.indexOf("\u0000") !== -1; n++) {
      s = s.replace(TOKEN_RE, (m, i) => stash[+i]);
    }
    return s;
  }

  // ---------------------------------------------------------
  // Blok
  // ---------------------------------------------------------
  const FENCE_RE = /^\s*(`{3,}|~{3,})\s*([\w+#.-]*)[^`]*$/;
  const HEADING_RE = /^\s{0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/;
  const HR_RE = /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/;
  const QUOTE_RE = /^\s{0,3}>\s?(.*)$/;
  const ITEM_RE = /^(\s*)([-*+]|\d{1,3}[.)])\s+(.*)$/;
  const TABLE_SEP_RE = /^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$/;

  function indentOf(line) {
    return line.match(/^[ \t]*/)[0].replace(/\t/g, "    ").length;
  }

  function isTableStart(lines, i) {
    return (
      i + 1 < lines.length &&
      lines[i].indexOf("|") !== -1 &&
      lines[i + 1].indexOf("|") !== -1 &&
      TABLE_SEP_RE.test(lines[i + 1])
    );
  }

  function isBlockStart(lines, i) {
    const line = lines[i];
    return (
      FENCE_RE.test(line) ||
      HEADING_RE.test(line) ||
      HR_RE.test(line) ||
      QUOTE_RE.test(line) ||
      ITEM_RE.test(line) ||
      isTableStart(lines, i)
    );
  }

  function splitRow(line) {
    let t = line.trim();
    if (t.charAt(0) === "|") t = t.slice(1);
    if (t.charAt(t.length - 1) === "|" && t.charAt(t.length - 2) !== "\\") t = t.slice(0, -1);
    const cells = [];
    let cur = "";
    for (let i = 0; i < t.length; i++) {
      const ch = t.charAt(i);
      if (ch === "\\" && t.charAt(i + 1) === "|") {
        cur += "|";
        i++;
      } else if (ch === "|") {
        cells.push(cur.trim());
        cur = "";
      } else {
        cur += ch;
      }
    }
    cells.push(cur.trim());
    return cells;
  }

  function parseTable(lines, start) {
    const header = splitRow(lines[start]);
    const aligns = splitRow(lines[start + 1]).map((c) => {
      const left = c.charAt(0) === ":";
      const right = c.charAt(c.length - 1) === ":";
      return left && right ? "center" : right ? "right" : left ? "left" : "";
    });
    const cols = header.length;

    let i = start + 2;
    const rows = [];
    while (i < lines.length && lines[i].trim() && lines[i].indexOf("|") !== -1) {
      const cells = splitRow(lines[i]);
      while (cells.length < cols) cells.push("");
      rows.push(cells.slice(0, cols));
      i++;
    }

    const cls = (k) => (aligns[k] ? ' class="align-' + aligns[k] + '"' : "");
    let html = '<div class="table-wrap"><table><thead><tr>';
    header.forEach((h, k) => { html += "<th" + cls(k) + ">" + renderInline(h) + "</th>"; });
    html += "</tr></thead>";
    if (rows.length) {
      html += "<tbody>";
      rows.forEach((r) => {
        html += "<tr>";
        r.forEach((c, k) => { html += "<td" + cls(k) + ">" + renderInline(c) + "</td>"; });
        html += "</tr>";
      });
      html += "</tbody>";
    }
    html += "</table></div>";
    return { html: html, next: i };
  }

  function parseList(lines, start) {
    const first = lines[start].match(ITEM_RE);
    const baseIndent = indentOf(lines[start]);
    const ordered = /^\d/.test(first[2]);
    const startNum = ordered ? parseInt(first[2], 10) : 1;
    const items = [];
    let i = start;

    while (i < lines.length) {
      const line = lines[i];

      if (!line.trim()) {
        // Baris kosong di antara item (loose list) tidak memutus list.
        let j = i + 1;
        while (j < lines.length && !lines[j].trim()) j++;
        if (j < lines.length && ITEM_RE.test(lines[j]) && indentOf(lines[j]) >= baseIndent) {
          i = j;
          continue;
        }
        break;
      }

      if (FENCE_RE.test(line)) break;

      const m = line.match(ITEM_RE);
      const ind = indentOf(line);

      if (!m) {
        if (items.length && ind > baseIndent && !HEADING_RE.test(line) && !QUOTE_RE.test(line)) {
          items[items.length - 1].text += " " + line.trim();
          i++;
          continue;
        }
        break;
      }

      if (ind < baseIndent) break;

      if (ind > baseIndent) {
        if (!items.length) break;
        const nested = parseList(lines, i);
        items[items.length - 1].children.push(nested.html);
        i = nested.next;
        continue;
      }

      if (/^\d/.test(m[2]) !== ordered) break;
      items.push({ text: m[3], children: [] });
      i++;
    }

    const tag = ordered ? "ol" : "ul";
    const attr = ordered && startNum !== 1 ? ' start="' + startNum + '"' : "";
    const CHECK_RE = /^\[([ xX]?)\]\s+(.*)$/;
    const body = items
      .map((it) => {
        const c = it.text.match(CHECK_RE);
        if (c) {
          const done = c[1].toLowerCase() === "x";
          return (
            '<li class="md-check' + (done ? " done" : "") + '">' +
            '<input type="checkbox" disabled' + (done ? " checked" : "") + "> " +
            renderInline(c[2]) + it.children.join("") + "</li>"
          );
        }
        return "<li>" + renderInline(it.text) + it.children.join("") + "</li>";
      })
      .join("");
    return { html: "<" + tag + attr + ">" + body + "</" + tag + ">", next: i };
  }

  function renderBlocks(lines) {
    const out = [];
    let i = 0;

    while (i < lines.length) {
      const line = lines[i];

      if (!line.trim()) { i++; continue; }

      // --- fenced code
      const f = line.match(FENCE_RE);
      if (f) {
        const marker = f[1];
        const lang = f[2] || "";
        const lead = line.match(/^ */)[0].length;
        const closeRe = new RegExp("^\\s*\\" + marker.charAt(0) + "{" + marker.length + ",}\\s*$");
        const code = [];
        i++;
        while (i < lines.length && !closeRe.test(lines[i])) {
          let l = lines[i];
          let strip = 0;
          while (strip < lead && l.charAt(strip) === " ") strip++;
          code.push(l.slice(strip));
          i++;
        }
        i++; // lewati penutup (atau lewat akhir jika belum tertutup / masih streaming)

        // ```topology -> diagram jaringan. Jika belum ada node (mis. masih
        // streaming) topologyHtml() mengembalikan null -> tampil sebagai kode.
        if (lang.toLowerCase() === "topology") {
          const topo = topologyHtml(code.join("\n"));
          if (topo) {
            out.push(topo);
            continue;
          }
        }

        out.push(codeBlockHtml(lang, code.join("\n")));
        continue;
      }

      // --- heading
      const h = line.match(HEADING_RE);
      if (h) {
        const level = h[1].length;
        out.push("<h" + level + ">" + renderInline(h[2]) + "</h" + level + ">");
        i++;
        continue;
      }

      // --- hr
      if (HR_RE.test(line)) {
        out.push("<hr>");
        i++;
        continue;
      }

      // --- blockquote
      if (QUOTE_RE.test(line)) {
        const inner = [];
        while (i < lines.length && QUOTE_RE.test(lines[i])) {
          inner.push(lines[i].match(QUOTE_RE)[1]);
          i++;
        }
        out.push("<blockquote>" + renderBlocks(inner) + "</blockquote>");
        continue;
      }

      // --- tabel
      if (isTableStart(lines, i)) {
        const t = parseTable(lines, i);
        out.push(t.html);
        i = t.next;
        continue;
      }

      // --- list
      if (ITEM_RE.test(line)) {
        const l = parseList(lines, i);
        out.push(l.html);
        i = l.next;
        continue;
      }

      // --- paragraf
      const buf = [line.trim()];
      i++;
      while (i < lines.length && lines[i].trim() && !isBlockStart(lines, i)) {
        buf.push(lines[i].trim());
        i++;
      }
      out.push("<p>" + buf.map(renderInline).join("<br>") + "</p>");
    }

    return out.join("");
  }

  function render(raw) {
    try {
      const text = String(raw || "").replace(/\r\n?/g, "\n");
      return renderBlocks(text.split("\n"));
    } catch (err) {
      // Jaring pengaman: tampilkan teks apa adanya, jangan pernah blank.
      return "<p>" + escapeHtml(String(raw || "")).replace(/\n/g, "<br>") + "</p>";
    }
  }

  // ---------------------------------------------------------
  // Tombol Salin (event delegation: innerHTML di-render ulang tiap chunk)
  // ---------------------------------------------------------
  function copyText(text) {
    if (root.navigator && navigator.clipboard && root.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    // http://IP-LAPTOP:8000 bukan secure context -> pakai fallback lama.
    return new Promise(function (resolve, reject) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy") ? resolve() : reject(new Error("copy failed"));
      } catch (e) {
        reject(e);
      } finally {
        document.body.removeChild(ta);
      }
    });
  }

  if (typeof document !== "undefined") {
    document.addEventListener("click", function (e) {
      const btn = e.target.closest && e.target.closest(".code-copy");
      if (!btn) return;
      const block = btn.closest(".code-block");
      const codeEl = block && block.querySelector("pre code");
      if (!codeEl) return;

      copyText(codeEl.textContent).then(
        function () { flash(btn, "Tersalin ✓"); },
        function () { flash(btn, "Gagal"); }
      );
    });
  }

  function flash(btn, label) {
    btn.textContent = label;
    clearTimeout(btn._t);
    btn._t = setTimeout(function () { btn.textContent = "Salin"; }, 1500);
  }

  root.RinMarkdown = { render: render, renderInline: renderInline, highlight: highlight };
  if (typeof module !== "undefined" && module.exports) module.exports = root.RinMarkdown;
})();
