import { LitElement, html } from "https://esm.sh/lit@3";

/**
 * Render a money amount with the browser's currency rules.
 *
 * The element carries the amount and the ISO currency code and formats both
 * for the page language, so 0.69 EUR reads as "€0.69" in en-US and "0,69 €"
 * in de-DE.
 */
export class RelayAmount extends LitElement {
  static properties = {
    amount: { type: Number },
    currency: { type: String },
  };

  render() {
    return html`${new Intl.NumberFormat(document.documentElement.lang, {
      style: "currency",
      currency: this.currency,
    }).format(this.amount)}`;
  }
}

customElements.define("relay-amount", RelayAmount);
