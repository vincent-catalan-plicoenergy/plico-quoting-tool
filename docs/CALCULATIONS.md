# How the quote is calculated

All logic is in `app/quote_engine.py`; all numbers come from `config/pricing.json`.

## 1. System
- **Package** (`energy_creator_10`: 6.6 kW PV + 10.1 kWh; `energy_creator_10_plus`: 7.92 kW PV + 10.1 kWh) or **custom** sizes.
- **Battery Only** → no new PV, existing inverter retained.
- **Battery + Hybrid Inverter Replacement** → no new PV, new hybrid inverter.
- **Full System** → new PV, inverter and battery. Existing solar is removed (cost added) unless *Retain existing solar* is ticked.

## 2. System cost (internal)
`PV kW × pv_per_kW + inverter + battery kWh × battery_per_kWh + install base + install per PV kW + battery install + removal + site adders`

Three-phase and double-storey adders are added automatically from the Site section.

## 3. Price
- `gross_price = price_override` if set, otherwise `system_cost × (1 + markup%)`
- `Solar STCs = floor(PV kW × zone rating × deeming years)`
- `Battery STCs = floor(weighted kWh × battery factor)`, where kWh is weighted by the tiers in `stc.battery_tiers`
- `WA rebate = min(kWh × per_kWh, cap)`, only if eligible (and in a VPP when `requires_vpp`)
- `customer_price = gross_price − STCs − WA rebate − VPP discount − promotion`
- `revenue = customer_price + STCs + WA rebate`
- `gross_profit = revenue − system_cost`

## 4. Finance
- Deposit comes off first.
- Interest-free loan = min(requested, `interest_free_loan_max`, remaining balance), repaid evenly over its term.
- **Plico Finance amount = customer price − deposit − interest-free loan.** The loan is excluded from the financed amount and the buyout.
- Plico Finance repayment is a standard amortised monthly payment.

## 5. Savings
- Daily usage = from the bill if entered, else `(quarterly bill ÷ 91.25 − supply charge) ÷ tariff`.
- Generation = PV kW × yield × 365 (includes existing PV when it is retained or the job is battery-only).
- Self-consumed = generation × self-consumption ratio (higher with a battery), capped at usage.
- Savings = self-consumed × tariff + exported × feed-in.
- Payback = customer price ÷ annual savings.

## 6. Readiness
| Level | Rule |
|---|---|
| Indicative | Any customer, technical or existing-system input missing |
| Estimated | All inputs present, some pre-install site checks outstanding |
| Ready for firm quote | All inputs and site checks complete |

## Values to verify before use
STC price, zone rating, deeming years, battery STC factor and tiers, WA rebate amount/cap/VPP rule, interest-free loan limit and terms, Plico Finance rate, Synergy tariff, supply charge and feed-in rate.
