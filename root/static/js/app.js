(() => {
  try {
    const stored = localStorage.getItem("themeMode");
    if (stored ? stored === "dark" : matchMedia("(prefers-color-scheme: dark)").matches) {
      document.documentElement.classList.add("dark");
    }
  } catch (_) {}
})();

function sharePage() {
  const url = globalThis.location.href;
  navigator.clipboard?.writeText(url);
  if (navigator.share) navigator.share({ title: document.title, url }).catch(() => {});
}

function openDialog(name) {
  return document.getElementById(name)?.showModal();
}

function closeDialog(trigger, name) {
  return (name ? document.getElementById(name) : trigger.closest("dialog"))?.close();
}

const actions = {
  dialog: (trigger) => openDialog(trigger.dataset.dialog),
  "dialog-close": (trigger) => closeDialog(trigger, trigger.dataset.dialogClose),
  copy: (trigger) => navigator.clipboard?.writeText(trigger.dataset.copy),
  share: () => sharePage(),
  href: (trigger) => {
    globalThis.location.href = trigger.dataset.href;
  },
  toggle: (trigger) => document.getElementById(trigger.dataset.toggle)?.toggle(),
};

const ACTION_SELECTOR = Object.keys(actions)
  .map((name) => `[data-${name}]`)
  .concat("[data-confirm]")
  .join(", ");

document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) return;
  const backdrop = target.closest("dialog[data-backdrop-close]");
  if (backdrop && event.target === backdrop) {
    backdrop.close();
    return;
  }
  const trigger = target.closest(ACTION_SELECTOR);
  if (!trigger) return;
  if (trigger.dataset.confirm && !globalThis.confirm(trigger.dataset.confirm)) {
    event.preventDefault();
    return;
  }
  const action = Object.keys(actions).find((name) => trigger.hasAttribute(`data-${name}`));
  if (action) {
    event.preventDefault();
    actions[action](trigger);
  }
});

document.addEventListener("focusin", (event) => {
  if (event.target instanceof HTMLInputElement && event.target.hasAttribute("data-select")) {
    event.target.select();
  }
});

document.addEventListener("change", ({ target: select }) => {
  if (!(select instanceof HTMLSelectElement) || !select.dataset.mirror) return;
  const target = document.getElementById(select.dataset.mirror);
  if (target) {
    const prefix = select.dataset.mirrorPrefix ?? "";
    target.textContent = `${prefix}${select.selectedOptions[0]?.textContent ?? ""}`;
  }
});

document.addEventListener("DOMContentLoaded", () => {
  for (const dialog of document.querySelectorAll("dialog[data-auto-open]")) {
    dialog.showModal();
  }
  if (globalThis.lucide) globalThis.lucide.createIcons();
});
