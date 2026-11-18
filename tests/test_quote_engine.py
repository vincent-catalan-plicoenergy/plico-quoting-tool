import pytest

from app import create_app, load_config
from app.quote_engine import (
    QuoteError,
    amortised_payment,
    battery_stcs,
    build_quote,
    finance_plan,
    pv_stcs,
)

CFG = load_config()

PARMELIA = {
    "customer_name": "Parmelia example",
    "postcode": "6167",
    "residential_status": "owner",
    "objective": "lower_bills",
    "quarterly_bill": 300,
    "has_existing_solar": True,
    "existing_panel_count": 5,
    "phase": "single",
    "roof_type": "tile",
    "storeys": "1",
    "solution_type": "full_system",
    "package": "energy_creator_10",
    "payment_type": "plico_finance",
    "plico_finance_term_months": 60,
}


def test_pv_stcs_rounds_down():
    # 6.6 * 1.382 * 5 = 45.6 -> 45
    assert pv_stcs(6.6, CFG) == 45


def test_battery_stcs_tiers():
    # 10.1 kWh fully in first tier: 10.1 * 6.8 = 68.68 -> 68
    assert battery_stcs(10.1, CFG) == 68
    # 20 kWh: 14 + 6*0.6 = 17.6 weighted -> 119.68 -> 119
    assert battery_stcs(20, CFG) == 119


def test_package_resolves_energy_creator_10():
    q = build_quote(PARMELIA, CFG)
    assert q["system"]["pv_kw"] == 6.6
    assert q["system"]["battery_kwh"] == 10.1
    assert q["system"]["new_inverter"] is True


def test_existing_solar_removal_added_when_not_retained():
    labels = [l["label"] for l in build_quote(PARMELIA, CFG)["cost"]["lines"]]
    assert "Existing solar removal" in labels
    labels = [l["label"] for l in build_quote({**PARMELIA, "retain_existing_solar": True}, CFG)["cost"]["lines"]]
    assert "Existing solar removal" not in labels


def test_revenue_is_price_plus_incentives():
    p = build_quote(PARMELIA, CFG)["pricing"]
    incentives = sum(i["amount"] for i in p["incentives"])
    assert p["revenue"] == pytest.approx(p["customer_price"] + incentives, abs=0.01)


def test_wa_rebate_needs_eligibility_and_vpp():
    def rebate(**kw):
        items = build_quote({**PARMELIA, **kw}, CFG)["pricing"]["incentives"]
        return sum(i["amount"] for i in items if i["label"] == "WA battery rebate")

    assert rebate() == 0
    assert rebate(wa_rebate_eligible=True) == 0  # VPP required
    assert rebate(wa_rebate_eligible=True, join_vpp=True) == 1300  # 10.1*130 capped at 1300


def test_battery_only_has_no_solar_or_new_inverter():
    q = build_quote({**PARMELIA, "solution_type": "battery_only"}, CFG)
    assert q["system"]["pv_kw"] == 0
    assert q["system"]["new_inverter"] is False


def test_interest_free_loan_excluded_from_plico_finance():
    f = finance_plan(20000, {"payment_type": "combination", "interest_free_loan_amount": 10000,
                             "deposit": 1000}, CFG)
    assert f["interest_free_loan_amount"] == 10000
    assert f["plico_finance_amount"] == 9000
    assert f["plico_finance_buyout"] == 9000
    assert f["cash_balance"] == 0


def test_interest_free_loan_capped():
    f = finance_plan(30000, {"payment_type": "interest_free_loan", "interest_free_loan_amount": 50000}, CFG)
    assert f["interest_free_loan_amount"] == CFG["finance"]["interest_free_loan_max"]
    assert f["cash_balance"] == 20000


def test_amortised_payment():
    assert amortised_payment(12000, 0, 12) == 1000
    assert amortised_payment(10000, 12, 12) == pytest.approx(888.49, abs=0.01)


def test_readiness_levels():
    r = build_quote(PARMELIA, CFG)["readiness"]
    assert r["level"] == "indicative"
    assert "Electricity bill (front + back)" in r["missing"]["customer"]

    complete = {**PARMELIA, "bill_uploaded": True, "panel_location": "north",
                "existing_solar_kw": 1.0, "existing_system_age_years": 15,
                "existing_inverter_model": "SMA SB1200"}
    assert build_quote(complete, CFG)["readiness"]["level"] == "estimated"
    checks = {k: True for k in ("switchboard_checked", "shading_checked", "orientation_checked",
                                "internet_available", "site_photos")}
    assert build_quote({**complete, **checks}, CFG)["readiness"]["level"] == "firm_ready"


def test_savings_from_bill():
    sv = build_quote(PARMELIA, CFG)["savings"]
    assert 0 < sv["daily_usage_kwh"] < 15
    assert sv["annual_bill_now"] == 1200
    assert 0 < sv["annual_savings"] <= 1200


@pytest.mark.parametrize("bad", [
    {"solution_type": "nope"},
    {"package": "nope"},
    {"package": "custom", "pv_kw": 0, "battery_kwh": 0},
    {"payment_type": "barter"},
    {"site_adders": ["nope"]},
    {"quarterly_bill": "abc"},
])
def test_invalid_input_raises(bad):
    with pytest.raises(QuoteError):
        build_quote({**PARMELIA, **bad}, CFG)


# ---------------------------------------------------------------- API ---
@pytest.fixture()
def client():
    return create_app().test_client()


def test_api_health(client):
    assert client.get("/api/health").json["status"] == "ok"


def test_api_config(client):
    body = client.get("/api/config").json
    assert "energy_creator_10" in body["packages"]
    assert "unit_costs" not in body  # internal costs stay server-side


def test_api_quote(client):
    res = client.post("/api/quote", json=PARMELIA)
    assert res.status_code == 200
    assert res.json["pricing"]["customer_price"] > 0


def test_api_quote_errors(client):
    assert client.post("/api/quote", data="x", content_type="text/plain").status_code == 400
    assert client.post("/api/quote", json={"solution_type": "nope"}).status_code == 422


def test_index_page(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Plico Quoting Tool" in res.data
