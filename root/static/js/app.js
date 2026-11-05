import "basecoat-css/all.min";
import Mousetrap from "mousetrap";

function sharePage() {
  const url = globalThis.location.href;
  navigator.clipboard?.writeText(url);
  if (navigator.share) navigator.share({ title: document.title, url }).catch(() => {});
}

let copyToast;

function copyText(value) {
  const written = navigator.clipboard?.writeText(value);
  if (!written) return;
  written.then(
    () => {
      const toaster = document.getElementById("toaster");
      if (!toaster?.toast) return;
      copyToast?.close?.();
      copyToast = toaster.toast({
        category: "success",
        title: toaster.dataset.copiedMessage ?? "Copied",
        duration: 2000,
      });
    },
    () => {},
  );
}

class Action {
  static names = ["dialog", "dialog-close", "copy", "share", "href", "toggle"];

  static selector = Action.names
    .map((name) => `[data-${name}]`)
    .concat("[data-confirm]", "[data-copy-target]")
    .join(", ");

  constructor(trigger) {
    this.trigger = trigger;
    this.name = Action.names.find((name) => trigger.hasAttribute(`data-${name}`));
    if (!this.name && trigger.hasAttribute("data-copy-target")) this.name = "copy";
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
    const id = this.trigger.dataset.copyTarget;
    const target = id ? this.element(id) : null;
    const value = target ? target.textContent.trim() : this.trigger.dataset.copy;
    if (value) copyText(value);
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
  if (
    event.target instanceof HTMLInputElement &&
    event.target.hasAttribute("data-select")
  ) {
    event.target.select();
  }
});

document.addEventListener("click", (event) => {
  if (
    event.target instanceof HTMLInputElement &&
    event.target.hasAttribute("data-select")
  ) {
    event.target.select();
    copyText(event.target.dataset.copyValue ?? event.target.value);
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

const adminUrl = document.body.dataset.adminUrl;
if (adminUrl) {
  Mousetrap.bind(
    "g a",
    (event) => {
      event.preventDefault();
      globalThis.location.href = adminUrl;
    },
    "keydown",
  );
}

document.addEventListener("DOMContentLoaded", () => {
  for (const dialog of document.querySelectorAll("dialog[data-auto-open]")) {
    dialog.showModal();
  }
});
