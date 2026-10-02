// Must run before first paint, so keep this a classic (blocking) script.
// Loading it as a module would defer it and flash the light theme.
if (matchMedia("(prefers-color-scheme: dark)").matches) {
  document.documentElement.classList.add("dark");
}
