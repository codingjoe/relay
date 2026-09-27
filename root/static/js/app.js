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

class Action {
  static names = ["dialog", "dialog-close", "copy", "share", "href", "toggle"];

  static selector = Action.names
    .map((name) => `[data-${name}]`)
    .concat("[data-confirm]")
    .join(", ");

  constructor(trigger) {
    this.trigger = trigger;
    this.name = Action.names.find((name) => trigger.hasAttribute(`data-${name}`));
  }

  static within(target) {
    const trigger = target.closest(Action.selector);
    return trigger && new Action(trigger);
  }

  element(id) {
    return document.getElementById(id);
  }

  confirmed() {
    const message = this.trigger.dataset.confirm;
    return !message || globalThis.confirm(message);
  }

  run() {
    if (this.name) this[this.name]();
  }

  dialog() {
    this.element(this.trigger.dataset.dialog)?.showModal();
  }

  "dialog-close"() {
    const name = this.trigger.dataset.dialogClose;
    (name ? this.element(name) : this.trigger.closest("dialog"))?.close();
  }

  copy() {
    navigator.clipboard?.writeText(this.trigger.dataset.copy);
  }

  share() {
    sharePage();
  }

  href() {
    globalThis.location.href = this.trigger.dataset.href;
  }

  toggle() {
    this.element(this.trigger.dataset.toggle)?.toggle();
  }
}

document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) return;
  const backdrop = target.closest("dialog[data-backdrop-close]");
  if (backdrop && event.target === backdrop) {
    backdrop.close();
    return;
  }
  const action = Action.within(target);
  if (!action) return;
  if (!action.confirmed()) {
    event.preventDefault();
    return;
  }
  if (action.name) {
    event.preventDefault();
    action.run();
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
