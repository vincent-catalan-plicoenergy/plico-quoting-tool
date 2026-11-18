/* UI logic: builds the form options, sends the quote request, renders the proposal. */
(function () {
  "use strict";
  const { money, num, escape } = window.PlicoFormat;
  const form = document.getElementById("quote-form");
  const results = document.getElementById("results");
  const STORAGE_KEY = "plico-quote-draft";
  let config = null;
  let lastQuote = null;
  let timer = null;

  const EXAMPLE = {
    customer_name: "Parmelia example", postcode: "6167", residential_status: "owner",
    objective: "lower_bills", quarterly_bill: 300, has_existing_solar: true,
    existing_panel_count: 5, existing_system_age_years: 12, phase: "single",
    roof_type: "tile", storeys: "1", solution_type: "full_system",
    package: "energy_creator_10", payment_type: "plico_finance",
    plico_finance_term_months: 60, join_vpp: true, wa_rebate_eligible: true,
  };

  // ---------- form helpers ----------
  function option(value, label) {
    const o = document.createElement("option");
    o.value = value;
    o.textContent = label;
    return o;
  }

  function readForm() {
    const data = { site_adders: [] };
    for (const el of form.elements) {
      if (!el.name) continue;
      if (el.type === "checkbox") {
        if (el.dataset.adder) { if (el.checked) data.site_adders.push(el.name); }
        else data[el.name] = el.checked;
      } else if (el.value !== "") {
        data[el.name] = el.type === "number" ? Number(el.value) : el.value;
      }
    }
    return data;
  }

  function writeForm(data) {
    form.reset();
    for (const el of form.elements) {
      if (!el.name) continue;
      if (el.type === "checkbox") {
        el.checked = el.dataset.adder ? (data.site_adders || []).includes(el.name) : !!data[el.name];
      } else if (data[el.name] !== undefined) {
        el.value = data[el.name];
      }
    }
    applyDefaults();
    refresh();
  }

  function applyDefaults() {
    const set = (name, value) => {
      const el = form.elements[name];
      if (el && el.value === "") el.value = value;
    };
    set("markup_pct", config.default_markup_pct);
    set("tariff_per_kwh", config.savings_defaults.tariff_per_kwh);
    set("supply_charge_per_day", config.savings_defaults.supply_charge_per_day);
    set("feed_in_per_kwh", config.savings_defaults.feed_in_per_kwh);
  }

  function toggleGroups() {
    const d = readForm();
    form.querySelectorAll("[data-show-if]").forEach((g) => (g.hidden = !d[g.dataset.showIf]));
    form.querySelectorAll("[data-show-if-package]").forEach((g) => (g.hidden = d.package !== g.dataset.showIfPackage));
    form.querySelectorAll("[data-show-if-payment]").forEach(
      (g) => (g.hidden = !g.dataset.showIfPayment.split(" ").includes(d.payment_type)));
  }

  // ---------- rendering ----------
  function rows(items) {
    return items.map((i) => `<tr><td>${escape(i.label)}</td><td class="num">${money(i.amount)}</td></tr>`).join("");
  }

  function list(title, items) {
    if (!items.length) return "";
    return `<h4>${title}</h4><ul>${items.map((i) => `<li>${escape(i)}</li>`).join("")}</ul>`;
  }

  function render(q) {
    const s = q.system, p = q.pricing, f = q.finance, sv = q.savings, r = q.readiness;
    const finRows = [];
    if (f.deposit) finRows.push(["Deposit", money(f.deposit)]);
    if (f.cash_balance) finRows.push(["Cash balance on install", money(f.cash_balance)]);
    if (f.interest_free_loan_amount) finRows.push([
      `Interest-free loan (${f.interest_free_loan_term_months} months)`,
      `${money(f.interest_free_loan_amount)} · ${money(f.interest_free_loan_monthly)}/mth`]);
    if (f.plico_finance_amount) finRows.push([
      `Plico Finance (${f.plico_finance_term_months} months @ ${f.plico_finance_rate_pct}%)`,
      `${money(f.plico_finance_amount)} · ${money(f.plico_finance_monthly)}/mth`]);
    if (f.total_monthly) finRows.push(["<strong>Total monthly</strong>", `<strong>${money(f.total_monthly)}</strong>`]);
    const nothingMissing = !r.missing.customer.length && !r.missing.technical.length &&
      !r.missing.existing_system.length && !r.warnings.length;

    results.innerHTML = `
      <div class="status status-${r.level}">${escape(r.label)}
        <span>Site checks ${r.site_checks_complete}/${r.site_checks_total}</span></div>

      <div class="card headline">
        <div><span class="muted">Customer price</span><strong>${money(p.customer_price)}</strong></div>
        <div><span class="muted">Est. savings / qtr</span><strong>${money(sv.quarterly_savings)}</strong></div>
        <div><span class="muted">Payback</span><strong>${q.payback_years ?? "–"} yrs</strong></div>
        <div><span class="muted">Monthly</span><strong>${f.total_monthly ? money(f.total_monthly) : "–"}</strong></div>
      </div>

      <div class="card">
        <h3>${escape(s.package_label)} · ${escape(s.solution_label)}</h3>
        <table>
          <tr><td>Solar</td><td class="num">${num(s.pv_kw, " kW")}</td></tr>
          <tr><td>Inverter</td><td class="num">${s.new_inverter ? num(s.inverter_kw, " kW") + " · " : ""}${escape(s.inverter_model)}</td></tr>
          <tr><td>Battery</td><td class="num">${num(s.battery_kwh, " kWh")} · ${escape(s.battery_model)}</td></tr>
        </table>
      </div>

      <div class="card">
        <h3>Price</h3>
        <table>
          <tr><td>System price (before rebates)</td><td class="num">${money(p.gross_price)}</td></tr>
          ${p.incentives.map((i) => `<tr><td>less ${escape(i.label)}</td><td class="num">−${money(i.amount)}</td></tr>`).join("")}
          ${p.discounts.map((i) => `<tr><td>less ${escape(i.label)}</td><td class="num">−${money(i.amount)}</td></tr>`).join("")}
          <tr class="total"><td>Customer price</td><td class="num">${money(p.customer_price)}</td></tr>
        </table>
        ${finRows.length ? `<h4>Payment</h4><table>${finRows.map(([a, b]) => `<tr><td>${a}</td><td class="num">${b}</td></tr>`).join("")}</table>` : ""}
      </div>

      <div class="card">
        <h3>Estimated savings</h3>
        <table>
          <tr><td>Daily usage</td><td class="num">${num(sv.daily_usage_kwh, " kWh")}</td></tr>
          <tr><td>Current annual bill</td><td class="num">${money(sv.annual_bill_now)}</td></tr>
          <tr><td>Annual solar generation</td><td class="num">${num(sv.annual_generation_kwh, " kWh")}</td></tr>
          <tr><td>Self-consumed / exported</td><td class="num">${num(sv.annual_self_consumed_kwh)} / ${num(sv.annual_exported_kwh)} kWh</td></tr>
          <tr class="total"><td>Annual savings</td><td class="num">${money(sv.annual_savings)}</td></tr>
        </table>
      </div>

      <details class="card internal" open>
        <summary>Internal: cost &amp; margin (not for customer)</summary>
        <table>${rows(q.cost.lines)}
          <tr class="total"><td>System cost</td><td class="num">${money(q.cost.total)}</td></tr>
          <tr><td>Revenue (price + rebates/STCs)</td><td class="num">${money(p.revenue)}</td></tr>
          <tr class="total"><td>Gross profit</td><td class="num">${money(p.gross_profit)} (${p.gross_margin_pct}%)</td></tr>
        </table>
        <p class="muted">STCs: ${p.stcs.pv} solar, ${p.stcs.battery} battery · Pricing config ${escape(q.config_version)}</p>
      </details>

      <div class="card">
        <h3>Still needed</h3>
        ${list("Customer", r.missing.customer)}${list("Technical", r.missing.technical)}${list("Existing system", r.missing.existing_system)}
        ${list("Warnings", r.warnings)}
        ${nothingMissing ? "<p>Nothing outstanding.</p>" : ""}
      </div>

      <div class="actions no-print">
        <button type="button" onclick="window.print()">Print / save PDF</button>
        <button type="button" class="secondary" id="export-json">Export JSON</button>
      </div>`;

    document.getElementById("export-json").addEventListener("click", exportJson);
  }

  function exportJson() {
    const blob = new Blob([JSON.stringify({ input: readForm(), quote: lastQuote }, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `plico-quote-${lastQuote.customer.postcode || "draft"}-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  // ---------- quote loop ----------
  async function refresh() {
    toggleGroups();
    const data = readForm();
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    try {
      lastQuote = await window.PlicoApi.getQuote(data);
      render(lastQuote);
    } catch (err) {
      results.innerHTML = `<div class="status status-error">${escape(err.message)}</div>`;
    }
  }

  function scheduleRefresh() {
    clearTimeout(timer);
    timer = setTimeout(refresh, 250);
  }

  // ---------- init ----------
  async function init() {
    config = await window.PlicoApi.getConfig();
    document.getElementById("config-banner").textContent =
      `Pricing config ${config.version}. Placeholder figures – check against the Master Plico Quoting Tool before sending to a customer.`;

    const sol = document.getElementById("solution_type");
    Object.entries(config.solution_types).forEach(([k, v]) => sol.append(option(k, v)));
    const pkg = document.getElementById("package");
    Object.entries(config.packages).forEach(([k, v]) =>
      pkg.append(option(k, `${v.label} (${v.pv_kw} kW + ${v.battery_kwh} kWh)`)));
    pkg.append(option("custom", "Custom system"));
    config.finance.plico_finance_terms_months.forEach((m) => document.getElementById("plico_terms").append(option(m, `${m} months`)));
    config.finance.interest_free_loan_terms_months.forEach((m) => document.getElementById("ifl_terms").append(option(m, `${m} months`)));

    const adders = document.getElementById("site-adders");
    Object.entries(config.site_adders)
      .filter(([k]) => !["three_phase", "double_storey"].includes(k)) // set automatically from phase/storeys
      .forEach(([k, label]) => {
        const l = document.createElement("label");
        l.className = "check";
        l.innerHTML = `<input type="checkbox" name="${escape(k)}" data-adder="1"> ${escape(label)}`;
        adders.append(l);
      });

    form.addEventListener("input", scheduleRefresh);
    form.addEventListener("change", scheduleRefresh);
    document.getElementById("load-example").addEventListener("click", () => writeForm(EXAMPLE));
    document.getElementById("reset").addEventListener("click", () => {
      localStorage.removeItem(STORAGE_KEY);
      writeForm({});
    });

    const saved = localStorage.getItem(STORAGE_KEY);
    writeForm(saved ? JSON.parse(saved) : {});
  }

  init().catch((err) => {
    document.getElementById("config-banner").textContent = `Could not load config: ${err.message}`;
  });
})();
