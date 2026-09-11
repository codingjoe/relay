const probe = document.createElement("canvas").getContext("2d", {
  willReadFrequently: true,
});
const swatch = document.body.appendChild(document.createElement("span"));
swatch.hidden = true;

export function toRgba(value, alpha = 1, fallback = "#71717a") {
  const name = value.startsWith("var(") ? value.slice(4, -1) : null;
  const color = name
    ? getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    : value;
  swatch.style.color = color || fallback;
  probe.clearRect(0, 0, 1, 1);
  probe.fillStyle = getComputedStyle(swatch).color;
  probe.fillRect(0, 0, 1, 1);
  const [red, green, blue, sourceAlpha] = probe.getImageData(0, 0, 1, 1).data;
  return `rgba(${red}, ${green}, ${blue}, ${(sourceAlpha / 255) * alpha})`;
}
