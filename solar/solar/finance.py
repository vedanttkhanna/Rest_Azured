from __future__ import annotations
import math


def calculate_finance(kw, annual_kwh, config):
    if not all(math.isfinite(x) and x>=0 for x in (kw,annual_kwh)):
        raise ValueError("Capacity and generation must be finite and nonnegative")
    c = config["finance"]
    capex = kw*c["capex_inr_per_kw"]
    subsidy = 0.0
    if c["subsidy_eligible"]:
        subsidy = min(kw,c["subsidy_first_kw"])*c["subsidy_first_rate"]
        subsidy += min(max(0,kw-c["subsidy_first_kw"]),c["subsidy_next_kw"])*c["subsidy_next_rate"]
        subsidy = min(subsidy,c["subsidy_cap_inr"],capex)
    net = capex-subsidy
    savings = annual_kwh*c["tariff_inr_per_kwh"]
    lifetime = sum(savings*(1-c["degradation_per_year"])**y for y in range(int(c["lifetime_years"])))
    return {"capex_inr": round(capex,2), "subsidy_inr": round(subsidy,2),
            "net_cost_inr": round(net,2), "annual_savings_inr": round(savings,2),
            "payback_years": round(net/savings,2) if savings>0 else None,
            "lifetime_savings_inr": round(lifetime-net,2)}, round(annual_kwh/1000*c["grid_co2_t_per_mwh"],3)
