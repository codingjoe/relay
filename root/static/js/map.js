import { Map, Marker, getVersion, setWorkerUrl } from "maplibre-gl";

const LIGHT_STYLE = "https://tiles.openfreemap.org/styles/positron";
const DARK_STYLE = "https://tiles.openfreemap.org/styles/dark";

setWorkerUrl(`/esm/maplibre-gl-worker.mjs?v=${getVersion()}`);

/** Render a small vector map around one coordinate. */
class LocationMap extends HTMLElement {
  connectedCallback() {
    const latitude = Number(this.dataset.latitude);
    const longitude = Number(this.dataset.longitude);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      return;
    }
    const zoom = 11;
    const dark = matchMedia("(prefers-color-scheme: dark)").matches;
    const color =
      getComputedStyle(this).getPropertyValue("--color-primary").trim() || "#6200d1";
    // Safari loses the WebGL context when MapLibre requests high-performance GPU, so drop that hint during creation.
    const safari = /^((?!chrome|android|crios|fxios).)*safari/i.test(
      navigator.userAgent,
    );
    const getContext = HTMLCanvasElement.prototype.getContext;
    if (safari) {
      HTMLCanvasElement.prototype.getContext = function (type, attributes) {
        if (type === "webgl2" && attributes) {
          attributes = { ...attributes, powerPreference: undefined };
        }
        return getContext.call(this, type, attributes);
      };
    }
    try {
      this.map = new Map({
        container: this,
        style: dark ? DARK_STYLE : LIGHT_STYLE,
        center: [longitude, latitude],
        zoom,
        minZoom: -2,
        interactive: false,
        attributionControl: true,
      });
    } finally {
      if (safari) {
        HTMLCanvasElement.prototype.getContext = getContext;
      }
    }
    new Marker({ color }).setLngLat([longitude, latitude]).addTo(this.map);
  }

  disconnectedCallback() {
    this.map?.remove();
  }
}

customElements.define("location-map", LocationMap);
