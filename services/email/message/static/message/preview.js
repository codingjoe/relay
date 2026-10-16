// Preview the HTML body the way a mail client would.

const STORAGE_KEY = "relay:message-preview";

// Mirror the field defaults of MessagePreview.
const DEFAULTS = { client: "gmail", theme: "light" };

const root = document.querySelector("[data-message-preview]");
const frame = root?.querySelector("[data-preview-frame]");
const menu = root?.querySelector("#preview-command-menu");
const summary = root?.querySelector("[data-preview-summary]");
const toggle = root?.querySelector("#preview-theme-toggle");
const trigger = root?.querySelector("#preview-options-trigger");

const THEMES = ["light", "dark"];

function themeIcons() {
  return Object.fromEntries(
    [...toggle.querySelectorAll("[data-preview-icon]")].map((icon) => [
      icon.dataset.previewIcon,
      icon,
    ]),
  );
}

function clientIcons() {
  return Object.fromEntries(
    [...trigger.querySelectorAll("[data-preview-client-icon]")].map((icon) => [
      icon.dataset.previewClientIcon,
      icon,
    ]),
  );
}

/** @returns {object} The stored mode, or an empty object when storage is refused. */
function storedMode() {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return stored && typeof stored === "object" ? stored : {};
  } catch {
    return {};
  }
}

/** @returns {string} The label of the client one value names. */
function clientLabel(value) {
  const item = clientItems().find(
    (item) => item.getAttribute("data-preview-client") === value,
  );
  return item?.dataset.filter ?? value;
}

function clientItems() {
  return [...root.querySelectorAll("[data-preview-client]")];
}

function currentMode() {
  return {
    client: root.dataset.previewClient ?? DEFAULTS.client,
    theme: root.dataset.previewTheme ?? DEFAULTS.theme,
  };
}

/**
 * Return the address of the frame in one mode.
 *
 * Defaults stay out of the address, so the default mode keeps the frame URL
 * the page rendered and does not reload it.
 *
 * @param {object} mode - The mode to show.
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

/** Show the mode in the frame, the check mark, the toggle, and the label. */
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
  for (const [client, icon] of Object.entries(clientIcons())) {
    icon.hidden = client !== mode.client;
  }
  const url = frameUrl(mode);
  if (frame.getAttribute("src") !== url) {
    frame.src = url;
  }
  summary.textContent = clientLabel(mode.client);
}

/** Show the mode and keep it for the next visit. */
function keepMode(mode) {
  applyMode(mode);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(mode));
  } catch {
    // A refused storage only costs the mode of the next visit.
  }
}

if (root && frame && menu && summary && toggle && trigger) {
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
