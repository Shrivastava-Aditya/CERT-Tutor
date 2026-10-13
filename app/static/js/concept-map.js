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
    const width = Math.max(el.clientWidth, 320);
    const height = +el.dataset.height || 420;
    const small = width < 500;
    const nodeR = small ? 20 : 26;
    // Short labels on small maps so they fit inside the panel
    const label = d => {
      const t = d.written ? d.title.replace(/^Amazon |^AWS /, "") : d.title;
      return small && t.length > 18 ? t.slice(0, 16) + "…" : t;
    };

    const nodes = data.nodes.map(d => ({ ...d }));
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

    const link = svg.append("g").selectAll("line").data(links).join("line")
      .attr("class", d => "cmap-link" + (d.hot ? " hot" : ""));

    const node = svg.append("g").selectAll("g").data(nodes).join("g")
      .attr("class", d => [
        "cmap-node",
        d.written ? "written" : "ghost",
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
      .force("link", d3.forceLink(links).id(d => d.id).distance(small ? 70 : 170).strength(0.6))
      .force("charge", d3.forceManyBody().strength(small ? -300 : -1000))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide(nodeR + (small ? 30 : 56)))
      .force("x", d3.forceX(width / 2).strength(0.03))
      .force("y", d3.forceY(height / 2).strength(0.06));

    const pad = nodeR + 6;
    const padX = small ? 52 : 80;   // room for the label under each node
    function draw() {
      nodes.forEach(d => {
        d.x = Math.max(padX, Math.min(width - padX, d.x));
        d.y = Math.max(pad, Math.min(height - pad - 18, d.y));
      });
      link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
          .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
      node.attr("transform", d => `translate(${d.x},${d.y})`);
    }

    if (reduceMotion) {
      // Settle the layout instantly and draw it once
      sim.stop();
      for (let i = 0; i < 300; i++) sim.tick();
      draw();
      return;
    }

    sim.on("tick", draw);
    // Once settled, keep a tiny bit of energy so the map gently breathes
    sim.on("end", () => sim.alphaTarget(0.008).restart());

    node.call(d3.drag()
      .on("start", (event, d) => { if (!event.active) sim.alphaTarget(0.25).restart(); d.fx = d.x; d.fy = d.y; })
      .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
      .on("end", (event, d) => { if (!event.active) sim.alphaTarget(0.008); d.fx = null; d.fy = null; }));
  }
})();
