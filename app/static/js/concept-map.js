// Living concept map: a D3 force simulation. Related concepts pull together and everything else pushes apart.
// The data comes from the JSON <script> inside each [data-concept-map] element.
(function () {
  const css = getComputedStyle(document.documentElement);
  const token = name => css.getPropertyValue(name).trim();
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

  document.querySelectorAll("[data-concept-map]").forEach(init);

  function init(el) {
    const data = JSON.parse(el.querySelector('script[type="application/json"]').textContent);
    const focus = el.dataset.focus || null;
    // A focused map (the side panel on a concept page) shows only that concept and its direct neighbours
    if (focus) {
      const keep = new Set([focus]);
      data.links.forEach(l => {
        if (l.source === focus) keep.add(l.target);
        if (l.target === focus) keep.add(l.source);
      });
      data.nodes = data.nodes.filter(n => keep.has(n.id));
      data.links = data.links.filter(l => l.source === focus || l.target === focus);
    }
    const width = Math.max(el.clientWidth, 320);
    const small = width < 500;
    const big = data.nodes.length > 20;
    // Big maps grow taller and sort nodes into one column per exam domain
    const columns = big && !small ? (data.domains || []) : [];
    const colIndexEarly = Object.fromEntries((data.domains || []).map((d, i) => [d.id, i]));
    // Tallest domain column decides the height: about 62px per concept
    const perColumn = {};
    data.nodes.forEach(n => { perColumn[n.domain] = (perColumn[n.domain] || 0) + 1; });
    const tallest = Math.max(0, ...Object.values(perColumn));
    const height = Math.max(+el.dataset.height || 420, columns.length ? 40 + tallest * 62 + 40 : 0);
    const colIndex = Object.fromEntries(columns.map((d, i) => [d.id, i]));
    const colX = d => d.domain in colIndex ? width * (colIndex[d.domain] + 0.5) / columns.length : width / 2;
    const top = columns.length ? 40 : 0;   // room for the column titles
    const nodeR = small ? 18 : big ? 19 : 26;
    // Short labels on small or crowded maps so they fit
    const label = d => {
      const t = d.written ? d.title.replace(/^Amazon |^AWS /, "") : d.title;
      return (small || big) && t.length > 20 ? t.slice(0, 18) + "…" : t;
    };

    const nodes = data.nodes.map(d => ({ ...d }));
    // Start each column's nodes spread evenly top to bottom, so the layout begins tidy
    if (big && !small) {
      const seen = {};
      nodes.forEach(n => {
        const i = seen[n.domain] = (seen[n.domain] ?? -1) + 1;
        const count = perColumn[n.domain];
        n.y0 = 40 + (i + 0.5) * ((height - 80) / count) + 20;
        n.x = (n.domain in colIndexEarly ? width * (colIndexEarly[n.domain] + 0.5) / data.domains.length : width / 2) + (i % 2 ? 34 : -34);
        n.y = n.y0;
      });
    }
    // Work out the focus neighbourhood before D3 swaps link ids for node objects
    const near = new Set(focus ? [focus] : []);
    const links = data.links.map(l => {
      const hot = focus && (l.source === focus || l.target === focus);
      if (hot) { near.add(l.source); near.add(l.target); }
      return { ...l, hot };
    });

    const colour = d => d.written ? token(`--dom-${d.domain}`) || token("--accent") : token("--new");

    const svg = d3.select(el).append("svg")
      .attr("class", "cmap")
      .attr("viewBox", [0, 0, width, height])
      .attr("role", "img")
      .attr("aria-label", "Concept map of related concepts");

    // Circular clip so square service icons sit neatly inside each node
    const clipId = `clip-${Math.random().toString(36).slice(2)}`;
    svg.append("defs").append("clipPath").attr("id", clipId)
      .append("circle").attr("r", nodeR - 5);

    svg.append("g").selectAll("text").data(columns).join("text")
      .attr("class", "cmap-col").attr("x", (d, i) => width * (i + 0.5) / columns.length).attr("y", 22)
      .attr("text-anchor", "middle").style("fill", d => token(`--dom-${d.id}`))
      .text(d => d.name.replace(/^Design /, "").replace(/ Architectures$/, ""));

    const link = svg.append("g").selectAll("line").data(links).join("line")
      .attr("class", d => "cmap-link" + (d.hot ? " hot" : ""));

    const node = svg.append("g").selectAll("g").data(nodes).join("g")
      .attr("class", d => [
        "cmap-node",
        d.written ? "written" : "ghost",
        d.written ? `m-${d.mastery || "new"}` : "",
        d.id === focus ? "focus" : "",
        focus && !near.has(d.id) ? "dim" : "",
      ].join(" "))
      .style("--node", colour)
      .attr("tabindex", d => d.written && d.id !== focus ? 0 : null)
      .attr("role", d => d.written && d.id !== focus ? "link" : null)
      .attr("aria-label", d => d.written ? d.title : `${d.title} (not written yet)`);

    node.append("circle").attr("class", "ring").attr("r", d => d.written ? nodeR : nodeR * 0.6);
    node.filter(d => d.written && d.icon).append("image")
      .attr("href", d => d.icon)
      .attr("x", -(nodeR - 5)).attr("y", -(nodeR - 5))
      .attr("width", (nodeR - 5) * 2).attr("height", (nodeR - 5) * 2)
      .attr("clip-path", `url(#${clipId})`);
    node.append("text").attr("class", "cmap-label")
      .attr("y", d => (d.written ? nodeR : nodeR * 0.6) + 16)
      .attr("text-anchor", "middle")
      .text(label)
      .append("title").text(d => d.title);

    // Click or press Enter to open a concept
    const open = d => { if (d.written && d.id !== focus) location.href = d.url; };
    node.on("click", (event, d) => { if (!event.defaultPrevented) open(d); })
        .on("keydown", (event, d) => { if (event.key === "Enter") open(d); });

    // Hover: light up a node's neighbours
    node.on("mouseenter", (event, d) => {
      link.classed("lit", l => l.source.id === d.id || l.target.id === d.id);
    }).on("mouseleave", () => link.classed("lit", false));

    const sim = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id(d => d.id).distance(small ? 70 : big ? 60 : 170).strength(big ? 0.15 : 0.6))
      .force("charge", d3.forceManyBody().strength(small ? -300 : big ? -220 : -1000))
      .force("collide", d3.forceCollide(nodeR + (small ? 30 : big ? 36 : 56)))
      .force("x", d3.forceX(colX).strength(columns.length ? 0.22 : 0.03))
      .force("y", columns.length ? d3.forceY(d => d.y0 ?? height / 2).strength(0.35) : d3.forceY(height / 2).strength(0.06));
    if (!columns.length) sim.force("center", d3.forceCenter(width / 2, height / 2));

    const pad = nodeR + 6;
    const padX = small ? 52 : 80;   // room for the label under each node
    function draw() {
      nodes.forEach(d => {
        d.x = Math.max(padX, Math.min(width - padX, d.x));
        d.y = Math.max(pad + top, Math.min(height - pad - 18, d.y));
      });
      link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
          .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
      node.attr("transform", d => `translate(${d.x},${d.y})`);
    }

    // Crop the view to where the nodes ended up, so the map has no empty bands
    function fit() {
      const ys = nodes.map(d => d.y);
      const minY = Math.min(...ys) - nodeR - (columns.length ? 46 : 12);
      const maxY = Math.max(...ys) + nodeR + 28;
      svg.attr("viewBox", [0, minY, width, maxY - minY]);
      svg.selectAll(".cmap-col").attr("y", minY + 22);
    }

    // Lay the map out before showing it (applying the edge limits on every step), then crop it
    sim.stop();
    for (let i = 0; i < 300; i++) { sim.tick(); draw(); }
    fit();
    if (reduceMotion) return;

    // Keep a tiny bit of energy so the map gently breathes
    sim.on("tick", draw);
    sim.alpha(0.02).alphaTarget(0.008).restart();

    node.call(d3.drag()
      .on("start", (event, d) => { if (!event.active) sim.alphaTarget(0.25).restart(); d.fx = d.x; d.fy = d.y; })
      .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
      .on("end", (event, d) => { if (!event.active) sim.alphaTarget(0.008); d.fx = null; d.fy = null; }));
  }
})();
