// Preview modes of the HTML body: client and theme.
//
// The frame carries the mode in its own query, so the mode is applied by the
// server and the frame stays sandboxed and script free. The mode of this
// visit is kept in local storage, and it never leaves the frame URL.

const STORAGE_KEY = "relay:message-preview";

// The server renders the frame in the default mode, so these mirror the field
// defaults of MessagePreview.
const DEFAULTS = { client: "gmail", theme: "light" };

const root = document.querySelector("[data-message-preview]");
const frame = root?.querySelector("[data-preview-frame]");
const menu = root?.querySelector("#preview-command-menu");
const summary = root?.querySelector("[data-preview-summary]");
const toggle = root?.querySelector("#preview-theme-toggle");

const THEMES = ["light", "dark"];

/** @returns {object} The sun and moon the toggle swaps. */
function themeIcons() {
  return Object.fromEntries(
    [...toggle.querySelectorAll("[data-preview-icon]")].map((icon) => [
      icon.dataset.previewIcon,
      icon,
    ]),
  );
}

/**
 * Return the stored mode, or an empty object when storage is refused.
 *
 * @returns {object} The stored mode.
 */
function storedMode() {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return stored && typeof stored === "object" ? stored : {};
  } catch {
    return {};
  }
}

/**
 * Return the label of the client one value names.
 *
 * @param {string} value - The client value.
 * @returns {string} The label, or the value when no item carries it.
 */
function clientLabel(value) {
  const item = clientItems().find(
    (item) => item.getAttribute("data-preview-client") === value,
  );
  return item?.dataset.filter ?? value;
}

/** @returns {Element[]} The client menu items. */
function clientItems() {
  return [...root.querySelectorAll("[data-preview-client]")];
}

/** @returns {object} The mode the page currently shows. */
function currentMode() {
  return {
    client: root.dataset.previewClient ?? DEFAULTS.client,
    theme: root.dataset.previewTheme ?? DEFAULTS.theme,
  };
}

/**
 * Point the frame at the mode.
 *
 * The defaults stay out of the address, so the default mode keeps the frame
 * URL the page rendered and never reloads it.
 *
 * @param {object} mode - The mode to show.
 * @returns {string} The address of the frame.
 */
function frameUrl(mode) {
  const url = new URL(frame.src);
  for (const key of Object.keys(DEFAULTS)) {
    if (mode[key] === DEFAULTS[key]) {
      url.searchParams.delete(key);
    } else {
      url.searchParams.set(key, mode[key]);
    }
  }
  return `${url.pathname}${url.search}`;
}

/**
 * Show one mode: the frame, the client check mark, the toggle, and the label.
 *
 * @param {object} mode - The mode to show.
 */
function applyMode(mode) {
  root.dataset.previewClient = mode.client;
  root.dataset.previewTheme = mode.theme;
  for (const item of clientItems()) {
    item.dataset.checked = String(
      item.getAttribute("data-preview-client") === mode.client,
    );
  }
  toggle.setAttribute("aria-pressed", String(mode.theme === "dark"));
  for (const [theme, icon] of Object.entries(themeIcons())) {
    icon.hidden = theme !== mode.theme;
  }
  const url = frameUrl(mode);
  if (frame.getAttribute("src") !== url) {
    frame.src = url;
  }
  summary.textContent = clientLabel(mode.client);
}

/**
 * Show the mode, and keep it for the next visit.
 *
 * @param {object} mode - The mode to show.
 */
function keepMode(mode) {
  applyMode(mode);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(mode));
  } catch {
    // A refused storage only costs the mode of the next visit.
  }
}

if (root && frame && menu && summary && toggle) {
  const restored = currentMode();
  const stored = storedMode();
  if (
    clientItems().some(
      (item) => item.getAttribute("data-preview-client") === stored.client,
    )
  ) {
    restored.client = stored.client;
  }
  if (THEMES.includes(stored.theme)) {
    restored.theme = stored.theme;
  }
  applyMode(restored);

  menu.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const item = target?.closest("[data-preview-client]");
    if (item) {
      keepMode({
        ...currentMode(),
        client: item.getAttribute("data-preview-client"),
      });
    }
  });

  toggle.addEventListener("click", () => {
    const mode = currentMode();
    keepMode({ ...mode, theme: mode.theme === "dark" ? "light" : "dark" });
  });
}
