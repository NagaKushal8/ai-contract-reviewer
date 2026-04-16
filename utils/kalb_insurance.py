"""
utils/kalb_insurance.py

Kalb Construction insurance coverage constants.

Hardcodes the coverage limits and policy details from Kalb Construction's
Certificate of Insurance. These values are used by Phase 2 AI agents to
compare contract insurance requirements against Kalb's actual coverage
and flag gaps or exposures.

Policy period: 2026-04-01 → 2027-04-01
"""

KALB_COI: dict = {

    # ------------------------------------------------------------------
    # Commercial General Liability
    # Occurrence-based policy; aggregate applies per project (not per policy)
    # ------------------------------------------------------------------
    "commercial_general_liability": {
        "each_occurrence":                   1_000_000,
        "general_aggregate":                 2_000_000,
        "products_completed_ops_aggregate":  2_000_000,
        "personal_advertising_injury":       1_000_000,
        "damage_to_rented_premises":           300_000,
        "med_exp":                              15_000,
        "policy_type":                       "occurrence",
        "aggregate_applies_per":             "project",
        "additional_insured":                True,
        "subrogation_waived":                True,
    },

    # ------------------------------------------------------------------
    # Automobile Liability
    # Covers any auto (owned, hired, non-owned)
    # ------------------------------------------------------------------
    "automobile_liability": {
        "combined_single_limit":  1_000_000,
        "covers_any_auto":        True,
        "additional_insured":     True,
        "subrogation_waived":     True,
    },

    # ------------------------------------------------------------------
    # Umbrella / Excess Liability
    # Sits over CGL and Auto; occurrence-based
    # Combined with CGL = $6M per occurrence for bodily injury / property damage
    # ------------------------------------------------------------------
    "umbrella_excess_liability": {
        "each_occurrence":    5_000_000,
        "aggregate":          5_000_000,
        "policy_type":        "occurrence",
        "retention":             10_000,
        "additional_insured":      True,
        "subrogation_waived":      True,
    },

    # ------------------------------------------------------------------
    # Workers' Compensation & Employers' Liability
    # Per statute (Nevada); subrogation waived
    # ------------------------------------------------------------------
    "workers_compensation": {
        "per_statute":               True,
        "el_each_accident":       1_000_000,
        "el_disease_ea_employee": 1_000_000,
        "el_disease_policy_limit":1_000_000,
        "subrogation_waived":         True,
    },

    # ------------------------------------------------------------------
    # Professional / Pollution Liability
    # Claims-made basis (not occurrence)
    # ------------------------------------------------------------------
    "professional_pollution_liability": {
        "limit":     1_000_000,
        "aggregate": 2_000_000,
    },

    # ------------------------------------------------------------------
    # Leased / Rented Equipment
    # ------------------------------------------------------------------
    "leased_rented_equipment": {
        "limit":      100_000,
        "deductible":   1_000,
    },

    # ------------------------------------------------------------------
    # Cyber Liability
    # ------------------------------------------------------------------
    "cyber_liability": {
        "limit": 1_000_000,
    },

    # ------------------------------------------------------------------
    # Policy period
    # ------------------------------------------------------------------
    "policy_effective": "2026-04-01",
    "policy_expiry":    "2027-04-01",

    # ------------------------------------------------------------------
    # Effective combined limit (CGL + Umbrella) per occurrence
    # ------------------------------------------------------------------
    "total_effective_liability": 6_000_000,

    # ------------------------------------------------------------------
    # Human-readable notes for AI agent context
    # ------------------------------------------------------------------
    "notes": [
        "CGL aggregate applies per project not per policy",
        "Umbrella sits over CGL and Auto",
        "Total CGL plus Umbrella equals 6M per occurrence",
        "All policies on occurrence basis except professional liability",
        "Additional insured confirmed on CGL Auto and Umbrella",
        "Waiver of subrogation confirmed on all major policies",
    ],
}
