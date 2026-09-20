import { LitElement, html } from "https://esm.sh/lit@3";

/** Render a money amount for the page language, e.g. "€0.69" or "0,69 €". */
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
