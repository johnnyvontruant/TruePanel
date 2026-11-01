(function () {
  "use strict";

  const root = document.documentElement;
  const darkPreference = window.matchMedia("(prefers-color-scheme: dark)");

  function effectiveDarkMode() {
    const explicitTheme = root.dataset.theme;
    if (explicitTheme === "dark") return true;
    if (explicitTheme === "light") return false;
    return darkPreference.matches;
  }

  function syncThemeToggle() {
    const toggle = document.getElementById("themeToggle");
    if (!toggle) return;

    const darkMode = effectiveDarkMode();
    const lightIcon = toggle.querySelector(".theme-emoji-light");
    const darkIcon = toggle.querySelector(".theme-emoji-dark");

    if (lightIcon) lightIcon.style.display = darkMode ? "none" : "inline";
    if (darkIcon) darkIcon.style.display = darkMode ? "inline" : "none";

    const action = darkMode ? "Switch to light mode" : "Switch to dark mode";
    toggle.setAttribute("aria-label", action);
    toggle.setAttribute("title", action);
  }

  syncThemeToggle();

  new MutationObserver(syncThemeToggle).observe(root, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });

  if (typeof darkPreference.addEventListener === "function") {
    darkPreference.addEventListener("change", syncThemeToggle);
  } else if (typeof darkPreference.addListener === "function") {
    darkPreference.addListener(syncThemeToggle);
  }

  window.addEventListener("pageshow", syncThemeToggle);
})();
