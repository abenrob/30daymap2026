/* The Vintages: wine across borders, 1962-2023. D3 v7. */
(async function () {
  const C = {
    cream: "#F4EEE1", parchment: "#EAE0CC", linen: "#D9CCB4", ink: "#2A1D19", inkSoft: "#6B5A50",
    bordeaux: "#6E1A2C", claret: "#9B3346", rose: "#D8A39D", oak: "#8A6748", cork: "#C4A783",
    gold: "#C9A646", goldDeep: "#A8862C", state: "#EFE6D3",
  };
  const CAT = { old: C.bordeaux, new: C.gold, other: C.oak };
  const CATNAME = { old: "Old World exporters", new: "New World exporters", other: "Elsewhere" };

  const [data, topo, land, fallback] = await Promise.all([
    d3.json("assets/wine_flows.json?v=1793966317"), d3.json("assets/countries.topo.json"),
    d3.json("assets/land.topo.json"), d3.json("assets/fallback_points.json"),
  ]);
  const nodes = data.nodes;
  nodes.forEach((n, i) => { n.i = i; });
  const byKey = new Map(nodes.map(n => [n.k, n]));
  const years = data.years;
  const Y0 = years[0], Y1 = years[years.length - 1];
  const states = topojson.feature(topo, Object.values(topo.objects)[0]).features;
  const landF = topojson.feature(land, Object.values(land.objects)[0]);

  // ---------- helpers
  const fmt = v => v >= 1e9 ? `${(v / 1e9).toFixed(v >= 1e10 ? 1 : 2)} bn litres`
    : v >= 1e6 ? `${Math.round(v / 1e6).toLocaleString("en")} m litres`
    : v >= 1e3 ? `${Math.round(v / 1e3).toLocaleString("en")} k litres` : `${Math.round(v)} litres`;
  const statesIn = y => states.filter(f => f.properties.y0 <= y && y <= f.properties.y1);
  function featureFor(n, y) {
    for (const g of n.gw) {
      const f = states.find(s => s.properties.gw === g && s.properties.y0 <= y && y <= s.properties.y1);
      if (f) return f;
    }
    return null;
  }
  function anchor(n, y) {
    const f = featureFor(n, y);
    if (f) return [f.properties.ax, f.properties.ay];
    return fallback[n.k] || null;
  }
  function nodeForFeature(f, y) {
    const g = f.properties.gw;
    return nodes.find(n => n.gw.includes(g) && n.y0 <= y && y <= n.y1) || null;
  }
  const flowsIn = y => (data.flows[y] || []).map(([e, i, l, est]) => ({ e, i, v: l, est }));

  // ---------- state
  const QS = new URLSearchParams(location.search);
  const CAPTURE = QS.has("capture");
  if (CAPTURE) document.body.classList.add("capture");
  let forcedDur = null;
  const hash = new URLSearchParams(location.hash.slice(1));
  let year = +hash.get("y") || Y0;
  let sel = hash.get("c") && byKey.has(hash.get("c")) ? byKey.get(hash.get("c")).i : null;
  let playing = false, timer = null, stepMs = 900;

  // ---------- controls
  const selectEl = d3.select("#country");
  [...nodes].filter(n => n.ex + n.im > 0).sort((a, b) => d3.ascending(a.n, b.n)).forEach(n => {
    selectEl.append("option").attr("value", n.k).text(`${n.n}${n.y0 > Y0 || n.y1 < Y1 ? ` (${n.y0}–${n.y1})` : ""}`);
  });
  selectEl.property("value", sel == null ? "" : nodes[sel].k).on("change", function () {
    sel = this.value ? byKey.get(this.value).i : null; render(true);
  });
  const slider = d3.select("#slider").attr("min", Y0).attr("max", Y1).property("value", year)
    .on("input", function () { year = +this.value; render(false); });
  d3.select("#play").on("click", () => playing ? stop() : play());
  d3.selectAll("#speed button").on("click", function () {
    d3.selectAll("#speed button").classed("on", false); d3.select(this).classed("on", true);
    stepMs = +this.dataset.ms; if (playing) { stop(); play(); }
  });
  function play() {
    if (year >= Y1) year = Y0;
    playing = true; d3.select("#play").text("Pause");
    render(false);
    timer = setInterval(() => {
      if (year >= Y1) { stop(); return; }
      year += 1; slider.property("value", year); render(false);
    }, stepMs);
  }
  function stop() { playing = false; clearInterval(timer); d3.select("#play").text("Play"); }

  // slider ticks: decades plus the years a country splits or merges
  const ticks = d3.select("#ticks");
  const pct = y => (y - Y0) / (Y1 - Y0) * 100;
  for (let y = 1970; y <= Y1; y += 10) ticks.append("span").style("left", pct(y) + "%").text(y);
  const groups = d3.group(nodes.filter(n => n.ex + n.im > 0), n => n.g);
  const events = new Map();
  for (const [g, ms] of groups) {
    if (ms.length < 2) continue;
    for (const m of ms) if (m.y1 < Y1 && m.y1 >= Y0) {
      const y = m.y1 + 1; events.set(y, [...(events.get(y) || []), m.n]);
    }
  }
  for (const [y, names] of events) {
    ticks.append("span").attr("class", "event").style("left", pct(y) + "%").attr("title", `${y}: ${names.join(", ")}`).text("◆");
  }

  // ---------- map
  const W = 1150, H = 560;
  const svg = d3.select("#map");
  const proj = d3.geoEqualEarth().rotate([-10, 0]).fitExtent([[8, 8], [W - 8, H - 8]], { type: "Sphere" });
  const path = d3.geoPath(proj);
  const defs = svg.append("defs");
  defs.append("clipPath").attr("id", "clip").append("path").attr("d", path({ type: "Sphere" }));
  for (const [name, col] of Object.entries({ old: C.bordeaux, new: C.goldDeep, other: C.oak, out: C.bordeaux, in: C.goldDeep })) {
    defs.append("marker").attr("id", `ah-${name}`).attr("viewBox", "0 -5 10 10").attr("refX", 8).attr("refY", 0)
      .attr("markerWidth", 7).attr("markerHeight", 7).attr("markerUnits", "userSpaceOnUse").attr("orient", "auto")
      .append("path").attr("d", "M0,-4L9,0L0,4Z").attr("fill", col);
  }
  svg.append("path").attr("class", "sphere").attr("d", path({ type: "Sphere" }));
  const g = svg.append("g").attr("clip-path", "url(#clip)");
  g.append("path").attr("class", "grat").attr("d", path(d3.geoGraticule10()));
  g.append("path").attr("class", "land").attr("d", path(landF));
  const gStates = g.append("g");
  const gArcs = g.append("g");

  // arc on the sphere: shortest great circle, bowed to the left of travel
  const toXYZ = ([lo, la]) => { const l = lo * Math.PI / 180, p = la * Math.PI / 180; return [Math.cos(p) * Math.cos(l), Math.cos(p) * Math.sin(l), Math.sin(p)]; };
  const toLL = ([x, y, z]) => [Math.atan2(y, x) * 180 / Math.PI, Math.asin(Math.max(-1, Math.min(1, z))) * 180 / Math.PI];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const norm = a => { const m = Math.hypot(...a); return a.map(v => v / m); };
  function arcLine(a, b) {
    const A = toXYZ(a), B = toXYZ(b);
    const ang = Math.acos(Math.max(-1, Math.min(1, A[0] * B[0] + A[1] * B[1] + A[2] * B[2])));
    const N = norm(cross(A, B));
    const h = Math.min(0.2 * ang, 0.22);
    const interp = d3.geoInterpolate(a, b);
    const pts = [];
    for (let s = 0; s <= 40; s++) {
      const t = s / 40, P = toXYZ(interp(t)), k = h * Math.sin(Math.PI * t);
      pts.push(toLL(norm([P[0] + N[0] * k, P[1] + N[1] * k, P[2] + N[2] * k])));
    }
    return { type: "LineString", coordinates: pts };
  }

  // ---------- sankey
  const SW = 1150, SH = 640, TOP = 34, BOT = 8;
  const sk = d3.select("#sankey");
  const gLinks = sk.append("g"), gNodes = sk.append("g"), gHead = sk.append("g");
  const tip = d3.select("#tip");
  const showTip = (ev, html) => tip.html(html).style("opacity", 1)
    .style("left", Math.min(ev.clientX + 14, innerWidth - 270) + "px").style("top", ev.clientY + 12 + "px");
  const hideTip = () => tip.style("opacity", 0);

  // fixed slot order (global, from the data build)
  const exportersAll = nodes.filter(n => n.ex > 0);
  const importersAll = nodes.filter(n => n.im > 0);

  // gap after a node: generous for readable nodes, a hairline for slivers
  const gapFor = h => h >= 4 ? 2.5 : 0.25;
  function scaleFor(valueMaps, total, H) {
    let k = H / total;
    for (let it = 0; it < 4; it++) {
      const pads = Math.max(...valueMaps.map(m => d3.sum([...m.values()], v => v > 0 ? gapFor(v * k) : 0)));
      k = (H - pads) / total;
    }
    return k;
  }
  function stack(list, values, x, w, k, top) {
    let y = top; const out = new Map();
    for (const n of list) {
      const v = values.get(n.i) || 0;
      if (v <= 0) { out.set(n.i, { n, x, w, y0: y, y1: y, v: 0 }); continue; }
      const h = v * k; out.set(n.i, { n, x, w, y0: y, y1: y + h, v }); y += h + gapFor(h);
    }
    return out;
  }
  function ribbon(p) {
    const [x0, a0, b0, x1, a1, b1] = p, xm = (x0 + x1) / 2;
    return `M${x0},${a0}C${xm},${a0} ${xm},${a1} ${x1},${a1}L${x1},${b1}C${xm},${b1} ${xm},${b0} ${x0},${b0}Z`;
  }
  function placeLinks(links, L, R, xL, xR) {
    // outgoing order follows the target's slot, incoming order the source's slot
    const outOff = new Map(), inOff = new Map();
    const bySrc = d3.group(links, d => d.s), byTgt = d3.group(links, d => d.t);
    for (const [s, ls] of bySrc) { let o = L.get(s).y0; ls.sort((a, b) => R.get(a.t).y0 - R.get(b.t).y0).forEach(l => { l.a0 = o; o += l.h; l.b0 = o; }); }
    for (const [t, ls] of byTgt) { let o = R.get(t).y0; ls.sort((a, b) => L.get(a.s).y0 - L.get(b.s).y0).forEach(l => { l.a1 = o; o += l.h; l.b1 = o; }); }
    links.forEach(l => { l.p = [xL, l.a0, l.b0, xR, l.a1, l.b1]; });
  }

  // ---------- render
  function render(selChanged) {
    location.replace(`#${new URLSearchParams({ ...(sel != null ? { c: nodes[sel].k } : {}), y: year })}`);
    const dur = forcedDur != null ? forcedDur : playing ? Math.min(stepMs * 0.9, 800) : 450;
    const flows = flowsIn(year);
    const total = d3.sum(flows, f => f.v);
    d3.select("#year").text(year);
    const S = sel != null ? nodes[sel] : null;
    const mine = S ? flows.filter(f => f.e === sel || f.i === sel) : flows;
    const exS = S ? d3.sum(mine.filter(f => f.e === sel), f => f.v) : 0;
    const imS = S ? d3.sum(mine.filter(f => f.i === sel), f => f.v) : 0;
    d3.select("#total").text(S ? `${S.n}: exported ${fmt(exS)}, imported ${fmt(imS)}` : `${fmt(total)} crossed a border`);

    // legend
    const lg = d3.select("#legend").html("");
    const items = S ? [[`Exports from ${S.n}`, C.bordeaux], [`Imports into ${S.n}`, C.gold]] : Object.entries(CATNAME).map(([k, v]) => [v, CAT[k]]);
    items.forEach(([t, c]) => lg.append("span").html(`<i style="background:${c}"></i>${t}`));
    lg.append("span").text(S ? "Arc width: volume" : "Largest 80 flows of the year; arc width: volume");

    // states
    const exBy = d3.rollup(flows, v => d3.sum(v, f => f.v), f => f.e);
    const maxEx = d3.max(exBy.values()) || 1;
    const toSel = S ? d3.rollup(mine.filter(f => f.e === sel), v => d3.sum(v, f => f.v), f => f.i) : null;
    const fromSel = S ? d3.rollup(mine.filter(f => f.i === sel), v => d3.sum(v, f => f.v), f => f.e) : null;
    const maxPartner = S ? Math.max(d3.max(toSel.values()) || 0, d3.max(fromSel.values()) || 0) || 1 : 1;
    const fill = f => {
      const n = nodeForFeature(f, year);
      if (!n) return C.state;
      if (S) {
        if (n.i === sel) return C.bordeaux;
        const a = (toSel.get(n.i) || 0), b = (fromSel.get(n.i) || 0);
        if (a >= b && a > 0) return d3.interpolate(C.state, C.rose)(0.25 + 0.75 * Math.sqrt(a / maxPartner));
        if (b > 0) return d3.interpolate(C.state, C.gold)(0.2 + 0.6 * Math.sqrt(b / maxPartner));
        return C.state;
      }
      const v = exBy.get(n.i) || 0;
      return v > 0 ? d3.interpolate(C.state, n.c === "new" ? C.gold : n.c === "old" ? C.rose : C.cork)(0.15 + 0.7 * Math.sqrt(v / maxEx)) : C.state;
    };
    gStates.selectAll("path.state").data(statesIn(year), f => `${f.properties.gw}-${f.properties.y0}`)
      .join(enter => enter.append("path").attr("class", "state").attr("d", path).style("fill", C.state).style("opacity", 0),
        update => update, exit => exit.transition("x").duration(dur).style("opacity", 0).remove())
      .on("mousemove", (ev, f) => {
        const n = nodeForFeature(f, year);
        if (!n) return showTip(ev, `<b>${f.properties.name}</b><br>no wine trade reported`);
        const e = exBy.get(n.i) || 0, im = d3.sum(flows.filter(x => x.i === n.i), x => x.v);
        showTip(ev, `<b>${n.n}</b> · ${year}<br>exported ${fmt(e)}<br>imported ${fmt(im)}`);
      })
      .on("mouseleave", hideTip)
      .on("click", (ev, f) => { const n = nodeForFeature(f, year); if (n) { sel = sel === n.i ? null : n.i; selectEl.property("value", sel == null ? "" : n.k); render(true); } })
      .transition().duration(dur).style("fill", fill).style("opacity", 1);

    // arcs
    const arcFlows = (S ? mine : flows).slice().sort((a, b) => b.v - a.v).slice(0, CAPTURE ? 40 : S ? 60 : 80)
      .map(f => ({ ...f, A: anchor(nodes[f.e], year), B: anchor(nodes[f.i], year) })).filter(f => f.A && f.B);
    const maxFlow = S ? (selMax.get(sel) || 1) : worldMax;
    const wScale = d3.scaleSqrt().domain([0, maxFlow]).range([0, S ? 9 : 11]);
    const col = f => S ? (f.e === sel ? C.bordeaux : C.goldDeep) : CAT[nodes[f.e].c] === C.gold ? C.goldDeep : CAT[nodes[f.e].c];
    const mk = f => S ? (f.e === sel ? "out" : "in") : nodes[f.e].c;
    gArcs.selectAll("path.arc").data(arcFlows, f => `${f.e}-${f.i}`)
      .join(enter => enter.append("path").attr("class", "arc").style("stroke-width", 0).style("opacity", 0),
        update => update, exit => exit.transition().duration(dur).style("stroke-width", 0).style("opacity", 0).remove())
      .attr("d", f => path(arcLine(f.A, f.B)))
      .attr("marker-end", f => `url(#ah-${mk(f)})`)
      .style("stroke", col)
      .on("mousemove", (ev, f) => showTip(ev, `<b>${nodes[f.e].n} → ${nodes[f.i].n}</b><br>${fmt(f.v)}${f.est ? " (estimated from value)" : ""}`))
      .on("mouseleave", hideTip)
      .transition().duration(dur)
      .style("stroke-width", f => Math.max(0.6, wScale(f.v)) + "px")
      .style("opacity", f => 0.55 + 0.35 * Math.min(1, f.v / maxFlow * 4));

    // sankey
    drawSankey(flows, S, dur);
  }

  function drawSankey(flows, S, dur) {
    const H = SH - TOP - BOT;
    let L, R, M, links, pad = 1.2;
    const xL = CAPTURE ? 200 : 190, xR = SW - (CAPTURE ? 300 : 190), nw = 12;
    if (!S) {
      d3.select("#sankey-title").html("Who sold, who bought");
      d3.select("#sankey-note").text("Exporters left, importers right, in a fixed order; heights are shares of the year's trade");
      const exV = d3.rollup(flows, v => d3.sum(v, f => f.v), f => f.e);
      const imV = d3.rollup(flows, v => d3.sum(v, f => f.v), f => f.i);
      const total = d3.sum(flows, f => f.v) || 1;
      const k = scaleFor([exV, imV], total, H);
      L = stack(exportersAll, exV, xL - nw, nw, k, TOP);
      R = stack(importersAll, imV, xR, nw, k, TOP);
      links = flows.map(f => ({ id: `${f.e}-${f.i}`, s: f.e, t: f.i, v: f.v, h: f.v * k, c: CAT[nodes[f.e].c] }));
      placeLinks(links, L, R, xL, xR);
      links = links.filter(l => l.h > 0.15);
      M = null;
    } else {
      d3.select("#sankey-title").html(`Who sold to <em>${S.n}</em>, and who bought from it`);
      d3.select("#sankey-note").text("Suppliers left, buyers right, in the same fixed order");
      const ins = flows.filter(f => f.i === S.i), outs = flows.filter(f => f.e === S.i);
      const inV = d3.rollup(ins, v => d3.sum(v, f => f.v), f => f.e);
      const outV = d3.rollup(outs, v => d3.sum(v, f => f.v), f => f.i);
      const tIn = d3.sum(ins, f => f.v), tOut = d3.sum(outs, f => f.v), big = Math.max(tIn, tOut) || 1;
      const k = scaleFor([inV, outV], big, H);
      const xC = (xL + xR) / 2;
      L = stack(exportersAll, inV, xL - nw, nw, k, TOP);
      R = stack(importersAll, outV, xR, nw, k, TOP);
      const cIn = { n: S, x: xC - nw, w: nw, y0: TOP, y1: TOP + tIn * k, v: tIn, centre: "in" };
      const cOut = { n: S, x: xC, w: nw, y0: TOP, y1: TOP + tOut * k, v: tOut, centre: "out" };
      M = [cIn, cOut];
      const l1 = ins.map(f => ({ id: `in-${f.e}`, s: f.e, t: "C", v: f.v, h: f.v * k, c: C.gold }));
      const l2 = outs.map(f => ({ id: `out-${f.i}`, s: "C", t: f.i, v: f.v, h: f.v * k, c: C.bordeaux }));
      placeLinks(l1, L, new Map([["C", cIn]]), xL, xC - nw);
      placeLinks(l2, new Map([["C", cOut]]), R, xC + nw, xR);
      links = [...l1, ...l2].filter(l => l.h > 0.1);
    }

    // column heads
    const xMid = S ? (xL + xR) / 2 : SW / 2;
    const heads = S ? [[xL, "end", "Bought from"], [xMid, "middle", ""], [xR + nw, "start", "Sold to"]]
      : [[xL, "end", "Exporters"], [xR + nw, "start", "Importers"]];
    gHead.selectAll("text.col").data(heads, d => d[2]).join("text").attr("class", "col")
      .attr("x", d => d[0]).attr("y", 16).attr("text-anchor", d => d[1]).text(d => d[2]);
    gHead.selectAll("text.focus").data(S ? [S] : []).join("text").attr("class", "focus")
      .attr("x", xMid).attr("y", 20).attr("text-anchor", "middle").text(d => d.n);

    // links
    gLinks.selectAll("path.link").data(links, d => d.id)
      .join(enter => enter.append("path").attr("class", "link")
        .attr("d", d => ribbon([d.p[0], d.p[1], d.p[1], d.p[3], d.p[4], d.p[4]])).each(function (d) { this._p = [d.p[0], d.p[1], d.p[1], d.p[3], d.p[4], d.p[4]]; }),
        update => update,
        exit => exit.transition().duration(dur).attrTween("d", function () {
          const p = this._p, q = [p[0], p[1], p[1], p[3], p[4], p[4]], i = d3.interpolate(p, q);
          return t => ribbon(i(t));
        }).remove())
      .attr("fill", d => d.c).attr("fill-opacity", d => d.h >= 2 ? 0.5 : 0.28)
      .on("mousemove", (ev, d) => {
        const a = d.s === "C" ? S.n : nodes[d.s].n, b = d.t === "C" ? S.n : nodes[d.t].n;
        showTip(ev, `<b>${a} → ${b}</b><br>${fmt(d.v)}`);
      })
      .on("mouseleave", hideTip)
      .transition().duration(dur).attrTween("d", function (d) {
        const i = d3.interpolate(this._p || d.p, d.p); this._p = d.p; return t => ribbon(i(t));
      });

    // nodes
    const nodeData = [...[...L.values()].map(d => ({ ...d, id: `L${d.n.i}` })),
      ...[...R.values()].map(d => ({ ...d, id: `R${d.n.i}` })),
      ...(M || []).map(d => ({ ...d, id: `C${d.centre}` }))];
    const ng = gNodes.selectAll("g.node").data(nodeData, d => d.id)
      .join(enter => { const e = enter.append("g").attr("class", "node"); e.append("rect"); e.append("text"); return e; });
    ng.select("rect").attr("x", d => d.x).attr("width", d => d.w)
      .attr("fill", d => d.centre === "in" ? C.goldDeep : d.centre === "out" ? C.bordeaux : CAT[d.n.c])
      .on("mousemove", (ev, d) => showTip(ev, `<b>${d.n.n}</b> · ${year}<br>${d.centre === "in" ? "imported " : d.centre === "out" ? "exported " : ""}${fmt(d.v)}`))
      .on("mouseleave", hideTip)
      .on("click", (ev, d) => { sel = sel === d.n.i ? null : d.n.i; selectEl.property("value", sel == null ? "" : d.n.k); render(true); })
      .transition().duration(dur).attr("y", d => d.y0).attr("height", d => Math.max(0, d.y1 - d.y0));
    ng.select("text")
      .attr("text-anchor", d => d.x < xL + 5 ? "end" : "start")
      .attr("x", d => d.x < xL + 5 ? d.x - 6 : d.x + d.w + 6)
      .attr("dy", "0.35em")
      .text(d => d.centre ? "" : `${d.n.n}  ${fmt(d.v).replace(" litres", " l")}`)
      .transition().duration(dur)
      .attr("y", d => (d.y0 + d.y1) / 2)
      .style("opacity", d => (d.y1 - d.y0) >= (CAPTURE ? 15 : 9) ? 1 : 0);
  }

  // per-country maximum single flow across all years, for stable arc widths
  const selMax = new Map();
  let worldMax = 0;
  for (const y of years) for (const [e, i, v] of data.flows[y]) {
    worldMax = Math.max(worldMax, v);
    selMax.set(e, Math.max(selMax.get(e) || 0, v));
    selMax.set(i, Math.max(selMax.get(i) || 0, v));
  }

  if (CAPTURE && sel != null) {
    d3.select(".dek").text(`${nodes[sel].n}: who it bought wine from and who it sold to, every year since ${Y0}, on the borders of the time.`);
  }
  // used by the GIF capture script: jump to a year with a given transition length
  window.__setYear = (y, d) => { forcedDur = d; year = y; slider.property("value", y); render(false); };
  window.__ready = true;
  render(true);
  if (QS.has("play")) play();
})();
