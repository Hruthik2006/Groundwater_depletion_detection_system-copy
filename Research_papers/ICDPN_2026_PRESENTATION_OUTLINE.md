# ICDPN-2026 Conference Presentation — Full Outline (Start → End)

**Paper:** AI-Driven Groundwater Depletion Prediction and Sustainable Extraction Optimization System
**Authors:** Sandhya N, Anoop S Sonagoji, Driti S, Hruthik C P, Tejashwini M Bevingidad
**Affiliation:** Dept. of AIML, Dayananda Sagar Academy of Technology and Management, Bangalore, India
**Event:** International Conference on Data Processing and Networking (ICDPN-2026), 25th–26th September 2026
**Deck:** `ICDPN_2026_PPT_Template-GroundWater.pptx` (13 in × 8 in, 12 slides)
**Submitted paper:** `ground_water_springer format.pdf` (12 pages, Springer single-column IEEE-style)

---

## 0. Pre-presentation checklist (do tonight)

- [ ] Delete the leftover `NNNNNN  RESULTS TABLE  JJJJJ` text box on **slide 8** (Results).
- [ ] Rename slide 12 header `10. REFERENCES (CONTD.)` → `10. References (Contd.)` (index lists `10. References`).
- [ ] Verify laptop: Python 3.10+, `pip list` includes `torch`, `fastapi`, `uvicorn`, `cvxpy`, `pytest`.
- [ ] Smoke-test once fully offline: `python main.py synthetic` boots and reaches `http://localhost:8000`.
- [ ] Run `python -m pytest tests -q` → confirm **18 passed** before the session.
- [ ] Have `D:\Ground_water\.env` keys ready **if** you plan a `realtime` demo (else stay on `synthetic`).
- [ ] Open dashboard once, save 1–2 screenshots from `insp/` as a fallback if the live demo fails.
- [ ] Print this outline + the one-page demo script as your speaker notes.
- [ ] Archify diagrams re-verified at current HEAD (24-Sep-2026):
      `01-architecture`, `02-dataflow`, `03-workflow` all pass validate (0 errors/warnings)
      and visual-check (0 diagnostics after compactifying `03-workflow` — viewBox 1230×652).
      `03-workflow.html` was re-delivered; `01`/`02` unchanged. Use them as backup slides.

---

## 1. Opening (0:30) — before slide 1

Greet panel, state your name on your turn, introduce the 5-person team and the paper title.
> "Good morning/afternoon, respected judges and panel. We present our work titled *AI-Driven Groundwater Depletion Prediction and Sustainable Extraction Optimization System*."

**Trigger slide 1 — Title (0:30)**
- Team, department, college, conference banner.
- No content discussion — move straight to index.

---

## 2. Index / Roadmap (slide 2) — 0:15

Read the ten section numbers quietly (Abstract → References). Do not dwell.
> 10 sections, ~10 minutes, ends with a short live demo.

---

## 3. Abstract (slide 3) — 1:00

**Key message (memorize):**
RMSE **2.663 m**, error reduction **84.7%**, constraint violation rate **CVR 0.0%**.

**Speak the 4-part abstract arc:**
1. Problem: groundwater depletion vs 3 obstacles — scale mismatch, vadose-zone delays, non-convex extraction control.
2. Method: **SciML + robust control** — 4-step mass-balance downscaling of GRACE → Gamma-kernel vadose delay → **three surrogates (GNN-LSTM, 2D Dupuit–Boussinesq PINN, 2D FNO)** → **Split Conformal Prediction** safety.
3. Control: **Two-Loop Sequential Convex Programming (SCP) + Chance-Constrained MPC (CCMPC)**.
4. Result: point to the stat box — RMSE 2.663 m | 84.7% ↓ | CVR 0.0%.

---

## 4. Introduction (slide 4) — 1:15

Anchor: groundwater = 97% of Earth's freshwater; depletion from Indo-Gangetic aquifer to Ogallala (paper [3], [4]).

Walk the **3 key challenges** (one bullet each):
1. **Spatial scale mismatch** — GRACE ~300 km vs watershed ~4 km. (Most important to stress.)
2. **Vadose-zone nonlinearity** — infiltration → recharge is delayed and nonlinear.
3. **Non-convex stochastic control** — extraction is non-convex under climate uncertainty.

Close with the one-line framework stack:
> GRACE Downscaling → Gamma-Kernel Vadose Dynamics → SciML Surrogates → Conformal Prediction → Sequential Convex Programming.

---

## 5. Literature Review (slide 5) — 1:30

Read the **6-row table** row by row: Research Area / Existing Approaches / Key Limitation / **Approach in This Work**.
Emphasize the progression: GRACE downscaling (registration → mass-conserving), numerical models MODFLOW/FEFLOW (fine grids, slow → SciML surrogates), PINNs, 2D FNO, GNN message passing, and **CCMPC (distributional assumptions → Split Conformal + SCP-CCMPC)**.

Talk naturally, don't enumerate the table; summarize patterns:
> Existing methods solve one piece but break on distortion, speed, or distributional assumptions. We close all four in one loop.

---

## 6. Research Gaps (slide 6) — 0:45

Read the **6 gaps** as a countdown; map each gap to the slide that closes it (gesture forward):
1. Spatial resolution gap → methodology (downscaling).
2. Mass conservation gap → Eq. 4 mass-balance correction.
3. Vadose-zone modelling gap → Gamma-kernel delay.
4. Computational gap → neural surrogates.
5. UQ gap → Split Conformal (no distributional assumptions).
6. Integrated prediction–control gap → unified SCP-CCMPC framework.

> "Every gap on this slide is closed by a named component in the next slide."

---

## 7. Proposed Methodology (slide 7) — 1:45 (longest slide)

Walk the **6 boxes left → right** (flow arrows):
1. **DATA INPUT** — GRACE/GRACE-FO + hydroclimatic data (CHIRPS P, MODIS ET, GLDAS SMSA/SWEA/CWSA, static soils/bedrock/topography, in-situ piezometric wells).
2. **SPATIAL DOWNSCALING** — 300 km → 4 km, 4 phases: (1) mascon-averaged ensemble regression, (2) **scale-preserving mass-balance correction (Eq. 4)**, (3) deep-storage isolation GWSA = TWSA − (SMSA+SWEA+CWSA), (4) head conversion via specific yield Sy → **GWLA**.
3. **VADOSE-ZONE DELAY** — discrete convolution with **Gamma lag kernel** (α from depth-to-bedrock, β from clay fraction) → effective recharge.
4. **SciML PREDICTION** — three complementary surrogates: GNN-LSTM (distance-decay graph + recurrence), **2D Dupuit–Boussinesq PINN** (PDE residual in loss via autodiff), **2D FNO** (spectral learning).
5. **UNCERTAINTY & SAFETY** — Split Conformal finite-sample margin (q̂₀.₉₅ = 0.4926 m).
6. **EXTRACTION OPTIMIZATION** — Two-loop SCP + CCMPC → sustainable pumping schedule under tightened head safety floor.

Optionally point out the code lives at `src/pipeline/pipeline.py` — single orchestration seam.

---

## 8. Results & Discussion (slide 8) — 1:15 **(FIX NNNNNN BOX FIRST)**

**Read the ablation table** (Config A / B / C): A (Local P, ET) 2.6762/2.1614 · B (Raw coarse GRACE) 17.4156/15.1568 · C (Proposed fusion) **2.6635/2.1596**.

**Stat boxes** (point to each):
- **84.7% ERROR REDUCTION** — note it is *vs raw GRACE* (17.42 → 2.66), not vs baseline.
- **95.4% TEST COVERAGE** — above the 95.0% target (Spatial CV §5.2 of paper).
- **0.0% CONTROL VIOLATION RATE** — strict safety floor Gₖ ≥ 35.4926 m enforced for 12 months.

**Add (off-slide, say for Q&A) if time allows:**
> Spatial 4-fold CV leaving out whole well clusters: RMSE 4.0261 m, MAE 3.3640 m — the model generalizes to unseen locations.

---

## 9. Comparative Analysis (slide 9) — 0:45

One sentence per element:
- B → C: **RMSE 17.4156 → 2.6635 m**; raw GRACE suffers mass-contagion spatial distortion.
- Proposed fusion also achieves the **lowest MAE (2.1596 m)** with **CVR 0.0%**.
- Point to the 84.7% stat again.

---

## 10. Conclusion & Future Work (slide 10) — 0:45

**Conclusion** (3 bullets):
1. Unified **SciML + chance-constrained control** framework, satellite-enhanced.
2. Mass-conserving downscaling + Gamma vadose delay feed three surrogates; conformal margin q̂ = 0.4926 m inside two-loop SCP-CCMPC → RMSE 2.6635 m, CVR 0.0%.
3. Delivered end-to-end: FastAPI REST backend, dashboard, 3D subsurface view, depletion alerts, pumping quotas, auto-reports.

**Future Work** (3 bullets):
1. Differentiable **MODFLOW-6** + adaptive conformal prediction (multilayer aquifers).
2. **IoT real-time pumping** via LoRaWAN/cellular flow meters.
3. **Decentralized control** for transboundary aquifers + field validation with monitoring wells/telemetry.

---

## 11. References (slides 11–12) — do not read

Render only, skip unless the panel asks. (25 refs, Springer format, spans two slides.)

---

## 12. Live Demo (2:00) — use the one-page script

Run in `D:\Ground_water` (see `demo_script` block below). If time is cut, show **only** the auto-report page.

**Demo flow (recommended 4-step):**
1. `python -m pytest tests -q` → **18 passed** (fast credibility).
2. `python main.py synthetic` → watch pipeline logs (q_hat ≈ 0.49, LP for CGWBHU2335, SCP converges) → server on :8000.
3. Open dashboard `http://127.0.0.1:8000/` → click a well → conformal forecast band + quota table + 3D subsurface.
4. Open auto-report `http://127.0.0.1:8000/api/v1/reports/view?lat=40.15&lon=-88.25` → full printed Springer-style report.

---

## 13. Q&A (1:00 buffer + panel time)

**Likely questions and their answers:**
- *Is the 84.7% vs the baseline?* → No — it is vs **raw coarse GRACE** (17.4156 m). Baseline A is 2.6762 m; both are near, proposed is best across RMSE and MAE.
- *What data did you actually run?* → 4 hydrogeological basins (Illinois, High Plains/Ogallala, Indo-Gangetic, North German). Default demo is `synthetic` mode; `dwlr` mode uses real CGWB India data (~389k rows); `realtime` needs Earth Engine/GRACE API keys in `.env`.
- *Why is CVR truly 0%?* → Chance-constrained control enforces Gₖ ≥ 35.0 + q̂(0.4926)=35.4926 m; split conformal is distribution-free, so no Gaussian assumption.
- *Why three surrogates?* → Complementary inductive biases — graph spatial coupling, physics PDE residual, spectral operator learning; benchmarked against each other (paper Table 3).
- *How reproducible?* → Synthesis is seeded (seed=42); offline runnable; 18 pytest tests.

---

## Appendix A — One-page demo script

```
# STEP 0 — validation headline (say before launching)
python -m pytest tests -q          # expect: 18 passed (~35 s)

# STEP 1 — launch full system (builds pipeline, then serves API + dashboard)
python main.py synthetic
# logs: Layer 1-3 build, GWLA shape / mean, q_hat ≈ 0.49 m,
#       CGWBHU2335 LP total extraction, SCP converged → http://localhost:8000

# STEP 2 — browsers side by side
#   Dashboard:   http://127.0.0.1:8000/
#   Auto-report: http://127.0.0.1:8000/api/v1/reports/view?lat=40.15&lon=-88.25

# STEP 3 — live endpoints (new cmd window)
curl "http://127.0.0.1:8000/api/v1/status"
curl -X POST "http://127.0.0.1:8000/api/v1/forecast/location_predict" ^
  -H "Content-Type: application/json" ^
  -d "{\"lat\":40.15,\"lon\":-88.25,\"horizon\":12}"
curl -X POST "http://127.0.0.1:8000/api/v1/control/pumping_quotas" ^
  -H "Content-Type: application/json" ^
  -d "{\"horizon\":12,\"h_min\":35.0,\"h_target\":45.0}"
curl "http://127.0.0.1:8000/api/v1/evaluation/paper_baselines"
curl "http://127.0.0.1:8000/api/v1/alerts/depletion"
curl "http://127.0.0.1:8000/api/v1/forecast/spatial_drawdown_3d"
```

**Backup:** the auto-report page alone (prediction + conformal band + LP quota + baselines + ablation + pumping table) is a complete 2-minute demo if the main pipeline is slow.

---

## Appendix B — Deck fixes + consistency log

- [ ] Slide 8: delete `NNNNNN  RESULTS TABLE  JJJJJ` placeholder box.
- [ ] Slide 12: header → `10. References (Contd.)`.
- Numbers verified consistent across paper (Table 3), deck (slides 3/8/9), and code config (16×16, α=0.05, H=12, h_min=35, Δ₀=1.5, τ_max=6).
- Honesty flags: `synthetic` default; `realtime` needs keys; `dwlr` uses real CGWB data.

---

## Appendix C — Archify diagrams (re-verified at HEAD, 24-Sep-2026)

All three generated at commit `4e12086` from the actual code; use as optional backing material if the panel wants a deeper visual.

| Diagram | File | Visually verified | Suggested use |
|---|---|---|---|
| 01-architecture | `archify\diagrams\01-architecture.html` | PASS (0 diagnostics) | Slide 7 backup: 3-tier stack (fastai data → FastAPI service → dashboard) |
| 02-dataflow | `archify\diagrams\02-dataflow.html` | PASS (0 diagnostics) | Slide 7 backup: paper Fig. 1-equivalent message flow (request → pipeline → LP/MPC → report) |
| 03-workflow | `archify\diagrams\03-workflow.html` | PASS (0 diagnostics; viewBox 1230×652) | Appendix / Q&A: synthetic-vs-realtime branch + fallback seam |

All three `deliver` clean, `validate` returns 0 errors / 0 warnings at `--quality showcase`, and all 4 viewports (1440×900, 1600×1000, 1920×1080, 2048×1320) fit — no scrolling, light theme.
Open the `.html` files in Chrome at appendices depth (Ctrl+F `appendix`) for viewer-mode slides before the talk.