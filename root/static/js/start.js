import hljs from "https://esm.sh/highlight.js@11.11.1/lib/common";

const slider = document.getElementById("price-slider");
const amount = document.getElementById("price-amount");
const volume = document.getElementById("price-volume");

if (slider && amount && volume) {
  const free = Number(slider.dataset.free);
  const perThousand = Number(slider.dataset.perThousand);

  function formatVolume(count) {
    return count.toLocaleString("en-US");
  }

  function formatEur(value) {
    return new Intl.NumberFormat("en-IE", {
      style: "currency",
      currency: "EUR",
    }).format(value);
  }

  function update() {
    const messages = Number(slider.value);
    const total = ((messages - free) / 1000) * perThousand;
    volume.textContent = formatVolume(messages);
    amount.textContent = formatEur(total);
  }

  slider.addEventListener("input", update);
  update();
}

for (const block of document.querySelectorAll("pre code[class*='language-']")) {
  hljs.highlightElement(block);
}
