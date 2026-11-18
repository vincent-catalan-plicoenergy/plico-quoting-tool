/* API client and formatting helpers for the Plico quoting tool. */
(function (global) {
  "use strict";

  async function request(path, options) {
    const res = await fetch(path, options);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error || `Request failed (${res.status})`);
    return body;
  }

  const PlicoApi = {
    getConfig: () => request("/api/config"),
    getQuote: (payload) =>
      request("/api/quote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
  };

  const aud = new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD" });
  const PlicoFormat = {
    money: (n) => (n === null || n === undefined ? "–" : aud.format(n)),
    num: (n, unit = "") => (n === null || n === undefined ? "–" : `${Number(n).toLocaleString("en-AU")}${unit}`),
    escape: (s) =>
      String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])),
  };

  global.PlicoApi = PlicoApi;
  global.PlicoFormat = PlicoFormat;
})(window);
