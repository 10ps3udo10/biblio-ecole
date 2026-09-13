(() => {
  const root = document.documentElement;
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  function apply(preference) {
    root.dataset.themePreference = preference;
    root.dataset.theme = preference === "dark" || (preference === "system" && system.matches) ? "dark" : "light";
  }
  apply(root.dataset.themePreference || "light");
  system.addEventListener("change", () => apply(root.dataset.themePreference));
  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("appearance-form");
    if (form) form.addEventListener("change", (event) => {
      if (event.target.name === "theme") apply(event.target.value);
    });
  });
})();
