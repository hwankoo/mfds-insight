/* 대화형 허가데이터 탐색기 — 외부 라이브러리 없음, DOM API 만 사용.
   보안: 값 삽입은 전부 textContent. innerHTML 은 쓰지 않는다. */
(function () {
  "use strict";

  var D = null;          // 디코딩된 데이터셋
  var N = 0;             // 전체 행 수
  var COLS = [];
  var state = { facets: {}, q: "", y0: null, y1: null, sortDesc: true, page: 0 };
  var PAGE = 50;
  var PALETTE = ["#1F3864", "#2E5C9A", "#5B8FD4", "#9DBFE8", "#C9D9EE", "#8C8C8C"];

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function fmt(n) { return Number(n).toLocaleString("ko-KR"); }

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
  function uniqueSorted(col) {
    var seen = Object.create(null), out = [];
    var a = D.col[col];
    for (var i = 0; i < a.length; i++) {
      var v = a[i] || "(없음)";
      if (!seen[v]) { seen[v] = 1; out.push(v); }
    }
    return out.sort(function (x, y) { return x.localeCompare(y, "ko"); });
  }

  function init() {
    var m = D.meta;
    var host = $("filters");
    clear(host);

    // 텍스트 검색
    if (m.search && m.search.length) {
      var g = el("div", "fgroup");
      g.appendChild(el("label", null, m.search.join(" · ") + " 검색"));
      var inp = el("input");
      inp.type = "search";
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
      g.appendChild(el("label", null, c));
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
      g.appendChild(el("label", null, c));
      var sel = el("select");
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
      g2.appendChild(el("label", null, "허가 연도"));
      var row = el("div", "yrow");
      var out = el("span", "yval", min + " – " + max);
      function mk(isStart) {
        var s = el("input");
        s.type = "range"; s.min = min; s.max = max;
        s.value = isStart ? min : max;
        s.addEventListener("input", function () {
          var v = parseInt(s.value, 10);
          if (isStart) state.y0 = Math.min(v, state.y1);
          else state.y1 = Math.max(v, state.y0);
          out.textContent = state.y0 + " – " + state.y1;
          state.page = 0;
          render();
        });
        return s;
      }
      row.appendChild(mk(true));
      row.appendChild(mk(false));
      g2.appendChild(row);
      g2.appendChild(out);
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
        var v = D.col[facets[f][0]][i] || "(없음)";
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

  /* ---------- 차트 (SVG 직접 생성) ---------- */
  var SVGNS = "http://www.w3.org/2000/svg";
  function svgEl(tag, attrs) {
    var e = document.createElementNS(SVGNS, tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    return e;
  }
  function svgText(x, y, str, anchor, size) {
    var t = svgEl("text", { x: x, y: y, "text-anchor": anchor || "middle",
                            "font-size": size || 11, fill: "#4a5462" });
    t.textContent = str;
    return t;
  }

  function barChart(host, pairs, title) {
    clear(host);
    host.appendChild(el("h3", null, title));
    if (!pairs.length) { host.appendChild(el("p", "muted", "데이터 없음")); return; }
    var W = 640, H = 240, P = { l: 44, r: 12, t: 12, b: 30 };
    var svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H, role: "img" });
    var max = Math.max.apply(null, pairs.map(function (p) { return p[1]; })) || 1;
    var bw = (W - P.l - P.r) / pairs.length;
    pairs.forEach(function (p, i) {
      var h = (H - P.t - P.b) * (p[1] / max);
      var x = P.l + i * bw, y = H - P.b - h;
      var r = svgEl("rect", { x: x + bw * 0.15, y: y, width: bw * 0.7, height: Math.max(h, 1),
                              fill: PALETTE[0], rx: 2 });
      var ttl = svgEl("title"); ttl.textContent = p[0] + ": " + fmt(p[1]) + "건";
      r.appendChild(ttl);
      svg.appendChild(r);
      if (pairs.length <= 30 && (i % Math.ceil(pairs.length / 14) === 0)) {
        svg.appendChild(svgText(x + bw / 2, H - P.b + 14, p[0]));
      }
    });
    svg.appendChild(svgEl("line", { x1: P.l, y1: H - P.b, x2: W - P.r, y2: H - P.b, stroke: "#d7dce4" }));
    svg.appendChild(svgText(P.l - 6, P.t + 10, fmt(max), "end"));
    host.appendChild(svg);
  }

  function hbarChart(host, pairs, title) {
    clear(host);
    host.appendChild(el("h3", null, title));
    if (!pairs.length) { host.appendChild(el("p", "muted", "데이터 없음")); return; }
    var rowH = 22, W = 640, H = pairs.length * rowH + 16, L = 190;
    var svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H, role: "img" });
    var max = pairs[0][1] || 1;
    pairs.forEach(function (p, i) {
      var y = i * rowH + 8;
      var w = (W - L - 60) * (p[1] / max);
      svg.appendChild(svgText(L - 8, y + 12, p[0].length > 22 ? p[0].slice(0, 21) + "…" : p[0], "end"));
      var r = svgEl("rect", { x: L, y: y + 2, width: Math.max(w, 1), height: rowH - 8,
                              fill: PALETTE[1], rx: 2 });
      var ttl = svgEl("title"); ttl.textContent = p[0] + ": " + fmt(p[1]) + "건";
      r.appendChild(ttl);
      svg.appendChild(r);
      svg.appendChild(svgText(L + w + 6, y + 12, fmt(p[1]), "start"));
    });
    host.appendChild(svg);
  }

  function donut(host, pairs, title) {
    clear(host);
    host.appendChild(el("h3", null, title));
    var total = pairs.reduce(function (a, p) { return a + p[1]; }, 0);
    if (!total) { host.appendChild(el("p", "muted", "데이터 없음")); return; }
    var S = 220, R = 92, r0 = 52, cx = S / 2, cy = S / 2, a0 = -Math.PI / 2;
    var svg = svgEl("svg", { viewBox: "0 0 " + S + " " + S, role: "img" });
    pairs.forEach(function (p, i) {
      var a1 = a0 + (p[1] / total) * Math.PI * 2;
      var large = (a1 - a0) > Math.PI ? 1 : 0;
      var d = ["M", cx + R * Math.cos(a0), cy + R * Math.sin(a0),
               "A", R, R, 0, large, 1, cx + R * Math.cos(a1), cy + R * Math.sin(a1),
               "L", cx + r0 * Math.cos(a1), cy + r0 * Math.sin(a1),
               "A", r0, r0, 0, large, 0, cx + r0 * Math.cos(a0), cy + r0 * Math.sin(a0), "Z"].join(" ");
      var path = svgEl("path", { d: d, fill: PALETTE[i % PALETTE.length], stroke: "#fff", "stroke-width": 1.5 });
      var ttl = svgEl("title");
      ttl.textContent = p[0] + ": " + fmt(p[1]) + "건 (" + (p[1] / total * 100).toFixed(1) + "%)";
      path.appendChild(ttl);
      svg.appendChild(path);
      a0 = a1;
    });
    host.appendChild(svg);
    var lg = el("div", "legend");
    pairs.forEach(function (p, i) {
      var it = el("span", "lgi");
      var sw = el("i"); sw.style.background = PALETTE[i % PALETTE.length];
      it.appendChild(sw);
      it.appendChild(el("span", null, p[0] + " " + (p[1] / total * 100).toFixed(1) + "%"));
      lg.appendChild(it);
    });
    host.appendChild(lg);
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

    var tbl = el("table");
    var thead = el("thead"), trh = el("tr");
    COLS.forEach(function (c) { trh.appendChild(el("th", null, c)); });
    thead.appendChild(trh); tbl.appendChild(thead);
    var tb = el("tbody");
    slice.forEach(function (i) {
      var tr = el("tr");
      COLS.forEach(function (c) { tr.appendChild(el("td", null, D.col[c][i] || "")); });
      tb.appendChild(tr);
    });
    tbl.appendChild(tb);
    var scroll = el("div", "scroll"); scroll.appendChild(tbl);
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

    barChart($("chart-year"), ys, "연도별 허가 건수");
    if (D.col["품목상태"]) donut($("chart-status"), countBy(idx, "품목상태"), "품목 상태");
    else if (D.col["제조수입구분"]) donut($("chart-status"), countBy(idx, "제조수입구분"), "제조 · 수입");
    if (D.col["업체명"]) hbarChart($("chart-company"), comps.slice(0, 12), "업체별 허가 건수 (상위 12)");
    renderTable(idx);

    var st = $("status"); clear(st);
    st.appendChild(el("span", null,
      "전체 " + fmt(N) + "건 중 " + fmt(idx.length) + "건 선택 · " +
      (performance.now() - t0).toFixed(0) + "ms" +
      (D.meta.truncated ? " · 원본 " + fmt(D.meta.total_all) + "건 중 최신분만 수록" : "")));
  }

  document.addEventListener("DOMContentLoaded", load);
})();
