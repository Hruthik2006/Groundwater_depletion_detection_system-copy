# Global Water Stress & Scarcity Index (1990-Present)
Per-country annual panel tracking freshwater withdrawal, water stress, renewable resources, and access.
Updated: 2026-04-23

## Sources
- **World Bank Open Data API (WDI + AQUASTAT)** - https://data.worldbank.org
  Free REST API, no key required. Water withdrawal and resource data sourced from FAO AQUASTAT via WDI.

## Files

| File | Description |
|------|-------------|
| freshwater_withdrawal.csv | Total withdrawal (billion m³) + sector shares by country & year |
| water_resources.csv | Renewable freshwater per capita, total renewable, population, GDP |
| water_access.csv | Drinking water access (basic, safely managed, rural, urban), irrigated land |
| water_stress_panel.csv | Full merged panel + derived stress & scarcity metrics |

## Key Columns

| Column | Description |
|--------|-------------|
| withdrawal_bcm | Annual freshwater withdrawal, total (billion cubic metres) |
| water_stress_pct | Withdrawal as % of renewable internal resources (= stress score) |
| agri_withdrawal_pct | Agriculture share of total withdrawal (%) |
| freshwater_per_capita_m3 | Renewable internal freshwater per capita (m³/person/year) |
| basic_water_access_pct | Population using at least basic drinking water (%) |
| safely_managed_water_pct | Population using safely managed drinking water (%) |
| urban_rural_access_gap_pp | Urban minus rural basic water access (percentage points) |
| falkenmark_category | no_stress / stress / scarcity / absolute_scarcity |
| stress_category | low / low_medium / medium_high / high |
| scarcity_risk_flag | 1 if high stress OR absolute scarcity, else 0 |
| agri_withdrawal_intensity_pct | Agriculture's share of total renewable freshwater consumed (%) |
| stress_5yr_trend_pp | 5-year trend in water stress score (pp/year — rising = worsening) |

## Falkenmark Scarcity Classification
| Category | Freshwater per Capita | Meaning |
|----------|-----------------------|---------|
| no_stress | ≥ 1700 m³/person/year | Adequate freshwater |
| stress | 1000–1699 m³/person/year | Periodic or regular water stress |
| scarcity | 500–999 m³/person/year | Chronic water scarcity |
| absolute_scarcity | < 500 m³/person/year | Severe constraint on human/economic development |

## Withdrawal Stress Classification (UN/FAO thresholds)
| Category | Withdrawal / Renewable | Meaning |
|----------|------------------------|---------|
| low | < 10% | Low pressure on water resources |
| low_medium | 10–20% | Moderate pressure |
| medium_high | 20–40% | Significant pressure, risk of shortages |
| high | ≥ 40% | Critical water stress |

## License
World Bank Open Data is CC BY 4.0. FAO AQUASTAT data is CC BY-NC-SA 3.0 IGO.
Compiled dataset: CC0 - Public Domain.