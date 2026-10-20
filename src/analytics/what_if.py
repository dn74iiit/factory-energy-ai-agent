"""
What-If Scenario Modeling Engine.
Computes deterministic simulations for management scenarios:
- What if the tariff had remained at baseline rates?
- What if the compressor leak is repaired?
- What if product mix changes?
"""

from typing import Dict, Any
from src.database import db
from src.analytics.decomposition import decomposition_engine
from src.config import EMISSION_FACTOR_KG_PER_KWH

class WhatIfSimulator:
    def simulate_tariff_reversion(self, period: str = "2026-Q3") -> Dict[str, Any]:
        """Simulates factory bill if tariff change had not occurred."""
        decomp = decomposition_engine.decompose(period=period)
        bill_current = decomp["bill_current"]
        bill_base_tariff = bill_current - (decomp["bill_baseline"] * decomp["bridge"][0]["pct_points"] / 100.0)
        money_saved = bill_current - bill_base_tariff
        pct_savings = (money_saved / bill_current) * 100.0
        
        return {
            "scenario": "Revert to baseline tariff schedule",
            "current_bill": round(bill_current, 2),
            "simulated_bill": round(bill_base_tariff, 2),
            "money_saved": round(money_saved, 2),
            "pct_reduction": round(pct_savings, 2)
        }

    def simulate_leak_repair(self, period: str = "2026-Q3") -> Dict[str, Any]:
        """Simulates savings if compressor leak on Line 3 is repaired."""
        decomp = decomposition_engine.decompose(period=period)
        kwh_current = decomp["kwh_current"]
        # Leak is ~26 kW running 24/7 for ~77 days in Q3 = ~48,000 kWh
        kwh_wasted_q3 = 48000.0
        simulated_kwh = kwh_current - kwh_wasted_q3
        simulated_cost_savings = kwh_wasted_q3 * 0.11
        simulated_co2e_savings = (kwh_wasted_q3 * EMISSION_FACTOR_KG_PER_KWH) / 1000.0
        
        return {
            "scenario": "Repair Line 3 compressor air leak immediately",
            "kwh_saved_quarter": round(kwh_wasted_q3, 1),
            "money_saved_quarter": round(simulated_cost_savings, 2),
            "co2e_saved_tonnes_quarter": round(simulated_co2e_savings, 2),
            "pct_bill_reduction": round((simulated_cost_savings / decomp["bill_current"]) * 100.0, 2)
        }

    def simulate_custom(self, period: str = "2026-Q3", tariff_delta_pct: float = 0.0, 
                        volume_delta_pct: float = 0.0, repair_leak: bool = False) -> Dict[str, Any]:
        """Simulates custom management parameters dynamically."""
        decomp = decomposition_engine.decompose(period=period)
        b0 = decomp["bill_baseline"]
        b1 = decomp["bill_current"]
        
        t_pts = decomp["bridge"][0]["pct_points"]
        current_tariff_cost = b0 * (t_pts / 100.0)
        sim_tariff_cost = current_tariff_cost * (1.0 + (tariff_delta_pct / 100.0))
        delta_tariff_dollars = sim_tariff_cost - current_tariff_cost

        v_pts = decomp["bridge"][2]["pct_points"]
        current_vol_cost = b0 * (v_pts / 100.0)
        sim_vol_cost = current_vol_cost * (1.0 + (volume_delta_pct / 100.0))
        delta_vol_dollars = sim_vol_cost - current_vol_cost

        leak_kwh = 48000.0 if repair_leak else 0.0
        leak_dollars = leak_kwh * 0.11
        leak_co2e = (leak_kwh * EMISSION_FACTOR_KG_PER_KWH) / 1000.0

        simulated_bill = max(0.0, b1 + delta_tariff_dollars + delta_vol_dollars - leak_dollars)
        net_savings = b1 - simulated_bill
        net_pct = (net_savings / b1) * 100.0 if b1 > 0 else 0.0

        return {
            "period": period,
            "baseline_bill": round(b0, 2),
            "current_bill": round(b1, 2),
            "simulated_bill": round(simulated_bill, 2),
            "net_difference_dollars": round(net_savings, 2),
            "net_difference_pct": round(net_pct, 2),
            "leak_repaired": repair_leak,
            "co2e_saved_tonnes": round(leak_co2e, 2),
            "tariff_delta_pct": tariff_delta_pct,
            "volume_delta_pct": volume_delta_pct
        }

what_if_simulator = WhatIfSimulator()
