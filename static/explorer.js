/* 대화형 허가데이터 탐색기 — 외부 라이브러리 없음, DOM API 만 사용.
   보안: 값 삽입은 전부 textContent. innerHTML 은 쓰지 않는다. */
(function () {
  "use strict";

  var D = null;          // 디코딩된 데이터셋
  var N = 0;             // 전체 행 수
  var COLS = [];
  var state = { facets: {}, q: "", y0: null, y1: null, sortDesc: true, page: 0 };
  var PAGE = 50;
  /* 무지개 색상 — src/mfds_insight/colors.py 와 같은 알고리즘(값을 바꾸면 양쪽 모두 수정).
     빨→보라 7색을 기준점으로 n등분하고, 흰 배경 대비 3.2:1 이상이 될 때까지 명도를 낮춘다. */
  var ANCHOR_HUES = [0, 28, 48, 130, 205, 235, 280], SAT = 0.68, L0 = 0.50, MIN_CONTRAST = 3.2;
  function hlsToRgb(h, l, s) {                        // Python colorsys.hls_to_rgb 와 동일
    if (s === 0) return [l, l, l];
    var m2 = l <= 0.5 ? l * (1 + s) : l + s - l * s, m1 = 2 * l - m2;
    function v(hh) {
      hh = ((hh % 1) + 1) % 1;
      if (hh < 1 / 6) return m1 + (m2 - m1) * hh * 6;
      if (hh < 0.5) return m2;
      if (hh < 2 / 3) return m1 + (m2 - m1) * (2 / 3 - hh) * 6;
      return m1;
    }
    return [v(h + 1 / 3), v(h), v(h - 1 / 3)];
  }
  function toHex(rgb) {
    return "#" + rgb.map(function (x) {
      var n = Math.round(x * 255);
      return (n < 16 ? "0" : "") + n.toString(16).toUpperCase();
    }).join("");
  }
  function contrastOnWhite(hex) {
    var c = [1, 3, 5].map(function (i) { return parseInt(hex.substr(i, 2), 16) / 255; })
      .map(function (x) { return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); });
    return 1.05 / (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2] + 0.05);
  }
  function hueAt(t) {
    var x = t * (ANCHOR_HUES.length - 1), i = Math.min(Math.floor(x), ANCHOR_HUES.length - 2), f = x - i;
    return ANCHOR_HUES[i] + (ANCHOR_HUES[i + 1] - ANCHOR_HUES[i]) * f;
  }
  function rainbow(n) {
    var out = [];
    for (var i = 0; i < n; i++) {
      var h = hueAt(n > 1 ? i / (n - 1) : 0) / 360, hx, steps = 0;
      while (true) {
        hx = toHex(hlsToRgb(h, L0 - steps * 0.005, SAT));
        if (contrastOnWhite(hx) >= MIN_CONTRAST || steps >= 60) break;
        steps++;
      }
      out.push(hx);
    }
    return out;
  }
  // colors.series_colors 와 동일. 탐색기 차트는 모두 지표 하나(연도별·업체별)라 kind="single".
  function seriesColors(n) {
    var c = (D && D.meta.colors) || { scheme: "accent", base: "#1F3864" };
    var out = [], i;
    if (c.scheme === "rainbow") return rainbow(n);
    if (c.scheme === "palette" && c.palette && c.palette.length) {
      for (i = 0; i < n; i++) out.push(c.palette[i % c.palette.length]);
      return out;
    }
    for (i = 0; i < n; i++) out.push(c.base || "#1F3864");
    return out;
  }

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function fmt(n) { return Number(n).toLocaleString("ko-KR"); }
  // 표 표시용: 날짜 구분자, 줄바꿈 금지 열. CSV 내려받기는 원본 값을 유지한다.
  var DATE_COLS = { "허가일자": 1, "취소취하일자": 1, "변경일자": 1 };
  var NOWRAP = { "허가일자": 1, "취소취하일자": 1, "변경일자": 1, "허가번호": 1,
                 "제조수입구분": 1, "품목상태": 1, "추적관리대상": 1 };
  function cell(col, v) {
    v = v || "";
    return DATE_COLS[col] && /^\d{8}$/.test(v) ? v.slice(0, 4) + "-" + v.slice(4, 6) + "-" + v.slice(6) : v;
  }

  /* ---------- 로딩 ---------- */
  function decode(enc) {
    if (enc.kind === "dict") {
      var d = enc.dict;
      return enc.data.map(function (i) { return d[i]; });
    }
    return enc.data;
  }

  function load() {
    fetch("data.json", { credentials: "omit" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (raw) {
        D = { meta: raw, col: {} };
        COLS = raw.columns;
        COLS.forEach(function (c) { D.col[c] = decode(raw.encoded[c]); });
        if (raw.encoded["_연도"]) D.col["_연도"] = raw.encoded["_연도"].data;
        N = COLS.length ? D.col[COLS[0]].length : 0;
        init();
      })
      .catch(function (e) {
        var box = $("status");
        clear(box);
        if (location.protocol === "file:") {
          box.appendChild(el("p", "err",
            "로컬 파일(file://)로 열어서 데이터를 읽을 수 없습니다."));
          box.appendChild(el("p", "err",
            "명령 프롬프트에서 python run.py serve 를 실행한 뒤, " +
            "http://localhost:8000/explore/ 로 접속하십시오."));
        } else {
          box.appendChild(el("p", "err", "데이터를 불러오지 못했습니다: " + e.message));
        }
      });
  }

  /* ---------- 필터 UI ---------- */
  /* 필터 키: merge_spacing 컬럼은 띄어쓰기를 지워 같은 품목으로 묶는다(표 표시는 원본). */
  var MERGE = {};
  function fkey(col, v) {
    v = v || "(없음)";
    return MERGE[col] ? v.replace(/\s+/g, "") : v;
  }
  function uniqueSorted(col) {
    var seen = Object.create(null), out = [];
    var a = D.col[col];
    for (var i = 0; i < a.length; i++) {
      var v = fkey(col, a[i]);
      if (!seen[v]) { seen[v] = 1; out.push(v); }
    }
    return out.sort(function (x, y) { return x.localeCompare(y, "ko"); });
  }

  function init() {
    var m = D.meta;
    (m.merge_spacing || []).forEach(function (c) { MERGE[c] = 1; });
    var host = $("filters");
    clear(host);

    // 텍스트 검색
    if (m.search && m.search.length) {
      var g = el("div", "fgroup");
      var sl = el("label", "flabel", m.search.join(" · ") + " 검색"); sl.htmlFor = "q"; g.appendChild(sl);
      var inp = el("input");
      inp.type = "search"; inp.id = "q";
      inp.placeholder = "예: 임플란트";
      inp.addEventListener("input", function () {
        state.q = inp.value.trim();
        state.page = 0;
        render();
      });
      g.appendChild(inp);
      host.appendChild(g);
    }

    // 패싯(체크박스)
    (m.facets || []).forEach(function (c) {
      var vals = uniqueSorted(c);
      if (vals.length > 30) return;              // 값이 너무 많으면 셀렉트로
      var g = el("div", "fgroup");
      g.appendChild(el("span", "flabel", c));
      var box = el("div", "chips");
      state.facets[c] = {};
      vals.forEach(function (v) {
        var id = "f_" + c + "_" + v;
        var wrap = el("label", "chip");
        var cb = el("input");
        cb.type = "checkbox"; cb.id = id;
        cb.addEventListener("change", function () {
          state.facets[c][v] = cb.checked;
          state.page = 0;
          render();
        });
        wrap.appendChild(cb);
        wrap.appendChild(el("span", null, v));
        box.appendChild(wrap);
      });
      g.appendChild(box);
      host.appendChild(g);
    });

    // 값이 많은 컬럼은 드롭다운
    (m.facets || []).forEach(function (c) {
      var vals = uniqueSorted(c);
      if (vals.length <= 30) return;
      var g = el("div", "fgroup");
      var sid = "s_" + c; var ll = el("label", "flabel", c); ll.htmlFor = sid; g.appendChild(ll);
      var sel = el("select"); sel.id = sid;
      sel.appendChild(el("option", null, "(전체)"));
      vals.forEach(function (v) {
        var o = el("option", null, v); o.value = v; sel.appendChild(o);
      });
      sel.addEventListener("change", function () {
        state.facets[c] = {};
        if (sel.selectedIndex > 0) state.facets[c][sel.value] = true;
        state.page = 0;
        render();
      });
      state.facets[c] = {};
      g.appendChild(sel);
      host.appendChild(g);
    });

    // 연도 범위
    if (D.col["_연도"]) {
      var ys = D.col["_연도"].filter(function (y) { return y; });
      var min = Math.min.apply(null, ys), max = Math.max.apply(null, ys);
      state.y0 = min; state.y1 = max;
      var g2 = el("div", "fgroup");
      g2.appendChild(el("span", "flabel", "허가 연도"));
      var row = el("div", "yrow");
      function mk(isStart) {
        var lab = el("label", "ysel");
        lab.appendChild(el("span", null, isStart ? "시작" : "종료"));
        var sel = el("select");
        for (var y = min; y <= max; y++) {
          var o = el("option", null, y + "년"); o.value = y; sel.appendChild(o);
        }
        sel.value = isStart ? min : max;
        sel.addEventListener("change", function () {
          var v = parseInt(sel.value, 10);
          if (isStart) { state.y0 = v; if (state.y1 < v) { state.y1 = v; endSel.value = v; } }
          else { state.y1 = v; if (state.y0 > v) { state.y0 = v; startSel.value = v; } }
          state.page = 0;
          render();
        });
        lab.appendChild(sel);
        row.appendChild(lab);
        return sel;
      }
      var startSel = mk(true);
      row.appendChild(el("span", "ydash", "~"));
      var endSel = mk(false);
      g2.appendChild(row);
      host.appendChild(g2);
    }

    var reset = el("button", "reset", "필터 초기화");
    reset.addEventListener("click", function () { location.reload(); });
    host.appendChild(reset);

    render();
  }

  /* ---------- 필터 적용 ---------- */
  function activeFacets() {
    var out = [];
    Object.keys(state.facets).forEach(function (c) {
      var on = Object.keys(state.facets[c]).filter(function (v) { return state.facets[c][v]; });
      if (on.length) out.push([c, on]);
    });
    return out;
  }

  function filteredIndex() {
    var facets = activeFacets();
    var q = state.q.toLowerCase();
    var searchCols = D.meta.search || [];
    var years = D.col["_연도"];
    var idx = [];
    for (var i = 0; i < N; i++) {
      var ok = true;
      for (var f = 0; f < facets.length && ok; f++) {
        var v = fkey(facets[f][0], D.col[facets[f][0]][i]);
        if (facets[f][1].indexOf(v) < 0) ok = false;
      }
      if (ok && years && years[i]) {
        if (years[i] < state.y0 || years[i] > state.y1) ok = false;
      }
      if (ok && q) {
        var hit = false;
        for (var s = 0; s < searchCols.length; s++) {
          var t = D.col[searchCols[s]][i];
          if (t && t.toLowerCase().indexOf(q) >= 0) { hit = true; break; }
        }
        ok = hit;
      }
      if (ok) idx.push(i);
    }
    return idx;
  }

  /* ---------- 차트 (SVG 직접 생성) ----------
     viewBox 를 실제 표시 폭(px)과 같게 잡아 1:1 로 그린다. 그래서 화면이 좁아도
     글자가 축소되지 않는다(FONT px 고정). 폭이 바뀌면 다시 그린다(onResize). */
  var SVGNS = "http://www.w3.org/2000/svg";
  var FONT = 13, INK = "#2b3440", GRID = "#e2e6ec";
  var measureCtx = null;
  function textWidth(str) {
    if (!measureCtx) {
      measureCtx = document.createElement("canvas").getContext("2d");
      measureCtx.font = FONT + "px " + getComputedStyle(document.body).fontFamily;
    }
    return measureCtx.measureText(str).width;
  }
  function svgEl(tag, attrs) {
    var e = document.createElementNS(SVGNS, tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    return e;
  }
  function svgText(x, y, str, anchor, opts) {
    opts = opts || {};
    var t = svgEl("text", { x: x, y: y, "text-anchor": anchor || "middle",
                            "font-size": opts.size || FONT, fill: opts.fill || INK });
    if (opts.weight) t.setAttribute("font-weight", opts.weight);
    t.textContent = str;
    return t;
  }
  function ellipsize(str, maxPx) {
    if (textWidth(str) <= maxPx) return str;
    var lo = 0, hi = str.length;
    while (lo < hi) {                              // 들어가는 최대 길이를 이분 탐색
      var mid = (lo + hi + 1) >> 1;
      if (textWidth(str.slice(0, mid) + "…") <= maxPx) lo = mid; else hi = mid - 1;
    }
    return str.slice(0, Math.max(1, lo)) + "…";
  }
  function niceTicks(max, n) {
    if (max <= 0) return [0];
    var raw = max / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    var step = [1, 2, 2.5, 5, 10].map(function (k) { return k * mag; })
      .filter(function (s) { return s >= raw; })[0];
    step = Math.max(1, Math.round(step));
    var out = [];
    for (var v = 0; v <= max + 1e-9; v += step) out.push(v);
    if (out[out.length - 1] < max) out.push(out[out.length - 1] + step);
    return out;
  }
  function widthOf(host) { return Math.max(260, Math.floor(host.clientWidth || 600)); }
  function newSvg(W, H, label) {
    return svgEl("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H,
                          role: "img", "aria-label": label });
  }
  function chartHead(host, title) {
    clear(host);
    host.appendChild(el("h3", null, title));
  }

  function barChart(host, pairs, title, partial) {
    chartHead(host, title);
    if (!pairs.length) { host.appendChild(el("p", "muted", "데이터 없음")); return; }
    var W = widthOf(host), H = W < 560 ? 230 : 280;
    var max = Math.max.apply(null, pairs.map(function (p) { return p[1]; })) || 1;
    var ticks = niceTicks(max, 4), top = ticks[ticks.length - 1];
    var P = { l: Math.ceil(textWidth(fmt(top))) + 12, r: 8, t: 10, b: 28 };
    var svg = newSvg(W, H, title);
    var colors = seriesColors(pairs.length);
    var ih = H - P.t - P.b, iw = W - P.l - P.r;
    ticks.forEach(function (t) {
      var y = H - P.b - ih * (t / top);
      svg.appendChild(svgEl("line", { x1: P.l, y1: y, x2: W - P.r, y2: y, stroke: GRID }));
      svg.appendChild(svgText(P.l - 6, y + 4, fmt(t), "end"));
    });
    var bw = iw / pairs.length;
    // 눈금 글자가 겹치지 않도록 간격(px)에 맞춰 1·2·5·10년 단위로 띄운다.
    var need = textWidth("2026*") + 10;
    var step = [1, 2, 5, 10, 20].filter(function (k) { return bw * k >= need; })[0] || 20;
    pairs.forEach(function (p, i) {
      var isPartial = partial && String(partial.year) === p[0];
      var h = ih * (p[1] / top), x = P.l + i * bw, y = H - P.b - h;
      var fill = colors[i];
      if (isPartial) {                               // 같은 색 + 흰 빗금(색 외 구분 수단)
        var defs = svgEl("defs"), pat = svgEl("pattern", { id: "hatch", width: 6, height: 6,
          patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" });
        pat.appendChild(svgEl("rect", { width: 6, height: 6, fill: colors[i], "fill-opacity": 0.85 }));
        pat.appendChild(svgEl("line", { x1: 0, y1: 0, x2: 0, y2: 6, stroke: "#fff", "stroke-width": 2 }));
        defs.appendChild(pat); svg.appendChild(defs);
        fill = "url(#hatch)";
      }
      var r = svgEl("rect", { x: x + bw * 0.14, y: y, width: Math.max(bw * 0.72, 1),
                              height: Math.max(h, 1), rx: 2, fill: fill });
      var ttl = svgEl("title");
      ttl.textContent = p[0] + "년: " + fmt(p[1]) + "건" +
        (isPartial ? " (" + partial.through_month + "월까지 집계)" : "");
      r.appendChild(ttl);
      svg.appendChild(r);
      if (+p[0] % step === 0 || (isPartial && bw >= need)) {
        svg.appendChild(svgText(x + bw / 2, H - P.b + 18, p[0] + (isPartial ? "*" : "")));
      }
    });
    svg.appendChild(svgEl("line", { x1: P.l, y1: H - P.b, x2: W - P.r, y2: H - P.b, stroke: "#9aa3ae" }));
    host.appendChild(svg);
    if (partial && pairs.some(function (p) { return String(partial.year) === p[0]; })) {
      host.appendChild(el("p", "fine", "* " + partial.year + "년은 " + partial.through_month +
        "월까지의 허가분만 집계되어 다른 해와 직접 비교할 수 없습니다(빗금 막대)."));
    }
  }

  function hbarChart(host, pairs, title) {
    chartHead(host, title);
    if (!pairs.length) { host.appendChild(el("p", "muted", "데이터 없음")); return; }
    var W = widthOf(host), max = pairs[0][1] || 1;
    var valW = textWidth(fmt(max)) + 10;
    var longest = Math.max.apply(null, pairs.map(function (p) { return textWidth(p[0]); }));
    // 이름 칸은 실제 이름 폭에 맞추되 최대 40%. 그보다 좁은 화면에서는 이름을 막대 위에 둔다.
    var stacked = W < 560 && longest > W * 0.4;
    var rowH = stacked ? 46 : 28, L = stacked ? 0 : Math.min(Math.ceil(longest) + 12, W * 0.4);
    var H = pairs.length * rowH + 6;
    var svg = newSvg(W, H, title), colors = seriesColors(pairs.length);
    pairs.forEach(function (p, i) {
      var y0 = i * rowH + 4;
      var barY = stacked ? y0 + 20 : y0 + 5, barH = stacked ? 16 : 18;
      var w = (W - L - valW) * (p[1] / max);
      var name = stacked ? ellipsize(p[0], W - 4) : ellipsize(p[0], L - 10);
      svg.appendChild(stacked ? svgText(0, y0 + 14, name, "start", { fill: "#16202e" })
                              : svgText(L - 8, barY + 14, name, "end"));
      var r = svgEl("rect", { x: L, y: barY, width: Math.max(w, 1), height: barH,
                              fill: colors[i], rx: 2 });
      var ttl = svgEl("title"); ttl.textContent = p[0] + ": " + fmt(p[1]) + "건";
      r.appendChild(ttl);
      svg.appendChild(r);
      svg.appendChild(svgText(L + w + 6, barY + 14, fmt(p[1]), "start"));
    });
    host.appendChild(svg);
  }

  /* 품목 상태: 그래프 대신 건수·비율 */
  function statusCards(host, pairs, title) {
    clear(host);
    if (!pairs.length) return;
    host.appendChild(el("h3", null, title));
    var total = pairs.reduce(function (a, p) { return a + p[1]; }, 0) || 1;
    var box = el("div", "kpis status");
    pairs.forEach(function (p) {
      var d = el("div", "kpi" + (p[0] === "정상" ? "" : " alt"));
      var n = el("div", "n", fmt(p[1])); n.appendChild(el("span", "u", "건"));
      d.appendChild(n);
      d.appendChild(el("div", "l", p[0] + " · " + (p[1] / total * 100).toFixed(1) + "%"));
      box.appendChild(d);
    });
    host.appendChild(box);
  }

  /* ---------- 집계 ---------- */
  function countBy(idx, col, topN) {
    var m = Object.create(null), a = D.col[col];
    for (var i = 0; i < idx.length; i++) {
      var v = a[idx[i]] || "(없음)";
      m[v] = (m[v] || 0) + 1;
    }
    var out = Object.keys(m).map(function (k) { return [k, m[k]]; });
    out.sort(function (x, y) { return y[1] - x[1]; });
    return topN ? out.slice(0, topN) : out;
  }

  function countByYear(idx) {
    var y = D.col["_연도"];
    if (!y) return [];
    var m = Object.create(null);
    for (var i = 0; i < idx.length; i++) {
      var v = y[idx[i]];
      if (v) m[v] = (m[v] || 0) + 1;
    }
    return Object.keys(m).map(Number).sort(function (a, b) { return a - b; })
      .map(function (k) { return [String(k), m[k]]; });
  }

  /* ---------- 표 ---------- */
  function renderTable(idx) {
    var host = $("table-host");
    clear(host);
    var sorted = idx.slice();
    var y = D.col["_연도"];
    if (y) sorted.sort(function (a, b) { return (state.sortDesc ? 1 : -1) * ((y[b] || 0) - (y[a] || 0)); });

    var pages = Math.max(1, Math.ceil(sorted.length / PAGE));
    if (state.page >= pages) state.page = pages - 1;
    var slice = sorted.slice(state.page * PAGE, (state.page + 1) * PAGE);

    var tbl = el("table", "data");
    var thead = el("thead"), trh = el("tr");
    COLS.forEach(function (c) {
      var th = el("th", NOWRAP[c] ? "nw" : null, c); th.scope = "col"; trh.appendChild(th);
    });
    thead.appendChild(trh); tbl.appendChild(thead);
    var tb = el("tbody");
    slice.forEach(function (i) {
      var tr = el("tr");
      COLS.forEach(function (c) { tr.appendChild(el("td", NOWRAP[c] ? "nw" : null, cell(c, D.col[c][i]))); });
      tb.appendChild(tr);
    });
    tbl.appendChild(tb);
    var scroll = el("div", "scroll"); scroll.appendChild(tbl);
    scroll.tabIndex = 0; scroll.setAttribute("role", "region");
    scroll.setAttribute("aria-label", "허가 목록 표 (가로로 스크롤)");
    host.appendChild(scroll);

    var nav = el("div", "pager");
    function btn(label, delta, disabled) {
      var b = el("button", null, label);
      b.disabled = disabled;
      b.addEventListener("click", function () { state.page += delta; render(); });
      return b;
    }
    nav.appendChild(btn("◀ 이전", -1, state.page === 0));
    nav.appendChild(el("span", null, (state.page + 1) + " / " + pages));
    nav.appendChild(btn("다음 ▶", 1, state.page >= pages - 1));
    var dl = el("button", "dl", "현재 조건 CSV 내려받기");
    dl.addEventListener("click", function () { exportCsv(sorted); });
    nav.appendChild(dl);
    host.appendChild(nav);
  }

  function exportCsv(idx) {
    var lines = [COLS.join(",")];
    for (var k = 0; k < idx.length; k++) {
      var i = idx[k];
      lines.push(COLS.map(function (c) {
        var v = D.col[c][i] || "";
        return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
      }).join(","));
    }
    var blob = new Blob(["\uFEFF" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "허가데이터_필터결과.csv";
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  }

  /* ---------- 렌더 ---------- */
  function render() {
    var t0 = performance.now();
    var idx = filteredIndex();

    var kp = $("kpis"); clear(kp);
    function kpi(n, l) {
      var d = el("div", "kpi");
      d.appendChild(el("div", "n", n));
      d.appendChild(el("div", "l", l));
      return d;
    }
    kp.appendChild(kpi(fmt(idx.length), "선택된 허가 건수"));
    var comps = D.col["업체명"] ? countBy(idx, "업체명") : [];
    if (comps.length) {
      kp.appendChild(kpi(fmt(comps.length), "업체 수"));
      var top3 = comps.slice(0, 3).reduce(function (a, p) { return a + p[1]; }, 0);
      kp.appendChild(kpi(idx.length ? (top3 / idx.length * 100).toFixed(1) + "%" : "–", "상위 3개사 점유"));
    }
    var ys = countByYear(idx);
    if (ys.length) {
      var peak = ys.reduce(function (a, p) { return p[1] > a[1] ? p : a; }, ys[0]);
      kp.appendChild(kpi(peak[0], "최다 허가 연도 (" + fmt(peak[1]) + "건)"));
    }

    last = { ys: ys, comps: comps };
    drawCharts();
    if (D.col["품목상태"]) statusCards($("chart-status"), countBy(idx, "품목상태"), "품목 상태");
    renderTable(idx);

    var st = $("status"); clear(st);
    st.appendChild(el("span", null,
      "전체 " + fmt(N) + "건 중 " + fmt(idx.length) + "건 선택 · " +
      (performance.now() - t0).toFixed(0) + "ms" +
      (D.meta.truncated ? " · 원본 " + fmt(D.meta.total_all) + "건 중 최신분만 수록" : "")));
  }

  /* 차트는 폭에 맞춰 그리므로, 창 크기·화면 회전 시 다시 그린다(집계는 재사용). */
  var last = null, rafId = 0, lastW = 0;
  function drawCharts() {
    if (!last) return;
    barChart($("chart-year"), last.ys, "연도별 허가 건수", D.meta.partial_year);
    if (D.col["업체명"]) hbarChart($("chart-company"), last.comps.slice(0, 12), "업체별 허가 건수 (상위 12)");
    lastW = $("chart-year").clientWidth;
  }
  window.addEventListener("resize", function () {
    cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(function () {
      if ($("chart-year").clientWidth !== lastW) drawCharts();
    });
  });

  document.addEventListener("DOMContentLoaded", load);
})();
