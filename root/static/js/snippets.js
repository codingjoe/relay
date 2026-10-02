import { highlightAll } from "microlighter";

for (const tabs of document.querySelectorAll(".tabs")) {
  tabs.addEventListener("click", () => highlightAll());
}

await highlightAll();
