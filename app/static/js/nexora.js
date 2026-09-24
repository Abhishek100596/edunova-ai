/**
 * EDUNOVA AI — frontend helpers (legacy API: window.Nexora)
 * Theme toggle, sidebar, toasts, Chart.js init, form loading
 */
(function () {
  "use strict";

  var THEME_KEY = "nexora-theme";

  function getPreferredTheme() {
    try {
      var stored = localStorage.getItem(THEME_KEY);
      if (stored === "light" || stored === "dark") return stored;
    } catch (e) { /* ignore */ }
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
      return "light";
    }
    return "dark";
  }

  function applyTheme(theme) {
    var root = document.documentElement;
    root.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch (e) { /* ignore */ }
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
      btn.setAttribute("title", theme === "dark" ? "Light mode" : "Dark mode");
    });
    window.dispatchEvent(new CustomEvent("nexora:themechange", { detail: { theme: theme } }));
  }

  function toggleTheme() {
    var current = document.documentElement.getAttribute("data-theme") || "dark";
    applyTheme(current === "dark" ? "light" : "dark");
  }

  /* ---------- Toasts ---------- */
  function ensureToastArea() {
    var area = document.getElementById("toast-area");
    if (!area) {
      area = document.createElement("div");
      area.id = "toast-area";
      area.className = "toast-area";
      area.setAttribute("aria-live", "polite");
      document.body.appendChild(area);
    }
    return area;
  }

  function toast(message, type, duration) {
    type = type || "info";
    duration = duration == null ? 4200 : duration;
    var area = ensureToastArea();
    var el = document.createElement("div");
    el.className = "toast toast-" + type;
    el.setAttribute("role", "status");

    var body = document.createElement("div");
    body.textContent = message;

    var close = document.createElement("button");
    close.type = "button";
    close.className = "toast-close";
    close.setAttribute("aria-label", "Dismiss");
    close.innerHTML = "&times;";
    close.addEventListener("click", function () {
      el.remove();
    });

    el.appendChild(body);
    el.appendChild(close);
    area.appendChild(el);

    if (duration > 0) {
      setTimeout(function () {
        if (el.parentNode) el.remove();
      }, duration);
    }
    return el;
  }

  /* ---------- Sidebar ---------- */
  function initSidebar() {
    var shell = document.querySelector(".app-shell");
    var sidebar = document.getElementById("app-sidebar");
    var backdrop = document.getElementById("sidebar-backdrop");
    var openBtns = document.querySelectorAll("[data-sidebar-open]");
    var closeBtns = document.querySelectorAll("[data-sidebar-close]");
    var collapseBtns = document.querySelectorAll("[data-sidebar-collapse]");

    function openMobile() {
      if (!sidebar) return;
      sidebar.classList.add("open");
      if (backdrop) backdrop.classList.add("show");
      document.body.style.overflow = "hidden";
    }

    function closeMobile() {
      if (!sidebar) return;
      sidebar.classList.remove("open");
      if (backdrop) backdrop.classList.remove("show");
      document.body.style.overflow = "";
    }

    openBtns.forEach(function (btn) {
      btn.addEventListener("click", openMobile);
    });
    closeBtns.forEach(function (btn) {
      btn.addEventListener("click", closeMobile);
    });
    if (backdrop) {
      backdrop.addEventListener("click", closeMobile);
    }

    collapseBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (!shell) return;
        if (window.matchMedia("(max-width: 900px)").matches) {
          if (sidebar && sidebar.classList.contains("open")) closeMobile();
          else openMobile();
        } else {
          shell.classList.toggle("sidebar-collapsed");
          try {
            localStorage.setItem(
              "nexora-sidebar-collapsed",
              shell.classList.contains("sidebar-collapsed") ? "1" : "0"
            );
          } catch (e) { /* ignore */ }
        }
      });
    });

    try {
      if (shell && localStorage.getItem("nexora-sidebar-collapsed") === "1") {
        if (!window.matchMedia("(max-width: 900px)").matches) {
          shell.classList.add("sidebar-collapsed");
        }
      }
    } catch (e) { /* ignore */ }

    window.addEventListener("resize", function () {
      if (!window.matchMedia("(max-width: 900px)").matches) {
        closeMobile();
      }
    });
  }

  /* ---------- Tabs ---------- */
  function initTabs() {
    document.querySelectorAll("[data-tabs]").forEach(function (root) {
      var tabs = root.querySelectorAll(".tab");
      var panels = root.querySelectorAll(".tab-panel");
      tabs.forEach(function (tab) {
        tab.addEventListener("click", function () {
          var target = tab.getAttribute("data-tab");
          tabs.forEach(function (t) { t.classList.toggle("active", t === tab); });
          panels.forEach(function (p) {
            p.classList.toggle("active", p.getAttribute("data-panel") === target);
          });
        });
      });
    });
  }

  /* ---------- Form loading ---------- */
  function resetLoadingButtons(scope) {
    var root = scope || document;
    root.querySelectorAll("form[data-loading] button.is-loading, form[data-loading] .btn.is-loading").forEach(function (btn) {
      btn.classList.remove("is-loading");
      btn.disabled = false;
      if (btn.dataset.originalHtml) {
        btn.innerHTML = btn.dataset.originalHtml;
      }
    });
  }

  function initForms() {
    document.querySelectorAll("form[data-loading]").forEach(function (form) {
      form.addEventListener("submit", function () {
        var btn = form.querySelector('button[type="submit"], .btn-primary, .btn-ai');
        if (!btn) return;
        btn.classList.add("is-loading");
        btn.disabled = true;
        var label = btn.getAttribute("data-loading-text") || "Working…";
        if (!btn.dataset.originalHtml) {
          btn.dataset.originalHtml = btn.innerHTML;
        }
        btn.innerHTML = label;
      });
    });
    // Restore buttons if the browser restores a cached page after a failed nav
    window.addEventListener("pageshow", function () {
      resetLoadingButtons(document);
    });
  }

  /* ---------- CSRF-aware fetch for JSON APIs ---------- */
  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  function apiFetch(url, options) {
    options = options || {};
    var headers = Object.assign({}, options.headers || {});
    var token = csrfToken();
    if (token) {
      headers["X-CSRFToken"] = token;
      headers["X-CSRF-Token"] = token;
    }
    if (options.body && typeof options.body === "object" && !(options.body instanceof FormData)) {
      headers["Content-Type"] = headers["Content-Type"] || "application/json";
      options.body = JSON.stringify(options.body);
    }
    options.headers = headers;
    options.credentials = options.credentials || "same-origin";
    return fetch(url, options).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) {
          var err = new Error((data && (data.error || data.message)) || ("Request failed (" + res.status + ")"));
          err.status = res.status;
          err.data = data;
          throw err;
        }
        return data;
      }).catch(function (parseErr) {
        if (parseErr.status) throw parseErr;
        if (!res.ok) {
          var err2 = new Error("Request failed (" + res.status + ")");
          err2.status = res.status;
          throw err2;
        }
        throw parseErr;
      });
    });
  }

  /* ---------- Onboarding completion % ---------- */
  function initOnboardingProgress() {
    var form = document.getElementById("onboarding-form");
    var bar = document.getElementById("onboarding-progress");
    var label = document.getElementById("onboarding-progress-label");
    if (!form || !bar) return;

    function update() {
      var fields = form.querySelectorAll("input, select, textarea");
      var total = 0;
      var filled = 0;
      fields.forEach(function (el) {
        if (el.type === "hidden" || el.type === "submit" || el.disabled) return;
        if (el.type === "checkbox" || el.type === "radio") {
          var name = el.name;
          if (!name) return;
          if (form.querySelector('input[name="' + name + '"]') !== el) return;
          total += 1;
          if (form.querySelector('input[name="' + name + '"]:checked')) filled += 1;
          return;
        }
        total += 1;
        if (String(el.value || "").trim() !== "") filled += 1;
      });
      var pct = total ? Math.round((filled / total) * 100) : 0;
      bar.style.width = pct + "%";
      if (label) label.textContent = pct + "% complete";
    }

    form.addEventListener("input", update);
    form.addEventListener("change", update);
    update();
  }

  /* ---------- Chart.js helpers ---------- */
  function chartColors() {
    var theme = document.documentElement.getAttribute("data-theme") || "dark";
    var isLight = theme === "light";
    return {
      text: isLight ? "#64748b" : "#94a3b8",
      grid: isLight ? "rgba(100,116,139,0.14)" : "rgba(148,163,184,0.12)",
      primary: isLight ? "#0284c7" : "#38bdf8",
      accent: isLight ? "#0891b2" : "#22d3ee",
      success: isLight ? "#059669" : "#34d399",
      warning: isLight ? "#d97706" : "#fbbf24",
      danger: isLight ? "#dc2626" : "#f87171",
      surface: isLight ? "#ffffff" : "#131c31",
    };
  }

  function baseChartOptions() {
    var c = chartColors();
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: c.text, boxWidth: 12, font: { family: "DM Sans", size: 12 } },
        },
        tooltip: {
          backgroundColor: c.surface,
          titleColor: c.text,
          bodyColor: c.text,
          borderColor: c.grid,
          borderWidth: 1,
        },
      },
      scales: {
        x: {
          ticks: { color: c.text },
          grid: { color: c.grid },
        },
        y: {
          ticks: { color: c.text },
          grid: { color: c.grid },
        },
      },
    };
  }

  var chartRegistry = [];

  function createChart(canvas, config) {
    if (!window.Chart || !canvas) return null;
    var existing = window.Chart.getChart(canvas);
    if (existing) existing.destroy();
    var chart = new window.Chart(canvas, config);
    chartRegistry.push(chart);
    return chart;
  }

  function initChartsFromDom() {
    if (!window.Chart) return;

    document.querySelectorAll("canvas[data-chart]").forEach(function (canvas) {
      var type = canvas.getAttribute("data-chart") || "line";
      var raw = canvas.getAttribute("data-chart-payload");
      if (!raw) return;
      var payload;
      try {
        payload = JSON.parse(raw);
      } catch (e) {
        console.warn("EDUNOVA chart payload invalid", e);
        return;
      }
      var c = chartColors();
      var options = Object.assign({}, baseChartOptions(), payload.options || {});
      if (type === "doughnut" || type === "pie" || type === "radar") {
        delete options.scales;
      }
      createChart(canvas, {
        type: type,
        data: {
          labels: payload.labels || [],
          datasets: (payload.datasets || []).map(function (ds, i) {
            var colors = [c.primary, c.accent, c.success, c.warning, c.danger];
            return Object.assign(
              {
                borderColor: colors[i % colors.length],
                backgroundColor:
                  type === "line"
                    ? "rgba(56,189,248,0.12)"
                    : colors[i % colors.length],
                tension: 0.35,
                fill: type === "line",
                borderWidth: 2,
              },
              ds
            );
          }),
        },
        options: options,
      });
    });
  }

  function refreshChartsOnTheme() {
    window.addEventListener("nexora:themechange", function () {
      // Re-init from DOM payloads so colors match theme
      chartRegistry.slice().forEach(function (ch) {
        try { ch.destroy(); } catch (e) { /* ignore */ }
      });
      chartRegistry = [];
      initChartsFromDom();
    });
  }

  /* ---------- Boot ---------- */
  function boot() {
    applyTheme(getPreferredTheme());

    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.addEventListener("click", toggleTheme);
    });

    initSidebar();
    initTabs();
    initForms();
    initOnboardingProgress();
    initChartsFromDom();
    refreshChartsOnTheme();

    // Flash messages already rendered as .toast — auto dismiss
    document.querySelectorAll("#toast-area .toast[data-autodismiss]").forEach(function (el) {
      var ms = parseInt(el.getAttribute("data-autodismiss"), 10) || 4200;
      setTimeout(function () {
        if (el.parentNode) el.remove();
      }, ms);
    });
  }

  // Early theme to avoid flash (also run inline in base if needed)
  applyTheme(getPreferredTheme());

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.Nexora = {
    toast: toast,
    toggleTheme: toggleTheme,
    applyTheme: applyTheme,
    createChart: createChart,
    chartColors: chartColors,
    baseChartOptions: baseChartOptions,
    csrfToken: csrfToken,
    apiFetch: apiFetch,
    resetLoadingButtons: resetLoadingButtons,
  };
})();
