import { highlightAll } from "https://cdn.jsdelivr.net/npm/microlighter@2/dist/index.js";

for (const tabs of document.querySelectorAll(".tabs")) {
  tabs.addEventListener("click", () => highlightAll());
}

await highlightAll();
