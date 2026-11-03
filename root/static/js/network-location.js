import { LitElement, html } from "lit";

const cache = new Map();
const ENDPOINT = "https://ipwho.is/";

/** Return whether the address is routable on the public internet. */
function isPublicAddress(address) {
  if (address.includes(":")) {
    const normalized = address.toLowerCase();
    return !(
      normalized === "::1" ||
      normalized.startsWith("fe80:") ||
      /^f[cd][0-9a-f]{2}:/.test(normalized)
    );
  }
  const parts = address.split(".").map(Number);
  if (
    parts.length !== 4 ||
    parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)
  ) {
    return false;
  }
  const [first, second] = parts;
  return !(
    first === 0 ||
    first === 10 ||
    first === 127 ||
    (first === 169 && second === 254) ||
    (first === 172 && second >= 16 && second <= 31) ||
    (first === 192 && second === 168) ||
    (first === 100 && second >= 64 && second <= 127) ||
    first >= 224
  );
}

/** Show the network behind an address, with an optional map. */
export class NetworkLocation extends LitElement {
  static properties = {
    address: { type: String },
    map: { type: Boolean },
    hideAddress: { type: Boolean, attribute: "hide-address" },
    details: { state: true },
    error: { state: true },
    loading: { state: true },
    mapReady: { state: true },
  };

  constructor() {
    super();
    this.address = "";
    this.map = false;
    this.hideAddress = false;
    this.details = null;
    this.error = false;
    this.loading = false;
    this.mapReady = false;
    this.visible = false;
    this.pending = "";
  }

  createRenderRoot() {
    return this;
  }

  connectedCallback() {
    super.connectedCallback();
    // Private addresses have no public location, so skip the lookup and the
    // placeholder entirely.
    if (!isPublicAddress(this.address)) {
      this.skipped = true;
      return;
    }
    // Dialogs keep their content out of view until opened, so the lookup
    // waits for the first paint instead of running for every message.
    this.observer = new IntersectionObserver(async (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        this.observer.disconnect();
        this.visible = true;
        if (this.map) {
          try {
            await import("#js/location-map.js");
            this.mapReady = true;
          } catch {
            this.map = false;
          }
        }
        this.lookup();
      }
    });
    this.observer.observe(this);
  }

  disconnectedCallback() {
    this.observer?.disconnect();
    super.disconnectedCallback();
  }

  updated(changedProperties) {
    if (changedProperties.has("address") && this.visible) {
      this.lookup();
    }
  }

  get labels() {
    const labels = document.getElementById("transmission-profile")?.dataset ?? {};
    return {
      unavailable: this.dataset.unavailable || labels.unavailable,
      retry: this.dataset.retry || labels.retry,
      map: labels.map,
    };
  }

  async lookup() {
    const address = this.address;
    if (!address || this.pending === address) {
      return;
    }
    if (cache.has(address)) {
      this.details = cache.get(address);
      this.error = false;
      this.loading = false;
      return;
    }
    this.pending = address;
    this.loading = true;
    this.error = false;
    try {
      const response = await fetch(`${ENDPOINT}${encodeURIComponent(address)}`, {
        referrerPolicy: "no-referrer",
        signal: AbortSignal.timeout(8000),
      });
      const data = await response.json();
      if (!data.success) {
        throw new Error(data.message || "lookup failed");
      }
      cache.set(address, data);
      if (this.address === address) {
        this.details = data;
      }
    } catch {
      if (this.address === address) {
        this.error = true;
      }
    } finally {
      if (this.address === address) {
        this.loading = false;
        this.pending = "";
      }
    }
  }

  get location() {
    return [this.details?.city, this.details?.region, this.details?.country]
      .filter(Boolean)
      .join(", ");
  }

  get network() {
    return this.details?.connection?.org || this.details?.connection?.isp;
  }

  renderMap() {
    const { latitude, longitude } = this.details;
    const label = `${this.labels.map || "Map"}: ${this.address}`;
    return html`
      <location-map
        class="block aspect-[3/2] w-full border-b border-border"
        data-latitude=${latitude}
        data-longitude=${longitude}
        aria-label=${label}
      ></location-map>
    `;
  }

  renderSkeleton() {
    if (!this.map) {
      return html`
        <div class="flex flex-col gap-1.5">
          ${
            this.hideAddress
              ? ""
              : html`<code class="text-sm font-medium">${this.address}</code>`
          }
          <div class="skeleton h-5 w-40"></div>
        </div>
      `;
    }
    return html`
      <div class="card gap-0 overflow-hidden p-0" data-size="sm">
        <div class="skeleton aspect-[3/2] w-full rounded-none"></div>
        <header class="p-4">
          <h3><code>${this.address}</code></h3>
          <div class="skeleton h-3 w-40"></div>
        </header>
      </div>
    `;
  }

  renderUnavailable() {
    return html`
      <div
        class="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-muted-foreground"
      >
        ${
          this.hideAddress ? "" : html`<code class="font-medium">${this.address}</code>`
        }
        <span>${this.labels.unavailable || "Location unavailable."}</span>
        <span aria-hidden="true">·</span>
        <button
          type="button"
          class="btn"
          data-variant="link"
          data-size="xs"
          @click=${() => this.lookup()}
        >
          ${this.labels.retry || "Retry"}
        </button>
      </div>
    `;
  }

  renderSummary() {
    return html`
      <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
        ${
          this.hideAddress
            ? ""
            : html`<code class="text-sm font-medium">${this.address}</code>`
        }
        ${
          this.network
            ? html`<span class="badge" data-variant="secondary">${this.network}</span>`
            : ""
        }
        ${
          this.location
            ? html`<span class="text-sm text-muted-foreground">${this.location}</span>`
            : ""
        }
      </div>
    `;
  }

  renderCard() {
    const hasMap =
      typeof this.details.latitude === "number" &&
      typeof this.details.longitude === "number";
    return html`
      <div class="card gap-0 overflow-hidden ${hasMap ? "p-0" : ""}" data-size="sm">
        ${
          hasMap
            ? this.mapReady
              ? this.renderMap()
              : html`<div class="skeleton aspect-[3/2] w-full rounded-none"></div>`
            : ""
        }
        <header class="${hasMap ? "p-4" : ""}">
          <h3><code>${this.address}</code></h3>
          ${this.location ? html`<p>${this.location}</p>` : ""}
          ${
            this.network
              ? html`<div class="card-action">
                  <span class="badge" data-variant="secondary">${this.network}</span>
                </div>`
              : ""
          }
        </header>
      </div>
    `;
  }

  render() {
    if (!this.address || this.skipped) {
      return html``;
    }
    if (this.loading) {
      return this.renderSkeleton();
    }
    if (this.error || !this.details) {
      return this.renderUnavailable();
    }
    return this.map ? this.renderCard() : this.renderSummary();
  }
}

customElements.define("network-location", NetworkLocation);
