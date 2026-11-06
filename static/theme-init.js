// Applies the saved (or system) theme before first paint to avoid a flash of
// the wrong theme. Must be an external classic script (CSP: script-src 'self').
(function () {
  try {
    var t = localStorage.getItem("riskmatris_theme");
    if (t !== "dark" && t !== "light") {
      t = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    document.documentElement.dataset.theme = t;
  } catch (e) {
    /* localStorage unavailable – default light theme */
  }
})();
