"""Plico quote engine.

Pure functions: takes a quote request (dict) and a pricing config (dict)
and returns an estimated proposal (dict). No I/O here, so it is easy to test.
"""
from __future__ import annotations

import math
from typing import Any

SOLUTION_TYPES = {
    "full_system": "Full System (solar + battery)",
    "battery_only": "Battery Only",
    "battery_hybrid_replacement": "Battery + Hybrid Inverter Replacement",
    "expansion": "Expansion of existing system",
}

PAYMENT_TYPES = {"cash", "plico_finance", "interest_free_loan", "combination"}

# Inputs Plico needs before a proposal counts as "estimated" rather than a rough guess.
CUSTOMER_FIELDS = {
    "bill_uploaded": "Electricity bill (front + back)",
    "postcode": "Property postcode",
    "residential_status": "Residential status (owner / renter)",
    "objective": "Customer objective",
    "payment_type": "Payment preference",
}
TECHNICAL_FIELDS = {
    "phase": "Single or three phase",
    "roof_type": "Roof type (tile / tin)",
    "storeys": "Single or double storey",
    "panel_location": "Intended panel location",
}
EXISTING_SOLAR_FIELDS = {
    "existing_solar_kw": "Existing solar size (kW)",
    "existing_panel_count": "Existing panel count",
    "existing_system_age_years": "Existing system age",
    "existing_inverter_model": "Existing inverter brand/model",
}
SITE_CHECKS = [
    "switchboard_checked",
    "shading_checked",
    "orientation_checked",
    "internet_available",
    "site_photos",
]


class QuoteError(ValueError):
    """Raised when a request cannot be priced."""


def _num(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise QuoteError(f"Expected a number, got {value!r}") from exc


def _money(value: float) -> float:
    return round(value + 1e-9, 2)


# ---------------------------------------------------------------- system ---
def resolve_system(req: dict, cfg: dict) -> dict:
    solution = req.get("solution_type", "full_system")
    if solution not in SOLUTION_TYPES:
        raise QuoteError(f"Unknown solution_type: {solution}")

    package_key = req.get("package") or "custom"
    if package_key != "custom":
        pkg = cfg["packages"].get(package_key)
        if pkg is None:
            raise QuoteError(f"Unknown package: {package_key}")
        pv_kw, battery_kwh = pkg["pv_kw"], pkg["battery_kwh"]
        inverter_kw, label = pkg["inverter_kw"], pkg["label"]
        inverter_model, battery_model = pkg["inverter_model"], pkg["battery_model"]
    else:
        pv_kw = _num(req.get("pv_kw"))
        battery_kwh = _num(req.get("battery_kwh"))
        inverter_kw = _num(req.get("inverter_kw"))
        label = "Custom system"
        inverter_model = req.get("inverter_model") or "TBC"
        battery_model = req.get("battery_model") or "TBC"

    if solution == "battery_only":
        pv_kw, inverter_kw, inverter_model = 0.0, 0.0, "Existing inverter retained"
    new_inverter = solution in ("full_system", "battery_hybrid_replacement") or (
        solution == "expansion" and inverter_kw > 0
    )
    if solution == "battery_hybrid_replacement":
        pv_kw = 0.0

    if pv_kw < 0 or battery_kwh < 0:
        raise QuoteError("System sizes cannot be negative")
    if pv_kw == 0 and battery_kwh == 0:
        raise QuoteError("System has no solar and no battery")

    return {
        "solution_type": solution,
        "solution_label": SOLUTION_TYPES[solution],
        "package": package_key,
        "package_label": label,
        "pv_kw": pv_kw,
        "battery_kwh": battery_kwh,
        "inverter_kw": inverter_kw if new_inverter else 0.0,
        "inverter_model": inverter_model if new_inverter else "Existing inverter retained",
        "battery_model": battery_model if battery_kwh else "None",
        "new_inverter": new_inverter,
        "retain_existing_solar": bool(req.get("retain_existing_solar")),
    }


# ------------------------------------------------------------------ cost ---
def system_cost(system: dict, req: dict, cfg: dict) -> dict:
    uc = cfg["unit_costs"]
    lines = []

    def add(label: str, amount: float) -> None:
        if amount:
            lines.append({"label": label, "amount": _money(amount)})

    add(f"Solar panels {system['pv_kw']} kW", system["pv_kw"] * uc["pv_per_kw"])
    if system["new_inverter"]:
        add("Hybrid inverter", uc["hybrid_inverter"])
    add(f"Battery {system['battery_kwh']} kWh", system["battery_kwh"] * uc["battery_per_kwh"])
    add("Installation (base)", uc["install_base"])
    add("Installation (solar)", system["pv_kw"] * uc["install_pv_per_kw"])
    if system["battery_kwh"]:
        add("Installation (battery)", uc["install_battery"])

    has_existing = _num(req.get("existing_solar_kw")) > 0 or _num(req.get("existing_panel_count")) > 0
    if has_existing and not system["retain_existing_solar"] and system["solution_type"] == "full_system":
        add("Existing solar removal", uc["existing_solar_removal"])

    adders = set(req.get("site_adders") or [])
    if req.get("phase") == "three":
        adders.add("three_phase")
    if str(req.get("storeys")) == "2":
        adders.add("double_storey")
    for key in sorted(adders):
        adder = cfg["site_adders"].get(key)
        if adder is None:
            raise QuoteError(f"Unknown site adder: {key}")
        add(adder["label"], adder["cost"])

    return {"lines": lines, "total": _money(sum(l["amount"] for l in lines))}


# --------------------------------------------------------------- rebates ---
def pv_stcs(pv_kw: float, cfg: dict) -> int:
    s = cfg["stc"]
    return math.floor(pv_kw * s["pv_zone_rating"] * s["pv_deeming_years"])


def battery_stcs(battery_kwh: float, cfg: dict) -> int:
    s = cfg["stc"]
    remaining, lower, weighted = battery_kwh, 0.0, 0.0
    for tier in s["battery_tiers"]:
        band = max(0.0, min(remaining, tier["up_to_kwh"] - lower))
        weighted += band * tier["pct"] / 100
        remaining -= band
        lower = tier["up_to_kwh"]
    return math.floor(weighted * s["battery_factor_per_kwh"])


def wa_rebate(battery_kwh: float, req: dict, cfg: dict) -> float:
    r = cfg["wa_rebate"]
    if not battery_kwh or not req.get("wa_rebate_eligible"):
        return 0.0
    if r.get("requires_vpp") and not req.get("join_vpp"):
        return 0.0
    return float(min(battery_kwh * r["per_kwh"], r["cap"]))


# --------------------------------------------------------------- finance ---
def amortised_payment(principal: float, annual_rate_pct: float, months: int) -> float:
    if principal <= 0 or months <= 0:
        return 0.0
    r = annual_rate_pct / 100 / 12
    if r == 0:
        return principal / months
    return principal * r / (1 - (1 + r) ** -months)


def finance_plan(customer_price: float, req: dict, cfg: dict) -> dict:
    f = cfg["finance"]
    payment = req.get("payment_type", "cash")
    if payment not in PAYMENT_TYPES:
        raise QuoteError(f"Unknown payment_type: {payment}")

    deposit = min(_num(req.get("deposit")), customer_price)
    ifl = 0.0
    if payment in ("interest_free_loan", "combination"):
        ifl = min(_num(req.get("interest_free_loan_amount"), f["interest_free_loan_max"]),
                  f["interest_free_loan_max"], customer_price - deposit)
    # The interest-free loan is excluded from the Plico Finance amount (and buyout).
    plico = 0.0
    if payment in ("plico_finance", "combination"):
        plico = customer_price - deposit - ifl
    cash_balance = customer_price - deposit - ifl - plico

    plico_term = int(_num(req.get("plico_finance_term_months"), 60))
    ifl_term = int(_num(req.get("interest_free_loan_term_months"), 120))
    plico_monthly = amortised_payment(plico, f["plico_finance_rate_pct"], plico_term)
    ifl_monthly = ifl / ifl_term if ifl else 0.0

    return {
        "payment_type": payment,
        "deposit": _money(deposit),
        "cash_balance": _money(max(cash_balance, 0.0)),
        "interest_free_loan_amount": _money(ifl),
        "interest_free_loan_term_months": ifl_term if ifl else None,
        "interest_free_loan_monthly": _money(ifl_monthly),
        "plico_finance_amount": _money(plico),
        "plico_finance_buyout": _money(plico),
        "plico_finance_rate_pct": f["plico_finance_rate_pct"] if plico else None,
        "plico_finance_term_months": plico_term if plico else None,
        "plico_finance_monthly": _money(plico_monthly),
        "total_monthly": _money(plico_monthly + ifl_monthly),
    }


# --------------------------------------------------------------- savings ---
def estimate_savings(system: dict, req: dict, cfg: dict) -> dict:
    s = cfg["savings"]
    tariff = _num(req.get("tariff_per_kwh"), s["tariff_per_kwh"])
    supply = _num(req.get("supply_charge_per_day"), s["supply_charge_per_day"])
    fit = _num(req.get("feed_in_per_kwh"), s["feed_in_per_kwh"])

    daily_usage = _num(req.get("daily_usage_kwh"))
    quarterly_bill = _num(req.get("quarterly_bill"))
    if not daily_usage and quarterly_bill:
        daily_usage = max((quarterly_bill / 91.25 - supply) / tariff, 0.0)
    annual_usage = daily_usage * 365
    annual_bill = quarterly_bill * 4 if quarterly_bill else annual_usage * tariff + supply * 365

    pv_kw = system["pv_kw"]
    if system["retain_existing_solar"] or system["solution_type"] in ("battery_only", "battery_hybrid_replacement"):
        pv_kw += _num(req.get("existing_solar_kw"))
    generation = pv_kw * s["pv_yield_kwh_per_kw_day"] * 365
    ratio = s["self_consumption_with_battery"] if system["battery_kwh"] else s["self_consumption_pv_only"]
    self_used = min(generation * ratio, annual_usage)
    exported = max(generation - self_used, 0.0)
    savings = min(self_used * tariff + exported * fit, max(annual_bill - supply * 365, 0) + exported * fit)

    return {
        "daily_usage_kwh": round(daily_usage, 1),
        "annual_usage_kwh": round(annual_usage),
        "annual_bill_now": _money(annual_bill),
        "annual_generation_kwh": round(generation),
        "annual_self_consumed_kwh": round(self_used),
        "annual_exported_kwh": round(exported),
        "annual_savings": _money(savings),
        "quarterly_savings": _money(savings / 4),
        "assumptions": {"tariff_per_kwh": tariff, "supply_charge_per_day": supply, "feed_in_per_kwh": fit},
    }


# ------------------------------------------------------------- readiness ---
def readiness(req: dict, system: dict) -> dict:
    def missing(fields: dict) -> list[str]:
        return [label for key, label in fields.items() if req.get(key) in (None, "", False)]

    missing_customer = missing(CUSTOMER_FIELDS)
    missing_technical = missing(TECHNICAL_FIELDS) if system["pv_kw"] else missing(
        {k: v for k, v in TECHNICAL_FIELDS.items() if k == "phase"})
    missing_existing = missing(EXISTING_SOLAR_FIELDS) if req.get("has_existing_solar") else []
    if req.get("has_existing_battery") and not req.get("existing_battery_model"):
        missing_existing.append("Existing battery brand/model/capacity")
    if not req.get("quarterly_bill") and not req.get("daily_usage_kwh"):
        missing_customer.append("Bill amount or daily usage")
    site_done = sum(1 for k in SITE_CHECKS if req.get(k))

    if missing_customer or missing_technical or missing_existing:
        level, label = "indicative", "Indicative only - key inputs missing"
    elif site_done < len(SITE_CHECKS):
        level, label = "estimated", "Estimated proposal - site checks outstanding"
    else:
        level, label = "firm_ready", "Ready for firm quote"

    warnings = []
    if req.get("residential_status") == "renter":
        warnings.append("Customer is renting: owner consent required.")
    if req.get("has_existing_solar") and _num(req.get("existing_system_age_years")) >= 10:
        warnings.append("Existing system is 10+ years old: check compliance before retaining.")
    if system["retain_existing_solar"]:
        warnings.append("Retained equipment can affect installation, approvals and compliance.")
    if req.get("phase") == "three":
        warnings.append("Three-phase site: confirm inverter and export limits.")

    return {
        "level": level,
        "label": label,
        "missing": {
            "customer": missing_customer,
            "technical": missing_technical,
            "existing_system": missing_existing,
        },
        "site_checks_complete": site_done,
        "site_checks_total": len(SITE_CHECKS),
        "warnings": warnings,
    }


# ------------------------------------------------------------------ main ---
def build_quote(req: dict, cfg: dict) -> dict:
    system = resolve_system(req, cfg)
    cost = system_cost(system, req, cfg)

    markup = _num(req.get("markup_pct"), cfg["margin"]["default_markup_pct"])
    gross_price = _num(req.get("price_override")) or cost["total"] * (1 + markup / 100)

    stc_price = cfg["stc"]["price_per_stc"]
    n_pv, n_bat = pv_stcs(system["pv_kw"], cfg), battery_stcs(system["battery_kwh"], cfg)
    incentives = [
        {"label": f"Solar STCs ({n_pv} x ${stc_price:.2f})", "amount": _money(n_pv * stc_price)},
        {"label": f"Battery STCs ({n_bat} x ${stc_price:.2f})", "amount": _money(n_bat * stc_price)},
        {"label": "WA battery rebate", "amount": _money(wa_rebate(system["battery_kwh"], req, cfg))},
    ]
    discounts = [
        {"label": "VPP discount", "amount": _money(_num(req.get("vpp_discount"), cfg["vpp_discount"]) if req.get("join_vpp") else 0)},
        {"label": "Promotion / campaign", "amount": _money(_num(req.get("promo_discount")))},
    ]
    incentives = [i for i in incentives if i["amount"]]
    discounts = [d for d in discounts if d["amount"]]
    incentive_total = sum(i["amount"] for i in incentives)
    discount_total = sum(d["amount"] for d in discounts)

    customer_price = max(gross_price - incentive_total - discount_total, 0.0)
    revenue = customer_price + incentive_total
    gross_profit = revenue - cost["total"]

    savings = estimate_savings(system, req, cfg)
    finance = finance_plan(customer_price, req, cfg)
    payback = customer_price / savings["annual_savings"] if savings["annual_savings"] else None

    return {
        "customer": {k: req.get(k) for k in ("customer_name", "address", "postcode", "objective", "residential_status")},
        "system": system,
        "cost": cost,
        "pricing": {
            "markup_pct": markup,
            "gross_price": _money(gross_price),
            "incentives": incentives,
            "discounts": discounts,
            "customer_price": _money(customer_price),
            "revenue": _money(revenue),
            "gross_profit": _money(gross_profit),
            "gross_margin_pct": round(gross_profit / revenue * 100, 1) if revenue else 0.0,
            "stcs": {"pv": n_pv, "battery": n_bat},
        },
        "finance": finance,
        "savings": savings,
        "payback_years": round(payback, 1) if payback else None,
        "readiness": readiness(req, system),
        "config_version": cfg.get("version"),
    }
