import { LitElement, html } from "https://esm.sh/lit@3";

/**
 * Render a money amount with the browser's currency rules.
 *
 * The element carries the amount and the ISO currency code and formats both
 * for the page language, so 0.69 EUR reads as "€0.69" in en-US and "0,69 €"
 * in de-DE. The markup inside the element is the server-rendered amount: it
 * shows until the element upgrades, and whenever the browser cannot format
 * the currency.
 */
export class RelayAmount extends LitElement {
  static properties = {
    amount: { type: Number },
    currency: { type: String },
  };

  connectedCallback() {
    this.fallback ??= this.textContent.trim();
    super.connectedCallback();
  }

  format() {
    try {
      return new Intl.NumberFormat(document.documentElement.lang, {
        style: "currency",
        currency: this.currency,
      }).format(this.amount);
    } catch {
      return null;
    }
  }

  render() {
    return html`${this.format() ?? this.fallback}`;
  }
}

customElements.define("relay-amount", RelayAmount);
