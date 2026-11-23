// Small enhancements on top of the pre-built HTML. Every page works without this file;
// it only adds: the click-to-play player, filters/search on the homepage, "3 days ago" dates and Share.
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];

  // ---------- lightweight YouTube player (loads the real player only on click) ----------
  document.addEventListener("click", e => {
    const yt = e.target.closest("a.yt[data-yt]");
    if (!yt || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    const id = encodeURIComponent(yt.dataset.yt);
    const f = document.createElement("iframe");
    f.src = `https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0&playsinline=1`;
    f.title = yt.getAttribute("aria-label") || "YouTube video";
    f.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen; web-share";
    f.allowFullscreen = true;
    const box = document.createElement("div");
    box.className = yt.className + " is-playing";
    box.appendChild(f);
    yt.replaceWith(box);
  });

  // ---------- relative dates ----------
  const ago = d => {
    const s = (Date.now() - d) / 1000;
    for (const [u, sec] of [["year", 31536000], ["month", 2592000], ["week", 604800], ["day", 86400], ["hour", 3600], ["minute", 60]]) {
      const v = Math.floor(s / sec);
      if (v >= 1) return `${v} ${u}${v > 1 ? "s" : ""} ago`;
    }
    return "just now";
  };
  $$("time[data-ago]").forEach(t => {
    const d = new Date(t.getAttribute("datetime"));
    if (!isNaN(d)) { t.title = t.textContent; t.textContent = ago(d); }
  });

  // ---------- share ----------
  $$("[data-share]").forEach(b => b.addEventListener("click", async () => {
    const data = { title: document.title, url: location.href.split("#")[0] };
    try {
      if (navigator.share) await navigator.share(data);
      else { await navigator.clipboard.writeText(data.url); b.textContent = "Link copied ✓"; }
    } catch { /* user cancelled */ }
  }));

  // ---------- homepage filters ----------
  const grid = $("#grid");
  if (!grid) return;
  const PAGE = 12;
  const cards = $$(".card", grid);
  const state = { topic: "all", type: "all", q: "", shown: PAGE };

  function apply() {
    const q = state.q.trim().toLowerCase();
    let match = 0;
    cards.forEach(c => {
      const ok = (state.topic === "all" || c.dataset.topic === state.topic) &&
                 (state.type === "all" || c.dataset.type === state.type) &&
                 (!q || c.dataset.search.includes(q));
      if (ok) match++;
      c.hidden = !ok || match > state.shown;
    });
    $("#empty").hidden = match > 0;
    $("#more").hidden = match <= state.shown;
  }

  $("#topics").addEventListener("click", e => {
    const b = e.target.closest("[data-topic]");
    if (!b) return;
    state.topic = b.dataset.topic; state.shown = PAGE;
    $$("#topics button").forEach(x => x.classList.toggle("on", x === b));
    apply();
  });
  $("#types").addEventListener("click", e => {
    const b = e.target.closest("[data-type]");
    if (!b) return;
    state.type = b.dataset.type; state.shown = PAGE;
    $$("#types button").forEach(x => x.classList.toggle("on", x === b));
    apply();
  });
  $("#q").addEventListener("input", e => { state.q = e.target.value; state.shown = PAGE; apply(); });
  $("#more").addEventListener("click", () => { state.shown += PAGE; apply(); });
  apply();
})();
