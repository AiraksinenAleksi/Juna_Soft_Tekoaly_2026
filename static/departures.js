// Departures board: auto-refresh (fetches the table-body partial) and the
// commuter/passenger filter. External file because the CSP ships
// `script-src 'self'` with no 'unsafe-inline' — inline <script> would be
// silently blocked by the browser.
(function () {
  "use strict";

  const body = document.getElementById("departures-body");
  if (!body) return;

  const url = body.dataset.partialUrl;
  let refreshing = false;

  const FILTERS = {
    all: () => true,
    passenger: (cat) => cat === "Commuter" || cat === "Long-distance",
    commuter: (cat) => cat === "Commuter",
    "long-distance": (cat) => cat === "Long-distance",
    cargo: (cat) => cat === "Cargo",
  };
  let activeFilter = "passenger";

  function applyFilter() {
    const rows = body.querySelectorAll("tr[data-category]");
    const rule = FILTERS[activeFilter] || FILTERS.all;
    let visible = 0;
    rows.forEach((tr) => {
      const show = rule(tr.dataset.category);
      tr.style.display = show ? "" : "none";
      if (show) visible += 1;
    });
    const noMatch = document.getElementById("no-match-row");
    if (noMatch) {
      noMatch.style.display = rows.length > 0 && visible === 0 ? "" : "none";
    }
  }

  document.querySelectorAll(".filter-pill").forEach((btn) => {
    btn.addEventListener("click", () => {
      activeFilter = btn.dataset.filter;
      document.querySelectorAll(".filter-pill").forEach((b) => {
        const active = b === btn;
        b.classList.toggle("active", active);
        b.setAttribute("aria-pressed", active ? "true" : "false");
      });
      applyFilter();
    });
  });

  async function refresh() {
    if (refreshing || document.hidden || !url) return;
    refreshing = true;
    try {
      const res = await fetch(url, { headers: { Accept: "text/html" } });
      if (res.ok) {
        body.innerHTML = await res.text();
        applyFilter();
      }
    } catch (e) {
      /* keep showing current data on transient failures */
    } finally {
      refreshing = false;
    }
  }

  applyFilter();
  setInterval(refresh, 60000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });
})();
