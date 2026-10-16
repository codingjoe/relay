const slider = document.getElementById("price-slider");
const amount = document.getElementById("price-amount");
const volume = document.getElementById("price-volume");

if (slider && amount && volume) {
  const free = Number(slider.dataset.free);
  const perThousand = Number(slider.dataset.perThousand);

  function formatVolume(count) {
    return count.toLocaleString("en-US");
  }

  function update() {
    const messages = Number(slider.value);
    const total = ((messages - free) / 1000) * perThousand;
    volume.textContent = formatVolume(messages);
    amount.setAttribute("amount", String(total));
  }

  slider.addEventListener("input", update);
  update();
}
