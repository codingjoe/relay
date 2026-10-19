import { LitElement, html } from "lit";

const cache = new Map();
const ENDPOINT = "https://ipapi.co/";

/** Show the network behind an address, with an optional map. */
export class NetworkLocation extends LitElement {
  static properties = {
    address: { type: String },
    map: { type: Boolean },
    details: { state: true },
    error: { state: true },
    loading: { state: true },
    mapReady: { state: true },
  };

  constructor() {
    super();
    this.address = "";
    this.map = false;
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
    // Dialogs keep their content out of view until opened, so the lookup
    // waits for the first paint instead of running for every message.
    this.observer = new IntersectionObserver(async (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        this.observer.disconnect();
        this.visible = true;
        if (this.map) {
          try {
            await import("#js/map.js");
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
    return document.getElementById("transmission-profile")?.dataset ?? {};
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
      const response = await fetch(`${ENDPOINT}${encodeURIComponent(address)}/json/`);
      const data = await response.json();
      if (data.error) {
        throw new Error(data.reason || "lookup failed");
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
    return [
      this.details?.city,
      this.details?.region,
      this.details?.country_name ?? this.details?.country,
    ]
      .filter(Boolean)
      .join(", ");
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
          <code class="text-sm font-medium">${this.address}</code>
          <div class="skeleton h-3 w-40"></div>
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
      <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
        <code class="text-sm font-medium">${this.address}</code>
        <span class="text-xs text-muted-foreground">
          ${this.labels.unavailable || "Location unavailable."}
        </span>
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
        <code class="text-sm font-medium">${this.address}</code>
        ${
          this.location
            ? html`<span class="text-sm text-muted-foreground">${this.location}</span>`
            : ""
        }
        ${
          this.details.org || this.details.isp
            ? html`<span class="badge" data-variant="secondary"
                >${this.details.org || this.details.isp}</span
              >`
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
            this.details.org || this.details.isp
              ? html`<div class="card-action">
                  <span class="badge" data-variant="secondary"
                    >${this.details.org || this.details.isp}</span
                  >
                </div>`
              : ""
          }
        </header>
      </div>
    `;
  }

  render() {
    if (!this.address) {
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
