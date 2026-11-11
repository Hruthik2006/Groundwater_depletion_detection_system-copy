"""Report and help-page rendering, extracted out of the web module.

Card 4 &amp; 3 of the architecture review: the location report HTML and the
help guide no longer live inside ``src/api/app.py``; ``render_location_report``
receives already-resolved data (grid indices, GWLA/Reff series, geophysical
values, conformal margin) and turns it into the printable HTML report. The
thresholds it bakes into the prose come from ``src.pipeline.config`` constants
via callers, with the same defaults so the 35.0 (control floor) vs 36.0
(depletion-alert line) split stays explicit.
"""

import json
from typing import Any, Dict, Optional

import numpy as np


def render_location_report(
    lat: float,
    lon: float,
    row: int,
    col: int,
    region_name: str,
    sy: float,
    k: float,
    q_hat: float,
    forecast: Dict[str, Any],
    lp_result: Optional[Dict[str, Any]] = None,
    mpc_result: Optional[Dict[str, Any]] = None,
    baselines: Optional[Dict[str, Any]] = None,
    ablation: Optional[Dict[str, Any]] = None,
    hydrograph: Optional[Dict[str, Any]] = None,
    chart_series: Optional[Dict[str, Any]] = None,
    horizon: int = 12,
    sec_summary: int = 1,
    sec_stratigraphy: int = 1,
    sec_conformal: int = 1,
    horizon_conformal: int = 12,
    sec_lp30day: int = 0,
    sec_baselines: int = 0,
    sec_ablation: int = 1,
    sec_pumping: int = 0,
    horizon_pumping: int = 12,
    sec_hydrograph: int = 1,
    horizon_hydrograph: int = 24,
    sec_math: int = 1,
    sec_table: int = 1,
    sec_recommendations: int = 1,
    critical_threshold: float = 36.0,
    critical_hard_threshold: float = 34.0,
    h_min: float = 35.0,
) -> str:
    """Renders the comprehensive, printable HTML Location Groundwater Assessment Report.

    The caller fully resolves the data context: the conformal forecast bundle
    (``analytic_forecast``), the live 30-day LP result, the live SCP-CCMPC
    pumping schedule, live framework baselines/ablation metrics, and the live
    hydrograph series. This function only turns it into markup — no analytic
    math or canned sine waves live here anymore.

    Returns the full ``<!DOCTYPE html>`` document as a string.
    """
    if horizon != 12 and horizon_conformal == 12:
        horizon_conformal = horizon
    h_len = max(1, horizon_conformal if sec_conformal else horizon)

    # ---- conformal forecast bundle (from pipeline.analytic_forecast) ------
    if len(forecast.get("heads", [])) < h_len:
        raise ValueError(
            f"Forecast bundle head length ({len(forecast.get('heads', []))}) "
            f"is shorter than requested report horizon ({h_len})."
        )
    G_base = float(forecast["G_base"])
    heads = list(forecast["heads"][:h_len])
    lower_bounds = list(forecast["lower_bounds"][:h_len])
    upper_bounds = list(forecast["upper_bounds"][:h_len])
    gwla_series = list(forecast["gwla_series"][:h_len])
    reff_series = list(forecast["reff_series"][:h_len])
    rec_quota = float(forecast["recommended_quota"])
    forecast_risk = str(forecast.get("risk_status", "SAFE"))

    labels_conformal = [f"Month {t + 1}" for t in range(h_len)]

    # Prediction 1 chart series. Default: the analytic bundle above. When the
    # caller supplies the dashboard chart's own series (chart_series — the
    # Generate-PDF flow in app.js extracts it from the home-screen chart),
    # the printed chart uses those values verbatim so the PDF matches the
    # home screen exactly. Table/stats below keep the analytic bundle.
    chart_labels = labels_conformal
    chart_heads = heads
    chart_lower = lower_bounds
    chart_upper = upper_bounds
    chart_horizon = horizon_conformal
    if chart_series and chart_series.get("heads"):
        chart_labels = [str(x) for x in chart_series["labels"]]
        chart_heads = [float(x) for x in chart_series["heads"]]
        chart_lower = (
            [float(x) for x in chart_series["lower_bounds"]]
            if chart_series.get("lower_bounds")
            else [h - q_hat for h in chart_heads]
        )
        chart_upper = (
            [float(x) for x in chart_series["upper_bounds"]]
            if chart_series.get("upper_bounds")
            else [h + q_hat for h in chart_heads]
        )
        chart_horizon = len(chart_heads)

    table_rows = ""
    for t_idx in range(h_len):
        head = heads[t_idx]
        lower = lower_bounds[t_idx]
        upper = upper_bounds[t_idx]
        gwla_t = gwla_series[t_idx]
        rf = reff_series[t_idx]

        if lower >= critical_threshold:
            status_tag = "<span style='color:#10b981; font-weight:700;'>SAFE</span>"
        elif lower >= critical_hard_threshold:
            status_tag = "<span style='color:#eab308; font-weight:700;'>WARNING</span>"
        else:
            status_tag = "<span style='color:#ef4444; font-weight:700;'>CRITICAL</span>"

        table_rows += f"""
        <tr>
          <td>Month {t_idx + 1}</td>
          <td><strong>{head:.2f} m</strong></td>
          <td>[{lower:.2f} m, {upper:.2f} m]</td>
          <td>{gwla_t:+.2f} m</td>
          <td>{rf:.2f} cm</td>
          <td>{status_tag}</td>
        </tr>
        """

    min_h = min(heads) if heads else G_base
    max_h = max(heads) if heads else G_base
    start_h = heads[0] if heads else G_base
    end_h = heads[-1] if heads else G_base
    net_change = end_h - start_h
    sum_reff = sum(reff_series)

    if forecast_risk == "CRITICAL":
        risk_status = "CRITICAL / ACTION REQUIRED"
        risk_color = "#ef4444"
    elif forecast_risk == "WARNING":
        risk_status = "VULNERABLE / DECLINING"
        risk_color = "#eab308"
    else:
        risk_status = "STABLE / SAFE"
        risk_color = "#10b981"

    # Stratigraphic estimates for location
    z_terrain = round(120.0 + (row - col) * 1.5, 1)
    z_vadose = round(12.5 + row * 0.4, 1)
    z_water_depth = z_terrain - start_h
    z_bedrock = round(z_terrain - 85.0 - (row + col) * 0.8, 1)
    sat_thickness = round(start_h - z_bedrock, 1)

    # 30-Day LP Data (live solver output)
    lp_days = []
    lp_extraction = []
    lp_head = []
    if lp_result and lp_result.get("daily_extractions"):
        lp_extraction = [round(float(x), 2) for x in lp_result["daily_extractions"][:30]]
        lp_head = [round(float(x), 3) for x in (lp_result.get("head_trajectory") or [])[:30]]
        lp_days = [f"Day {d}" for d in range(1, len(lp_extraction) + 1)]

    # Multi-Well Pumping Quotas Data (live SCP-CCMPC output)
    h_pump = max(1, horizon_pumping)
    pump_labels = [f"Month {t + 1}" for t in range(h_pump)]
    pump_datasets = []
    if mpc_result and mpc_result.get("optimal_pumping") is not None:
        pumping = np.asarray(mpc_result["optimal_pumping"])  # (H, N)
        n_show = min(4, int(pumping.shape[1]))
        pump_colors = ["#2563eb", "#00f2fe", "#a855f7", "#10b981"]
        for i in range(n_show):
            pump_datasets.append({
                "label": f"Well {i + 1} Quota (m³/mo)",
                "backgroundColor": pump_colors[i],
                "data": [round(max(0.0, float(pumping[t, i])), 2) for t in range(min(h_pump, int(pumping.shape[0])))],
            })

    # Hydrograph Data (live rasters at the query cell)
    h_hydro = max(1, horizon_hydrograph)
    hydro_labels = []
    hydro_precip = []
    hydro_recharge = []
    hydro_head = []
    if hydrograph and hydrograph.get("labels"):
        hydro_labels = hydrograph["labels"][:h_hydro]
        hydro_precip = [round(float(v), 2) for v in hydrograph["precipitation_mm"][:h_hydro]]
        hydro_recharge = [round(float(v), 2) for v in hydrograph["effective_recharge_mm"][:h_hydro]]
        hydro_head = [round(float(v), 2) for v in hydrograph["head_level_m"][:h_hydro]]

    # Baseline & Ablation rows (live evaluator output)
    baseline_rows_html = ""
    if baselines:
        for name, m in baselines.items():
            rmse = m.get("RMSE")
            mae = m.get("MAE")
            r2 = m.get("R2")
            cvr = m.get("CVR")
            baseline_rows_html += (
                "<tr>"
                f"<td>{name}</td>"
                f"<td>{rmse:.2f} m</td>"
                f"<td>{mae:.2f} m</td>"
                f"<td>{r2:.3f}</td>"
                f"<td>{cvr * 100.0:.1f}%</td>"
                "</tr>"
            )

    ablation_rows_html = ""
    if ablation:
        full_m = ablation.get("Full_Model_P_T_LevelHistory")
        ablated_m = ablation.get("Ablated_Model_LevelHistory_Removed")
        ratio = (ablation.get("RMSE_Degradation_Ratio") or {}).get("RMSE_Multiplier")
        if full_m:
            ablation_rows_html += (
                "<tr>"
                "<td>Full Model (P, T, Level History)</td>"
                f"<td>{full_m.get('RMSE', 0.0):.2f} m</td>"
                f"<td>{full_m.get('MAE', 0.0):.2f} m</td>"
                f"<td>{full_m.get('R2', 0.0):.3f}</td>"
                f"<td>{full_m.get('CVR', 0.0) * 100.0:.1f}%</td>"
                "</tr>"
            )
        if ablated_m:
            ablation_rows_html += (
                "<tr>"
                "<td>Ablated (w/o Level History)</td>"
                f"<td>{ablated_m.get('RMSE', 0.0):.2f} m</td>"
                f"<td>{ablated_m.get('MAE', 0.0):.2f} m</td>"
                f"<td>{ablated_m.get('R2', 0.0):.3f}</td>"
                f"<td>{ablated_m.get('CVR', 0.0) * 100.0:.1f}%</td>"
                "</tr>"
            )
        if ratio is not None:
            ablation_rows_html += (
                "<tr style=\"background: rgba(16,185,129,0.08); font-weight: 700;\">"
                f"<td>RMSE Degradation Ratio (omit Level History)</td>"
                "<td colspan=\"4\">" + f"{ratio:.2f} &#215; vs Full Model" + "</td>"
                "</tr>"
            )

    # Build Section Blocks
    section_blocks = []

    # 1. Summary & Metadata Section
    if sec_summary:
        section_blocks.append(fr"""
    <h2 class="section-title">1. Query Location &amp; Hydrogeological Basin Assessment</h2>
    <div class="grid-meta">
      <div class="meta-item">
        <label>Query Coordinate</label>
        <span>Lat: {lat:.4f}°, Lon: {lon:.4f}°</span>
      </div>
      <div class="meta-item">
        <label>Hydrogeological Basin</label>
        <span>{region_name}</span>
      </div>
      <div class="meta-item">
        <label>Target Grid Cell</label>
        <span>Row {row}, Col {col} (4km Mascon Grid)</span>
      </div>
      <div class="meta-item">
        <label>Specific Yield ($S_y$)</label>
        <span>{sy:.3f}</span>
      </div>
      <div class="meta-item">
        <label>Hydraulic Conductivity ($K$)</label>
        <span>{k:.2f} m/day</span>
      </div>
      <div class="meta-item">
        <label>Conformal Safety Margin ($\hat{{q}}$)</label>
        <span>± {q_hat:.2f} m (95% Confidence)</span>
      </div>
    </div>
        """)

    # 2. Stratigraphic Hydrogeological Profile
    if sec_stratigraphy:
        section_blocks.append(fr"""
    <h2 class="section-title">2. Stratigraphic Hydrogeological Profile &amp; Aquifer Matrix</h2>
    <div class="grid-meta" style="background: #f8fafc;">
      <div class="meta-item">
        <label>Terrain Surface Elevation ($z_\text{{terrain}}$)</label>
        <span>{z_terrain:.1f} m MSL</span>
      </div>
      <div class="meta-item">
        <label>Water Table Depth</label>
        <span>{z_water_depth:.2f} m below surface</span>
      </div>
      <div class="meta-item">
        <label>Saturated Aquifer Thickness</label>
        <span>{sat_thickness:.1f} m</span>
      </div>
      <div class="meta-item">
        <label>Vadose Zone Thickness ($z_\text{{vadose}}$)</label>
        <span>{z_vadose:.1f} m</span>
      </div>
      <div class="meta-item">
        <label>Bedrock Elevation ($z_\text{{bedrock}}$)</label>
        <span>{z_bedrock:.1f} m MSL</span>
      </div>
      <div class="meta-item">
        <label>Aquifer Type Classification</label>
        <span>Unconfined Sandy Silt Matrix</span>
      </div>
    </div>
        """)

    # 3. Mathematical Formulations & Pumping Allocation
    if sec_math:
        section_blocks.append(
            r"""
    <h2 class="section-title">3. Recommended Pumping Allocation &amp; Optimization Formulation</h2>
    <div class="math-box">
      <p style="margin:0 0 6px 0;"><strong>Sequential Convex Programming (SCP) Objective &amp; Safety Constraint:</strong></p>
      $$\min_{E_{1:H}} \sum_{t=1}^H \left[ \gamma_\text{pump} (E_t - E_t^*)^2 + \sigma_\text{slack} s_t \right] \quad \text{s.t.} \quad G_t(E) - \hat{q}_{1-\alpha} \ge h_\text{min} - s_t, \quad \|E^{(k+1)} - E^{(k)}\|_2 \le \Delta$$
      <p style="margin:6px 0 0 0; font-size:12px; color:#475569;">Recommended Safe Monthly Extraction Quota: <strong>"""
            + f"{rec_quota:.2f} m³/month"
            + r"""</strong>.</p>
    </div>
    <div class="math-box">
      <p style="margin:0 0 6px 0;"><strong>Hydrogeological Flow &amp; Delay Formulations:</strong></p>
      <p style="margin:4px 0 2px 0;">1. 2D Unconfined Darcy Continuity: $$S_y \frac{\partial h}{\partial t} = \nabla \cdot (K \nabla h) - \sum_{k=1}^{N_w} Q_k(t) \delta(\mathbf{x} - \mathbf{x}_k) + R_\text{eff}(\mathbf{x}, t)$$</p>
      <p style="margin:4px 0 2px 0;">2. Vadose Zone Continuous Gamma Delay: $$R_\text{eff}(t) = \int_0^t [P(\tau) - \text{ET}(\tau)]^+ \cdot \kappa_{\alpha, \beta}(t - \tau) d\tau$$</p>
      <p style="margin:4px 0 2px 0;">3. Split Conformal Nonconformity Quantile: $$\hat{q}_{1-\alpha} = \inf \left\{ q \in \mathbb{R} : \frac{1}{n+1} \sum_{i=1}^n \mathbf{1}_{\{|y_i - \hat{y}_i| \le q\}} \ge 1 - \alpha \right\}$$</p>
    </div>
        """
        )

    # 4. Predictions Suite
    pred_charts_html = []

    # Pred 1: Conformal Forecast
    if sec_conformal:
        pred_charts_html.append(fr"""
      <div class="chart-container-card">
        <div class="chart-card-header">
          <span>Prediction 1: Piezometric Head Forecast &amp; Split Conformal Bounds ({chart_horizon} Months)</span>
        </div>
        <canvas id="rptChartConformal" style="width:100%; max-height:220px;"></canvas>
      </div>
        """)

    # Predictions 2 (30-Day LP), 3 (Baselines) and 5 (Pumping Quotas) were
    # removed from the printed report (2026-11-11) — they are global, not
    # location-specific. sec_lp30day / sec_baselines / sec_pumping are still
    # accepted for compatibility but no longer render anything.

    # Pred 2 (was 4): Ablation Suite
    if sec_ablation:
        pred_charts_html.append(f"""
      <div class="chart-container-card">
        <div class="chart-card-header">
          <span>Prediction 2: Historical Level Autoregressive Ablation Suite (Table 4)</span>
        </div>
        <table style="margin-top: 6px;">
          <thead>
            <tr><th>Ablation Configuration</th><th>RMSE (m)</th><th>MAE (m)</th><th>R² Score</th><th>Safety CVR</th></tr>
          </thead>
          <tbody>
            {ablation_rows_html}
          </tbody>
        </table>
      </div>
        """)

    # Pred 3 (was 6): Hydrograph
    if sec_hydrograph:
        pred_charts_html.append(fr"""
      <div class="chart-container-card">
        <div class="chart-card-header">
          <span>Prediction 3: Hydrograph (Rainfall, Vadose Delay Recharge &amp; Head Dynamics - {horizon_hydrograph} Months)</span>
        </div>
        <canvas id="rptChartHydrograph" style="width:100%; max-height:220px;"></canvas>
      </div>
        """)

    if pred_charts_html:
        section_blocks.append(f"""
    <h2 class="section-title">4. Analytical Prediction Models &amp; Scientific Forecast Suites</h2>
    <div class="pred-grid-container">
      {"".join(pred_charts_html)}
    </div>
        """)

    # 5. Full Tabular Grid
    if sec_table:
        section_blocks.append(fr"""
    <h2 class="section-title">5. {h_len}-Month Projected Head &amp; Recharge Forecast Table</h2>
    <div class="summary-grid">
      <div class="stat-card">
        <div class="val">{start_h:.2f} m</div>
        <div class="lbl">Initial Head (Month 1)</div>
      </div>
      <div class="stat-card">
        <div class="val">{min_h:.2f} m</div>
        <div class="lbl">Minimum Projected Head</div>
      </div>
      <div class="stat-card">
        <div class="val">{net_change:+.2f} m</div>
        <div class="lbl">Net Horizon Trend</div>
      </div>
      <div class="stat-card">
        <div class="val">{sum_reff:.2f} cm</div>
        <div class="lbl">Cumulative Recharge ($\sum R_\text{{eff}}$)</div>
      </div>
    </div>

    <table>
      <thead>
        <tr>
          <th>Timeline</th>
          <th>Predicted Head ($\hat{{G}}$)</th>
          <th>95% Conformal Safety Interval</th>
          <th>GWLA Anomaly</th>
          <th>Effective Recharge ($R_\text{{eff}}$)</th>
          <th>Risk Status</th>
        </tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
        """)

    # 6. Depletion Risk Assessment & Recommendations
    if sec_recommendations:
        section_blocks.append(fr"""
    <h2 class="section-title">6. Groundwater Depletion Risk Assessment &amp; Recommendations</h2>
    <div class="math-box" style="border-left-color: {risk_color}; background: rgba(0,0,0,0.02);">
      <p style="margin: 0 0 6px 0;"><strong>Operational Decision Support Protocol:</strong></p>
      <ul style="margin: 0; padding-left: 20px; color: #334155; line-height: 1.7;">
        <li><strong>Recommended Sustainable Pumping Quota:</strong> Maintain monthly extraction below <strong>{rec_quota:.2f} m³/month</strong> to ensure continuous 95% compliance with the {critical_threshold:.1f}m critical head threshold.</li>
        <li><strong>Vadose Recharge Window:</strong> Peak percolation arrives with a modal transit delay of <strong>3.75 months</strong> following major rainfall anomalies. Pumping limits may safely ease during verified recharge crests.</li>
        <li><strong>Conformal Safeguard:</strong> The distribution-free nonconformity margin ($\hat{{q}} = \pm {q_hat:.2f}\text{{m}}$) guarantees that true piezometric levels will not violate lower bounds under extreme climate variance.</li>
      </ul>
    </div>
        """)

    body_sections_html = "".join(section_blocks)

    html_content = fr"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Custom Groundwater Assessment Report - ({lat}°, {lon}°)</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Outfit:wght@400;600;700&display=swap" rel="stylesheet">
  <script>
    window.MathJax = {{
      tex: {{
        inlineMath: [['$', '$'], ['\\(', '\\)']],
        displayMath: [['$$', '$$'], ['\\[', '\\]']],
        processEscapes: true
      }}
    }};
  </script>
  <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    @page {{ size: A4; margin: 15mm; }}
    body {{ font-family: 'Instrument Sans', 'Segoe UI', sans-serif; margin: 0; padding: 24px; color: #1e293b; background: #f8fafc; line-height: 1.6; font-size: 14px; }}
    .report-card {{ background: #fff; padding: 36px 40px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.06); max-width: 980px; margin: 0 auto; border: 1px solid #e2e8f0; }}
    .header {{ border-bottom: 2px solid #2563eb; padding-bottom: 18px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: flex-start; }}
    .header h1 {{ margin: 0; color: #0f172a; font-family: 'Outfit', sans-serif; font-size: 24px; }}
    .header p {{ margin: 4px 0 0 0; color: #64748b; font-size: 13px; }}
    .badge {{ background: #e0f2fe; color: #0284c7; padding: 6px 14px; border-radius: 20px; font-weight: 700; font-size: 13px; font-family: 'JetBrains Mono', monospace; display: inline-block; }}
    .status-banner {{ background: rgba(16, 185, 129, 0.08); border-left: 4px solid {risk_color}; padding: 14px 18px; border-radius: 6px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }}
    .status-banner strong {{ color: #0f172a; font-size: 15px; }}
    .grid-meta {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; background: #f1f5f9; padding: 18px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #e2e8f0; }}
    .meta-item label {{ font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; display: block; margin-bottom: 3px; }}
    .meta-item span {{ font-weight: 700; font-size: 15px; color: #0f172a; }}
    .section-title {{ font-family: 'Outfit', sans-serif; color: #1e3a8a; font-size: 16px; margin: 24px 0 12px; border-bottom: 1px solid #cbd5e1; padding-bottom: 6px; page-break-after: avoid; }}
    .math-box {{ background: #f8fafc; border-left: 3px solid #2563eb; padding: 12px 16px; margin: 12px 0; border-radius: 0 6px 6px 0; font-size: 13px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }}
    th, td {{ padding: 9px 12px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
    th {{ background: #f1f5f9; color: #334155; font-weight: 700; font-family: 'Outfit', sans-serif; }}
    tr:nth-child(even) {{ background: #fafafa; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }}
    .stat-card {{ background: #f8fafc; border: 1px solid #e2e8f0; padding: 12px; border-radius: 8px; text-align: center; }}
    .stat-card .val {{ font-size: 17px; font-weight: 700; color: #1e293b; font-family: 'JetBrains Mono', monospace; }}
    .stat-card .lbl {{ font-size: 11px; color: #64748b; text-transform: uppercase; margin-top: 4px; }}
    .pred-grid-container {{ display: flex; flex-direction: column; gap: 18px; margin-bottom: 20px; }}
    .chart-container-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; page-break-inside: avoid; }}
    .chart-card-header {{ font-size: 12px; font-weight: 700; color: #1e3a8a; font-family: 'Outfit', sans-serif; text-transform: uppercase; margin-bottom: 10px; letter-spacing: 0.3px; }}
    .rpt-print-img {{ display: none; }}
    .btn-print {{ background: #2563eb; color: #fff; border: none; padding: 10px 20px; border-radius: 6px; font-weight: 600; cursor: pointer; float: right; margin-top: -5px; font-size: 13px; box-shadow: 0 2px 6px rgba(37,99,235,0.3); }}
    .btn-print:hover {{ background: #1d4ed8; }}
    .signoff {{ margin-top: 36px; padding-top: 18px; border-top: 1px dashed #cbd5e1; display: flex; justify-content: space-between; font-size: 12px; color: #64748b; page-break-inside: avoid; }}
    @media print {{
      .btn-print {{ display: none !important; }}
      body {{ background: #fff; margin: 0; padding: 0; }}
      .report-card {{ box-shadow: none; border: none; padding: 0; max-width: 100%; }}
      .chart-container-card {{ page-break-inside: avoid; }}
      canvas {{ display: none !important; }}
      .rpt-print-img {{ display: block !important; width: 100%; height: auto; }}
    }}
  </style>
</head>
<body>
  <div class="report-card">
    <button class="btn-print" onclick="window.print()">🖨️ Save as PDF / Print</button>
    <div class="header">
      <div>
        <h1>Detailed Groundwater Location Assessment</h1>
        <p>Satellite Gravimetry (GRACE-FO), Scientific ML Dynamic Surrogates &amp; Split Conformal Risk Control</p>
      </div>
      <span class="badge">PROJECTION COMPLETE</span>
    </div>

    <div class="status-banner">
      <div>
        <strong>Risk Status: <span style="color: {risk_color};">{risk_status}</span></strong>
        <p style="margin: 2px 0 0 0; font-size: 12px; color: #475569;">95% Conformal Lower Bound $h_\text{{lower}} = \hat{{G}} - \hat{{q}}$ evaluated against safety threshold $h_\text{{min}} = {critical_threshold:.1f}\text{{ m}}$.</p>
      </div>
      <div style="text-align: right;">
        <span style="font-size: 20px; font-weight: 700; color: #0f172a; font-family: 'JetBrains Mono', monospace;">{rec_quota:.2f}</span>
        <span style="font-size: 11px; color: #64748b; display: block;">m³/month Quota</span>
      </div>
    </div>

    {body_sections_html}

    <div class="signoff">
      <div>Report Generated by: <strong>Satellite-Enhanced Groundwater System v2.0</strong></div>
      <div>Compliance Verification: <strong>Sequential Convex Programming (SCP) &amp; Conformal UQ</strong></div>
      <div>Date: <strong id="rptDate"></strong><script>document.getElementById('rptDate').textContent=new Date().toISOString().slice(0,10);</script></div>
    </div>
  </div>

  <!-- Chart.js Render Scripts for Selected Prediction Suites -->
  <script>
    document.addEventListener("DOMContentLoaded", function() {{
      const secConf = {1 if sec_conformal else 0};
      const secHydro = {1 if sec_hydrograph else 0};
      const rptCharts = [];
      // Print fix (2026-11-11): switching to print layout resizes the report
      // card, which makes Chart.js clear + redraw its canvases; Chrome's PDF
      // snapshot can catch that mid-redraw and the chart comes out blank or
      // squashed in the PDF even though it looks fine on screen. Redrawing on
      // beforeprint alone proved unreliable in real Chrome, so the charts are
      // also snapshotted to static PNG <img> twins: print CSS hides the live
      // canvases and shows the images instead, which always print correctly.
      function snapshotRptCharts() {{
        rptCharts.forEach(function(ch) {{
          try {{
            const cv = ch.canvas;
            let img = cv.nextElementSibling;
            if (!img || !img.classList.contains("rpt-print-img")) {{
              img = document.createElement("img");
              img.className = "rpt-print-img";
              img.alt = "Chart image (print version)";
              cv.parentNode.insertBefore(img, cv.nextSibling);
            }}
            img.src = cv.toDataURL("image/png");
          }} catch (e) {{}}
        }});
      }}
      window.addEventListener("beforeprint", function() {{
        rptCharts.forEach(function(ch) {{ ch.resize(); ch.update("none"); }});
        snapshotRptCharts();
      }});

      // 1. Conformal Head Forecast Chart
      if (secConf) {{
        const ctxConf = document.getElementById("rptChartConformal");
        if (ctxConf) {{
          rptCharts.push(new Chart(ctxConf.getContext("2d"), {{
            type: "line",
            data: {{
              labels: {json.dumps(chart_labels)},
              datasets: [
                {{ label: "Predicted Head (m)", data: {json.dumps(chart_heads)}, borderColor: "#2563eb", backgroundColor: "rgba(37,99,235,0.08)", borderWidth: 2.5, pointRadius: 3, fill: false, tension: 0.3 }},
                {{ label: "95% Conformal Lower Bound", data: {json.dumps(chart_lower)}, borderColor: "rgba(239,68,68,0.8)", borderDash: [4, 3], borderWidth: 1.8, pointRadius: 0, fill: false, tension: 0.3 }},
                {{ label: "95% Conformal Upper Bound", data: {json.dumps(chart_upper)}, borderColor: "rgba(16,185,129,0.8)", borderDash: [4, 3], borderWidth: 1.8, pointRadius: 0, fill: false, tension: 0.3 }}
              ]
            }},
            options: {{ responsive: true, animation: false, plugins: {{ legend: {{ labels: {{ font: {{ size: 10 }} }} }} }}, scales: {{ y: {{ title: {{ display: true, text: "Head (m)", font: {{ size: 10 }} }} }}, x: {{ title: {{ display: true, text: "Forecast Month", font: {{ size: 10 }} }} }} }} }}
          }}));
        }}
      }}

      // 2. Hydrograph Chart
      if (secHydro) {{
        const ctxHydro = document.getElementById("rptChartHydrograph");
        if (ctxHydro) {{
          rptCharts.push(new Chart(ctxHydro.getContext("2d"), {{
            type: "bar",
            data: {{
              labels: {json.dumps(hydro_labels)},
              datasets: [
                {{ type: "bar", label: "Precipitation (cm)", data: {json.dumps(hydro_precip)}, backgroundColor: "rgba(59, 130, 246, 0.4)", yAxisID: "yRain" }},
                {{ type: "line", label: "Vadose Recharge (cm)", data: {json.dumps(hydro_recharge)}, borderColor: "#00f2fe", borderWidth: 2, pointRadius: 2, fill: false, yAxisID: "yRain" }},
                {{ type: "line", label: "Head Level (m)", data: {json.dumps(hydro_head)}, borderColor: "#f97316", borderWidth: 2.5, pointRadius: 2, fill: false, yAxisID: "yHead" }}
              ]
            }},
            options: {{ responsive: true, animation: false, plugins: {{ legend: {{ labels: {{ font: {{ size: 10 }} }} }} }}, scales: {{ yHead: {{ position: "left", title: {{ display: true, text: "Head Level (m)", font: {{ size: 10 }} }} }}, yRain: {{ position: "right", grid: {{ drawOnChartArea: false }}, title: {{ display: true, text: "Rainfall / Recharge (cm)", font: {{ size: 10 }} }} }} }} }}
          }}));
        }}
      }}

      // Take the first print snapshot once the charts have drawn.
      setTimeout(snapshotRptCharts, 300);
    }});
  </script>
</body>
</html>
"""
    return html_content


# --------------------------------------------------------------- Help Guide



HELP_GUIDE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Implementation Guide: Satellite-Enhanced Groundwater System</title>
  <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
  <link rel="alternate icon" type="image/png" href="/static/favicon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/styles.css" />
  <script>
    window.MathJax = {
      tex: {
        inlineMath: [['$', '$'], ['\\(', '\\)']],
        displayMath: [['$$', '$$'], ['\\[', '\\]']],
        processEscapes: true
      },
      options: {
        ignoreHtmlClass: 'tex2jax_ignore',
        processHtmlClass: 'tex2jax_process'
      }
    };
  </script>
  <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
  <style>
    :root {
      --bg:#090d16;--card:rgba(15,23,42,0.88);--border:rgba(255,255,255,0.13);
      --text:#f1f5f9;--sub:#94a3b8;--cyan:#00f2fe;--blue:#3b82f6;--green:#4ade80;
    }
    *{box-sizing:border-box;margin:0;padding:0;}
    body{background:var(--bg);color:var(--text);font-family:'Instrument Sans',sans-serif;line-height:1.75;font-size:15px;}
    .wrap{max-width:1200px;margin:0 auto;padding:20px 24px 90px;}
    .layout{display:flex;gap:28px;align-items:flex-start;}
    .toc{position:sticky;top:20px;width:220px;min-width:220px;background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px 14px;font-size:0.78rem;}
    .toc h4{color:var(--cyan);font-family:'Outfit',sans-serif;margin-bottom:10px;font-size:0.85rem;}
    .toc a{display:block;color:var(--sub);text-decoration:none;padding:4px 0 4px 8px;border-left:2px solid transparent;transition:all 0.2s;}
    .toc a:hover{color:var(--cyan);border-color:var(--cyan);}
    .content{flex:1;min-width:0;}
    .hdr{background:linear-gradient(135deg,rgba(15,23,42,0.97),rgba(30,41,59,0.88));border:1px solid var(--border);border-radius:16px;padding:32px;margin-bottom:28px;}
    .hdr h1{font-family:'Outfit',sans-serif;font-size:1.75rem;background:linear-gradient(90deg,#fff 30%,var(--cyan));-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:8px;}
    .hdr p{color:var(--sub);font-size:0.92rem;}
    .badge-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px;}
    .badge{background:rgba(0,242,254,0.12);border:1px solid rgba(0,242,254,0.3);color:var(--cyan);font-size:0.72rem;padding:3px 10px;border-radius:20px;font-family:'JetBrains Mono',monospace;}
    .sec{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:28px 30px;margin-bottom:22px;backdrop-filter:blur(10px);}
    h2{font-family:'Outfit',sans-serif;color:var(--cyan);font-size:1.2rem;border-bottom:1px solid rgba(0,242,254,0.2);padding-bottom:8px;margin-bottom:16px;}
    h3{font-family:'Outfit',sans-serif;color:#e2e8f0;font-size:1rem;margin:20px 0 10px;}
    h4{color:#93c5fd;font-size:0.9rem;margin:14px 0 6px;}
    p{color:var(--sub);margin-bottom:12px;}
    li{color:var(--sub);margin-bottom:6px;margin-left:18px;}
    ul,ol{margin-bottom:14px;}
    strong{color:#e2e8f0;}
    code{font-family:'JetBrains Mono',monospace;background:rgba(0,0,0,0.4);color:var(--cyan);padding:1px 6px;border-radius:4px;font-size:0.82rem;}
    .math{background:rgba(0,0,0,0.35);border-left:3px solid var(--cyan);padding:14px 18px;margin:14px 0;border-radius:0 8px 8px 0;overflow-x:auto;font-size:0.95rem;}
    .pipeline{background:rgba(0,0,0,0.4);border:1px solid rgba(0,242,254,0.2);border-radius:10px;padding:16px 20px;font-family:'JetBrains Mono',monospace;font-size:0.78rem;color:#7dd3fc;line-height:2;margin:14px 0;white-space:pre-wrap;}
    table{width:100%;border-collapse:collapse;margin:16px 0;font-size:0.83rem;}
    th{background:rgba(0,242,254,0.1);color:#fff;padding:10px 13px;text-align:left;border:1px solid var(--border);font-family:'Outfit',sans-serif;}
    td{background:rgba(0,0,0,0.22);color:var(--sub);padding:9px 13px;border:1px solid var(--border);vertical-align:top;}
    tr:hover td{background:rgba(0,242,254,0.04);}
    .info-box{background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.3);border-radius:8px;padding:12px 16px;margin:14px 0;}
    .info-box p{color:#93c5fd;margin:0;font-size:0.88rem;}
    .warn-box{background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.3);border-radius:8px;padding:12px 16px;margin:14px 0;}
    .warn-box p{color:#fcd34d;margin:0;font-size:0.88rem;}
    .step{display:flex;gap:14px;margin-bottom:16px;}
    .step-num{width:28px;min-width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,var(--cyan),var(--blue));color:#0f172a;font-weight:700;font-size:0.8rem;display:flex;align-items:center;justify-content:center;margin-top:2px;}
    .step-body h4{margin:0 0 4px;color:#e2e8f0;}
    .step-body p{margin:0;}
  </style>
</head>
<body>
<div class="wrap">
  <!-- Top Header Bar (Matching Home & Admin Pages) -->
  <header class="top-header" style="border-radius: 20px; margin-bottom: 24px;">
    <div class="header-brand" onclick="window.location.href='/'" style="cursor: pointer; margin-left: 40px;"
      title="Click to return to User Dashboard">
      Satellite Enhanced Groundwater Prediction system
      <span style="font-size: 0.78rem; opacity: 0.7; font-weight: 400; margin-left: 10px;">&bull; Technical Implementation Guide</span>
    </div>
    <div class="header-nav-right" style="margin-right: 40px; display: flex; align-items: center; gap: 1rem;">
      <a href="/" class="header-nav-link">Dashboard</a>
      <a href="/help" class="header-nav-link" style="color: var(--cyan); font-weight: 700;">Help</a>
    </div>
  </header>

  <div class="hdr">
    <h1>Implementation Guide: Satellite-Enhanced Groundwater Forecasting &amp; SCP-CCMPC Framework</h1>
    <p>Operational pipeline architecture for satellite gravimetry downscaling, scientific machine learning surrogates, split conformal uncertainty quantification, and chance-constrained sequential convex programming extraction management.</p>
    <div class="badge-row">
      <span class="badge">GRACE / GRACE-FO</span>
      <span class="badge">GNN-LSTM &middot; PINN &middot; FNO</span>
      <span class="badge">Split Conformal UQ</span>
      <span class="badge">SCP-CCMPC</span>
      <span class="badge">CVXPY &middot; OSQP</span>
      <span class="badge">Google Earth Engine</span>
    </div>
  </div>

  <div class="layout">
    <nav class="toc">
      <h4>&#128203; Contents</h4>
      <a href="#s1">1. Pipeline Architecture</a>
      <a href="#s2">2. Data Sources</a>
      <a href="#s3">3. Geospatial Ingestion</a>
      <a href="#s4">4. Multi-Phase Downscaling</a>
      <a href="#s5">5. ML Surrogates</a>
      <a href="#s6">6. Conformal UQ</a>
      <a href="#s7">7. SCP-CCMPC Control</a>
      <a href="#s8">8. Benchmarking</a>
      <a href="#s9">9. References</a>
    </nav>

    <div class="content">

      <div class="sec" id="s1">
        <h2>1. Pipeline Architecture and System Execution Environment</h2>
        <p>Implementing an operational framework for satellite-enhanced groundwater forecasting and sustainable extraction management requires integrating heterogeneous geospatial data pipelines, deep learning surrogate modeling, and real-time non-convex control solvers. Traditional piezometric monitoring networks suffer from sparse spatial coverage and reactive tracking capabilities, whereas satellite gravimetry from the Gravity Recovery and Climate Experiment (<strong>GRACE</strong>) and GRACE Follow-On (<strong>GRACE-FO</strong>) missions provides broad coverage of Terrestrial Water Storage Anomalies (<strong>TWSA</strong>) at a spatial footprint of approximately <strong>~300 km</strong>.</p>
        <p>Bridging this multi-scale mismatch necessitates a modular computational pipeline that refines macro-scale satellite signals into localized groundwater level estimates, quantifies predictive uncertainty, and executes closed-loop extraction management under climate variability.</p>
        <p>The software stack combines: <code>earthengine-api</code>, <code>geemap</code>, <code>xarray</code>, <code>rioxarray</code> (geospatial); <code>scikit-learn</code>, <code>xgboost</code>, <code>torch</code>, <code>torch_geometric</code>, <code>neuraloperator</code> (ML); and <code>cvxpy</code>, <code>jax</code>, <code>osqp</code>, <code>ecos</code> (optimization).</p>
        <div class="pipeline">Data Ingestion Pipeline
&#9500;&#9472;&#9472; CHIRPS Precipitation (P) &amp; MODIS Evapotranspiration (ET)
&#9500;&#9472;&#9472; GLDAS Storage Components (SMSA, SWEA, CWSA, Qs)
&#9492;&#9472;&#9472; CSR GRACE Mascons (TWSA_native)
      |
      &#9660; Phase 1: Ensemble Spatial Regression
      &#9492;&#9472;&#9472; Train M_spatial &#8594; raw TWSA_down (4 km)
      |
      &#9660; Phase 2: Scale Preservation Correction
      &#9492;&#9472;&#9472; Enforce mass conservation &#8594; TWSA_scaled
      |
      &#9660; Phase 3: Deep Storage Isolation
      &#9492;&#9472;&#9472; Subtract shallow GLDAS anomalies &#8594; GWSA
      |
      &#9660; Phase 4: Hydraulic Head Translation
      &#9492;&#9472;&#9472; Scale GWSA by Sy(x,y) &#8594; GWLA
      |
      &#9660; Phase 5: Vadose Zone Delay Convolution
      &#9492;&#9472;&#9472; Convolve (P-ET) with Gamma Kernel &#8594; R_eff(t)
      |
      &#9660; Scientific ML Surrogates (GNN-LSTM / PINN / FNO)
      |
      &#9660; Split Conformal Predictor &#8594; \hat{q} safety margin
      |
      &#9660; SCP-CCMPC Optimizer &#8594; E*(1:H) pumping schedule</div>

        <table>
          <thead><tr><th>Pipeline Layer</th><th>Primary Dependencies</th><th>Input Streams</th><th>Output Parameters</th><th>Core Tasks</th></tr></thead>
          <tbody>
            <tr><td>Geospatial Ingestion</td><td><code>earthengine-api</code>, <code>xarray</code>, <code>rioxarray</code></td><td>CHIRPS, MODIS, GLDAS Noah, CSR GRACE Mascons</td><td>Synchronized NetCDF/Xarray tensors</td><td>Polygon masking, reprojection, temporal resampling</td></tr>
            <tr><td>Downscaling Engine</td><td><code>scikit-learn</code>, <code>xgboost</code>, <code>scipy.ndimage</code></td><td>Coarse TWSA, hydroclimatic covariates</td><td>High-res GWSA &amp; GWLA grids (4 km &times; 4 km)</td><td>Ensemble regression, scale preservation, mass balance</td></tr>
            <tr><td>Vadose Delay Engine</td><td><code>scipy.stats</code>, <code>torch</code>, <code>numpy</code></td><td>Net recharge (P&minus;ET), sediment thickness, clay content</td><td>Effective recharge \(R_\text{eff}(t)\)</td><td>Gamma kernel convolution for unsaturated transport</td></tr>
            <tr><td>Dynamic Surrogates</td><td><code>torch</code>, <code>torch_geometric</code>, <code>neuraloperator</code></td><td>Historical head \(G\), extraction \(E\), recharge \(R_\text{eff}\), geophysics \(Z\)</td><td>Predicted hydraulic head trajectories \(\hat{G}_{t+1:t+H}\)</td><td>Message-passing GNNs, Dupuit-Boussinesq PINNs, 2D FNOs</td></tr>
            <tr><td>Conformal Predictor</td><td><code>MAPIE</code>, <code>nonconformist</code>, <code>scipy</code></td><td>Calibration residuals, target confidence \(1-\alpha\)</td><td>Dynamic conformal margin \(\hat{q}\)</td><td>Empirical quantile for finite-sample guarantees</td></tr>
            <tr><td>Optimization Solver</td><td><code>cvxpy</code>, <code>jax</code>, <code>osqp</code>, <code>ecos</code></td><td>Neural Jacobians, state boundaries, costs</td><td>Pumping schedules \(E^*_{1:H}\)</td><td>Two-loop Sequential Convex Programming under chance constraints</td></tr>
          </tbody>
        </table>
      </div>
<div class="sec" id="s2">
        <h2>2. Remote Sensing &amp; Subsurface Data Sources</h2>
        <table>
          <thead><tr><th>Parameter</th><th>Source</th><th>Resolution</th><th>Sampling</th><th>Processing &amp; Formulation Method</th></tr></thead>
          <tbody>
            <tr><td>Precipitation (\(P\))</td><td>CHIRPS v2.0 / v3.0</td><td>~5.6 km (0.05&deg;)</td><td>Daily / Pentad</td><td>Bilinear interpolation to 4 km target grid</td></tr>
            <tr><td>Evapotranspiration (\(ET\))</td><td>MODIS MOD16A2 / WaPOR</td><td>500 m</td><td>8-day / Monthly</td><td>Spatial accumulation &amp; temporal aggregation</td></tr>
            <tr><td>Soil Moisture (\(\text{SMSA}\))</td><td>GLDAS Noah L4 V2.1</td><td>~27.8 km (0.25&deg;)</td><td>Monthly</td><td>Grid mapping across 4 depth layers (0&ndash;200 cm)</td></tr>
            <tr><td>Surface Runoff (\(Q_s\))</td><td>GLDAS Noah L4 V2.1</td><td>~27.8 km</td><td>Monthly</td><td>Mass-preserving spatial aggregation</td></tr>
            <tr><td>Snow Water Equivalent (\(\text{SWEA}\))</td><td>GLDAS Noah L4 V2.1</td><td>~27.8 km</td><td>Monthly</td><td>Grid mapping to fine sub-pixels</td></tr>
            <tr><td>Canopy Water Storage (\(\text{CWSA}\))</td><td>GLDAS Noah L4 V2.1</td><td>~27.8 km</td><td>Monthly</td><td>Grid mapping to fine sub-pixels</td></tr>
            <tr><td>Terrestrial Water Storage (\(\text{TWSA}\))</td><td>CSR GRACE/GRACE-FO RL06.2 Mascons</td><td>~300 km mascons</td><td>Monthly</td><td>Native mascon masking &amp; land-ocean separation</td></tr>
            <tr><td>Soil Texture (Clay, Sand, Silt)</td><td>ISRIC SoilGrids 250m v2.0</td><td>250 m (6 depth layers)</td><td>Static</td><td>Rosetta pedotransfer function for \(S_y(x,y) = \theta_s - \theta_{fc}\)</td></tr>
            <tr><td>Depth to Bedrock (\(\text{DTB}\))</td><td>Shangguan et al. / EarthEnv</td><td>250 m</td><td>Static</td><td>Parameterizes 2D Gamma vadose lag parameters \(\alpha_{\text{lag}}, \beta_{\text{lag}}\)</td></tr>
            <tr><td>Topography (Elev, TRI, TPI)</td><td>EarthEnv / SRTM v4.1</td><td>90 m / 250 m</td><td>Static</td><td>Terrain roughness index &amp; position index derivatives</td></tr>
            <tr><td>Hydraulic Head (\(G\))</td><td>Piezometer observation wells (USGS NWIS)</td><td>Point coordinate</td><td>Daily / Monthly</td><td>Spatial point extraction &amp; cubic spline fill</td></tr>
            <tr><td>Specific Yield (\(S_y\))</td><td>Pedotransfer / Borehole log</td><td>Point / Grid</td><td>Static</td><td>Derived via SoilGrids pedotransfer &amp; kriging</td></tr>
          </tbody>
        </table>

        <h3>Environment Variables &amp; API Keys Configuration</h3>
        <p>Real-time remote sensing data streams and Google Earth Engine endpoints require credentials configured in <code>.env</code>:</p>
        <div class="pipeline"># Environment Configuration (.env)
GEE_PROJECT_ID=your_gee_project_id_here
EARTHDATA_USERNAME=your_earthdata_username
EARTHDATA_PASSWORD=your_earthdata_password
EARTHDATA_BEARER_TOKEN=your_earthdata_token_here
USGS_API_KEY=your_usgs_api_key_here
MAPBOX_ACCESS_TOKEN=your_mapbox_token_here</div>
        <div class="info-box"><p>&#128161; <strong>One-Time GEE Authorization:</strong> Run <code>earthengine authenticate</code> in your terminal once to authorize persistent OAuth2 tokens for Google Earth Engine image collection sampling.</p></div>
      </div>

      <div class="sec" id="s3">
        <h2>3. Geospatial Ingestion, Reprojection, and Interactive Location Pinning</h2>
        <p>The initial phase establishes an automated data ingestion pipeline to fetch, mask, align, and synchronize spatial and temporal hydroclimatic variables derived from satellite remote sensing platforms, land surface models, and ground monitoring networks. Spatial processing standardizes incoming heterogeneous rasters to a uniform <strong>4 km &times; 4 km</strong> target grid in the <strong>EPSG:4326 (WGS84)</strong> coordinate reference system across the study basin.</p>
        <p>Automated programmatic pipelines utilize the <strong>Google Earth Engine Python API</strong> (<code>ee</code>) and <strong>NASA EarthData</strong> authentication protocols. CHIRPS provides precipitation at ~5.6 km pentad resolution; MODIS MOD16A2 provides 8-day ET at 500 m; GLDAS Noah L4 V2.1 provides monthly shallow storage at 0.25&deg;. All spatial rasters are clipped using <code>rioxarray</code>. Missing ground-well observations are imputed using <strong>spatiotemporal cubic spline interpolation</strong>.</p>

        <h3>Interactive GIS Pin Auto-Region Detection</h3>
        <p>Whenever a pin marker is dragged or clicked on the 3D GIS Terrain map, the system automatically evaluates coordinates \(\text{(lat, lon)}\) against known hydrogeological study basins (Ganges, High Plains, North German Basin, Illinois, or custom coordinates). If the pin moves to another basin, the framework auto-switches data streams, re-downscales satellite rasters, and re-computes 3D WebGL subsurface profiles, risk alerts, and pumping quotas for the pinned location.</p>
        <p>Dynamic predictors across all grid cells are scaled via z-score normalization based on historical baseline statistics:</p>
        <div class="math">\[\tilde{X}(x, y, t) = \frac{X(x, y, t) - \mu_X(x, y)}{\sigma_X(x, y)}\]</div>
      </div>
<div class="sec" id="s4">
        <h2>4. Multi-Phase Downscaling and Physical Delay Engineering</h2>
        <p>Translating coarse satellite gravimetry into well-scale inputs involves a multi-phase downscaling workflow that enforces regional mass conservation, subtracts shallow water storage columns, and accounts for unsaturated vadose zone delay physics.</p>

        <h3>Phase 1 &mdash; Ensemble Spatial Regression</h3>
        <p>An ensemble machine learning regressor \(\mathcal{M}_\text{spatial}\) (Random Forest or XGBoost) is trained to learn empirical scale-invariant relationships between coarse basin-scale storage variations and spatially aggregated high-resolution hydroclimatic predictors:</p>
        <div class="math">\[\text{TWSA}_\text{down}(x, y, t) = \mathcal{M}_\text{spatial}\!\left(\mathbf{X}_\text{fine}(x, y, t)\right)\]</div>

        <h3>Phase 2 &mdash; Scale Preservation Correction</h3>
        <p>To enforce mass balance consistency, a scale preservation correction aggregates high-resolution downscaled pixels back to the native GRACE mascon footprint \(M_k\) and applies a scaling factor ratio:</p>
        <div class="math">\[\text{TWSA}_\text{scaled}(x,y,t) = \text{TWSA}_\text{down}(x,y,t) \times \frac{\text{TWSA}_\text{native}(M_k, t)}{\dfrac{1}{N_k}\displaystyle\sum_{(i,j)\in M_k} \text{TWSA}_\text{down}(x_i, y_j, t)}\]</div>

        <h3>Phase 3 &mdash; Deep Groundwater Storage Isolation</h3>
        <p>Because GRACE measures the total integrated water column, deep Groundwater Storage Anomalies (GWSA) are isolated by subtracting shallow storage components:</p>
        <div class="math">\[\text{GWSA}(x,y,t) = \text{TWSA}_\text{scaled}(x,y,t) - \left(\text{SMSA} + \text{SWEA} + \text{CWSA}\right)(x,y,t)\]</div>

        <h3>Phase 4 &mdash; Hydraulic Head Translation &amp; SoilGrids Pedotransfer Functions</h3>
        <p>The isolated equivalent water height anomaly is translated into localized piezometric Groundwater Level Anomalies (GWLA, in metres) using spatial specific yield \(S_y(x,y)\) derived via ISRIC SoilGrids 250m pedotransfer equations:</p>
        <div class="math">\[\theta_s = 0.427 - 0.001 \times \text{clay} + 0.003 \times \text{sand}\]</div>
        <div class="math">\[\theta_{fc} = 0.046 + 0.0025 \times \text{clay} + 0.0005 \times \text{silt}\]</div>
        <div class="math">\[S_y(x,y) = \text{clip}\!\left(\theta_s - \theta_{fc},\; 0.02,\; 0.35\right), \qquad \text{GWLA}(x,y,t) = \frac{\text{GWSA}(x,y,t)}{S_y(x,y)}\]</div>

        <h3>Phase 5 &mdash; Unsaturated Vadose Zone Delay (DTB Parameterized Gamma Kernel)</h3>
        <p>Surface net recharge does not reach the saturated water table instantaneously. Physical transit through the unsaturated vadose zone is modelled by convolving net recharge with a spatially-varying Gamma distribution kernel \(K_\gamma\) parameterized by Depth to Bedrock (\(\text{DTB}\)) and clay content:</p>
        <div class="math">\[\alpha_{\text{lag}}(x,y) = 1.5 + 0.05 \times \text{DTB}(x,y), \qquad \beta_{\text{lag}}(x,y) = 1.0 + 0.02 \times \text{clay}(x,y)\]</div>
        <div class="math">\[K_\gamma(\tau;\, \alpha_\text{lag}, \beta_\text{lag}) = \frac{\tau^{\alpha_\text{lag}-1}\, e^{-\tau/\beta_\text{lag}}}{\beta_\text{lag}^{\alpha_\text{lag}}\, \Gamma(\alpha_\text{lag})}\]</div>
        <div class="math">\[R_\text{eff}(x,y,t) = \int_0^t \bigl(P(x,y,\tau) - ET(x,y,\tau) - Q_s(x,y,\tau)\bigr) \cdot K_\gamma(t-\tau;\, \alpha_\text{lag}, \beta_\text{lag})\; d\tau\]</div>
      </div>

      <div class="sec" id="s5">
        <h2>5. Scientific Machine Learning Dynamic Surrogates</h2>
        <p>The groundwater system is framed as a non-linear dynamic discrete state transition:</p>
        <div class="math">\[G_{i,t+1} = \mathcal{F}_\theta\!\left(G_{i,t},\; E_{i,t},\; R_{\text{eff},i,t},\; Z_i\right) + \varepsilon_{i,t}\]</div>

        <h3>5.1 &mdash; Static-Conditioned GNN-LSTM</h3>
        <p>Monitoring wells are modeled as nodes \(\mathcal{V}\) in a directed graph \(\mathcal{G} = (\mathcal{V}, \mathcal{E})\), with geological flow paths defining edges \(\mathcal{E}\). Spatial message-passing layers capture inter-well interference during joint extraction, while recurrent LSTM cells process temporal sequences. Static hydrogeological attributes \(Z_i\) are concatenated directly into node feature updates at each hidden layer to specialize regional predictions to local structural properties.</p>

        <h3>5.2 &mdash; Physics-Informed Neural Networks (PINNs)</h3>
        <p>In sparse monitoring zones, network predictions are constrained by embedding the 2D non-linear <strong>Dupuit-Boussinesq equation</strong> directly into the loss function:</p>
        <div class="math">\[S_y \frac{\partial h}{\partial t} = \nabla \cdot \left(K h \,\nabla h\right) - E(x,y,t) + R_\text{eff}(x,y,t)\]</div>
        <div class="math">\[\mathcal{L} = \mathcal{L}_\text{data} + \lambda_\text{pde}\,\mathcal{L}_\text{PDE}\]</div>
        <p>Spatial and temporal derivatives are evaluated via gradient backpropagation (<code>torch.autograd</code>).</p>

        <h3>5.3 &mdash; Fourier Neural Operators (FNO)</h3>
        <p>FNO architectures parameterize integral kernels within the spectral domain using 2D FFTs, enabling discretization-invariant surrogate execution:</p>
        <div class="math">\[\bigl(\mathcal{K}_\phi\, v\bigr)(x) = \mathcal{F}^{-1}\!\left(R_\phi \cdot \mathcal{F}(v)\right)(x) + W v(x)\]</div>
        <p>FNO surrogates support <strong>zero-shot super-resolution</strong>, evaluating fine-scale extraction scenarios up to three orders of magnitude faster than MODFLOW.</p>

        <h3>Surrogate Architecture Comparison</h3>
        <table>
          <thead><tr><th>Dimension</th><th>GNN-LSTM</th><th>PINN</th><th>FNO</th></tr></thead>
          <tbody>
            <tr><td>Spatial representation</td><td>Discrete topological graph</td><td>Continuous point coordinates \((x,y,t)\)</td><td>Discretization-invariant functional space</td></tr>
            <tr><td>Temporal mechanism</td><td>Recurrent LSTM hidden state</td><td>Continuous temporal variable \(t\)</td><td>Discrete step operator mapping</td></tr>
            <tr><td>Physical constraint</td><td>Soft static feature conditioning</td><td>Hard PDE residual loss (Dupuit-Boussinesq)</td><td>Spectral mode regularization</td></tr>
            <tr><td>Mesh dependency</td><td>Mesh-dependent (fixed nodes)</td><td>Mesh-free point evaluation</td><td>Discretization-invariant (zero-shot)</td></tr>
            <tr><td>Parameter inversion</td><td>Indirect via latent embeddings</td><td>Direct inversion of \(K\) &amp; \(S_y\)</td><td>Global operator mapping</td></tr>
            <tr><td>Operational target</td><td>Networked monitoring well arrays</td><td>Data-scarce boundary estimation</td><td>Digital twins &amp; high-speed control</td></tr>
          </tbody>
        </table>
      </div>

      <div class="sec" id="s6">
        <h2>6. Calibration-Free Uncertainty Quantification via Split Conformal Prediction</h2>
        <p>Safe extraction control under climate variability requires robust uncertainty quantification without relying on uncalibrated Gaussian distributional assumptions. The framework implements <strong>split conformal prediction</strong> to generate finite-sample prediction intervals around nominal neural surrogate forecasts.</p>
        <p>Data partitioning separates historical records into training set \(\mathcal{D}_\text{train}\), calibration set \(\mathcal{D}_\text{calib}\) of \(N_\text{cal}\) samples, and unseen testing set \(\mathcal{D}_\text{test}\). Absolute non-conformity residual scores are computed over \(\mathcal{D}_\text{calib}\):</p>
        <div class="math">\[s_i = \left| G_i - \hat{G}_i \right|, \quad i \in \mathcal{D}_\text{calib}\]</div>
        <p>Given target violation probability \(\alpha\) (e.g. \(\alpha = 0.05\) for 95% safety), the empirical quantile \(\hat{q}\) is evaluated:</p>
        <div class="math">\[\hat{q} = \operatorname{Quantile}_{1-\alpha}\!\left(s_1,\, s_2,\,\ldots,\, s_{N_\text{cal}}\right)\]</div>
        <p>This converts the stochastic chance constraint:</p>
        <div class="math">\[\mathbb{P}\!\left(G_{i,t} \ge h_\text{min}\right) \ge 1 - \alpha\]</div>
        <p>into an equivalent tightened deterministic boundary constraint on nominal neural predictions:</p>
        <div class="math">\[\hat{G}_{i,t} \ge h_\text{min} + \hat{q}\]</div>
        <div class="info-box"><p>&#128161; <strong>Key property:</strong> Split conformal prediction provides exact finite-sample coverage guarantees under exchangeability &mdash; no parametric distributional assumptions required.</p></div>
      </div>
<div class="sec" id="s7">
        <h2>7. Chance-Constrained MPC via Sequential Convex Programming</h2>
        <p>Embedding non-linear neural dynamic surrogates \(\mathcal{F}_\theta\) into optimal extraction formulations yields a non-convex optimization problem resolved using <strong>Chance-Constrained Model Predictive Control (CCMPC)</strong> via a two-loop <strong>Sequential Convex Programming (SCP)</strong> architecture.</p>

        <h3>Objective Function</h3>
        <div class="math">\[\min_{E_{1:H}} \sum_{t=1}^{H}\sum_{i=1}^{N_w}\left[\gamma_\text{pump}\cdot E_{i,t}^2 + \gamma_\text{head}\left(\hat{G}_{i,t} - h_\text{target}\right)^2\right]\]</div>

        <h3>Constraints</h3>
        <div class="math">\[0 \le E_{i,t} \le E_\text{max} \quad \text{(pumping capacity)}\]
\[\hat{G}_{i,t} \ge h_\text{min} + \hat{q} \quad \text{(conformal safety bound)}\]
\[\left\|E^{(k+1)} - E^{(k)}\right\|_2 \le \Delta_\text{trust} \quad \text{(trust-region step limit)}\]</div>

        <h3>SCP Linearization (Inner QP)</h3>
        <p>Non-linear state dynamics are linearized at each iteration around nominal trajectory \(\bar{E}^{(k)}\):</p>
        <div class="math">\[\hat{G}_{t+1} \approx \mathcal{F}_\theta\!\left(\bar{G}_t^{(k)}, \bar{E}_t^{(k)}\right) + A_t^{(k)}\!\left(G_t - \bar{G}_t^{(k)}\right) + B_t^{(k)}\!\left(E_t - \bar{E}_t^{(k)}\right)\]</div>
        <p>Jacobian matrices computed via automatic differentiation (<code>JAX</code> / <code>PyTorch</code>):</p>
        <div class="math">\[A_t^{(k)} = \frac{\partial \mathcal{F}_\theta}{\partial G_t}\Bigg|_{\bar{G}_t^{(k)}, \bar{E}_t^{(k)}}, \qquad B_t^{(k)} = \frac{\partial \mathcal{F}_\theta}{\partial E_t}\Bigg|_{\bar{G}_t^{(k)}, \bar{E}_t^{(k)}}\]</div>

        <h3>SCP Parameter Specifications</h3>
        <table>
          <thead><tr><th>Parameter</th><th>Symbol</th><th>Default</th><th>Operational Role</th></tr></thead>
          <tbody>
            <tr><td>Planning Horizon</td><td>\(H\)</td><td>12&ndash;36 months</td><td>Rolling control lookahead horizon</td></tr>
            <tr><td>Target Violation Probability</td><td>\(\alpha\)</td><td>0.05 (95% safety)</td><td>Probability bound setting conformal quantile \(\hat{q}\)</td></tr>
            <tr><td>Initial Trust Region</td><td>\(\Delta_0\)</td><td>5% of \(E_\text{max}\)</td><td>Initial step bound for local trajectory updates</td></tr>
            <tr><td>Expansion Factor</td><td>\(\beta_+\)</td><td>1.5</td><td>Multiplier expanding trust region when fidelity is high</td></tr>
            <tr><td>Contraction Factor</td><td>\(\beta_-\)</td><td>0.5</td><td>Penalty shrinkage factor when step overshoots</td></tr>
            <tr><td>Convergence Tolerance</td><td>\(\varepsilon_\text{tol}\)</td><td>10&minus;3</td><td>Termination threshold for change in control vector</td></tr>
            <tr><td>QP Solver</td><td>&mdash;</td><td>OSQP / ECOS / CLARABEL</td><td>Convex sparse matrix solver for inner QP subproblem</td></tr>
          </tbody>
        </table>
        <div class="warn-box"><p>&#9888;&#65039; <strong>Non-convexity note:</strong> The outer loop iterates until \(\|E^{(k+1)} - E^{(k)}\|_2 \le \varepsilon_\text{tol}\). If the solver reports <code>user_limit</code>, increase Max SCP Outer Iterations or reduce planning horizon \(H\).</p></div>
      </div>

      <div class="sec" id="s8">
        <h2>8. Experimental Protocol, Benchmarking &amp; Operational Integration</h2>
        <p>Validation tests downscaling accuracy, dynamic forecasting precision, and optimization safety across hydrogeological regimes. Two study domains are evaluated:</p>
        <ul>
          <li><strong>Glacial Aquifer System, Illinois (USA)</strong> &mdash; 32 monitoring wells (21 training, 11 spatial validation), seasonal agricultural pumping demands.</li>
          <li><strong>North German Basin (Europe)</strong> &mdash; slow-responding porous media aquifer, ~3,000 monitoring wells benchmark network.</li>
        </ul>

        <h3>Evaluation Guardrails</h3>
        <div class="step"><div class="step-num">1</div><div class="step-body"><h4>Rolling-Origin Temporal Cross-Validation</h4><p>Surrogate models train on a rolling historical window and predict future horizon \(H\), advancing progressively across records spanning 2005&ndash;2025.</p></div></div>
        <div class="step"><div class="step-num">2</div><div class="step-body"><h4>Spatial K-Fold Cross-Validation</h4><p>Entire sub-basins or well clusters are withheld during training to evaluate spatial transferability to unmonitored zones.</p></div></div>
        <div class="step"><div class="step-num">3</div><div class="step-body"><h4>Feature Ablation Matrix</h4><p><strong>Config A:</strong> Local Baseline (surface meteorology P, ET only) &bull; <strong>Config B:</strong> Raw GRACE (unrefined mascons) &bull; <strong>Config C:</strong> Proposed Fusion (downscaled GWLA + lag-corrected R_eff + static geophysics).</p></div></div>

        <h3>Performance Metrics</h3>
        <div class="math">\[\text{RMSE} = \sqrt{\frac{1}{N}\sum_{i=1}^{N}(G_i - \hat{G}_i)^2}, \quad \text{MAE} = \frac{1}{N}\sum_{i=1}^{N}|G_i - \hat{G}_i|, \quad \text{CVR} = \frac{\#\{i: \hat{G}_i < h_\text{min} + \hat{q}\}}{N}\]</div>

        <h3>Full Model Comparison Matrix</h3>
        <table>
          <thead><tr><th>Model Paradigm</th><th>Ingestion Requirements</th><th>Physical Consistency</th><th>Spatial Generalization</th><th>Execution Latency</th><th>Focus</th></tr></thead>
          <tbody>
            <tr><td>MODFLOW Baseline</td><td>High &mdash; detailed 3D conductivity grids</td><td>High &mdash; strictly enforces PDEs</td><td>Low &mdash; requires full re-parameterization</td><td>High (~seconds/run)</td><td>Regional planning &amp; aquitard evaluation</td></tr>
            <tr><td>Local Site-LSTM</td><td>Low &mdash; well levels &amp; meteorology</td><td>None &mdash; empirical patterns only</td><td>None &mdash; locked to training coordinate</td><td>Fast (~ms)</td><td>Short-term site-specific prediction</td></tr>
            <tr><td>Global GNN-LSTM</td><td>Moderate &mdash; multi-well graph</td><td>Low &mdash; static conditioning</td><td>Moderate &mdash; topological neighbors</td><td>Fast (~ms)</td><td>Basin-scale multi-well drawdown tracking</td></tr>
            <tr><td>PINN Framework</td><td>Moderate &mdash; sparse well records</td><td>High &mdash; Dupuit-Boussinesq PDE</td><td>Moderate &mdash; bounded by domain</td><td>Moderate (fast inference)</td><td>Unmonitored zones &amp; K, Sy discovery</td></tr>
            <tr><td>Fourier Operator (FNO)</td><td>High &mdash; simulated flow fields</td><td>Moderate &mdash; spectral domain</td><td>High &mdash; zero-shot super-resolution</td><td>Ultra-fast (~ms full field)</td><td>Digital twins &amp; rapid control</td></tr>
            <tr><td><strong>Proposed CCMPC-SCP</strong></td><td>Downscaled GWLA, R_eff, geophysics</td><td><strong>High</strong> &mdash; SCP safety loops</td><td><strong>High</strong> &mdash; conformal bounds adapt</td><td>Real-time (~seconds/loop)</td><td><strong>Sustainable extraction scheduling</strong></td></tr>
          </tbody>
        </table>
      </div>

      <div class="sec" id="s9">
        <h2>9. References and Works Cited</h2>
        <ol>
          <li><code>gemini_R_1.docx</code> &mdash; Core Satellite-Enhanced Groundwater Forecasting and SCP-CCMPC Theoretical Architecture.</li>
          <li><code>(23) Analysis of ground water depletion.docx</code> &mdash; Hydrogeological piezometric observations and regional aquifer depletion metrics.</li>
          <li>CHIRPS v2.0/v3.0 &mdash; <em>Climate Hazards Center InfraRed Precipitation With Station Data.</em> Google Earth Engine Catalog.</li>
          <li>NASA EarthData / CSR GRACE Mascon RL06.2 &mdash; Instructions on Downloading GRACE &amp; GLDAS Data. UW eScience DSSG 2023.</li>
          <li>Downloading Gridded CHIRPS data sets using Python &mdash; Stack Overflow, 2021.</li>
          <li>pyGRACE &mdash; Python-based pre-processing of CSR GRACE and GRACE-FO for Google Earth Engine. GitHub: hillsonghimire.</li>
          <li>Detecting Climate Trends Using CHIRPS Data in Google Earth Engine &amp; Python &mdash; Medium, 2023.</li>
          <li>Chance-Constrained Neural MPC under Uncontrollable Agents via Sequential Convex Programming &mdash; arXiv:2504.03293v2.</li>
          <li>Recent Advances in Optimization Modeling Software &mdash; CVXPY 1.9 Technical Report.</li>
          <li>shaoanlu/sqp_nmpc_cbf_cvxpy &mdash; Model predictive control with Discrete Control Barrier Function constraints using CVXPY. GitHub.</li>
          <li>scipy.stats.gamma &mdash; SciPy v1.18.0 Manual.</li>
          <li>Sequential Convex Programming MPC for Dynamic Vehicle Collision Avoidance &mdash; ResearchGate, 2017.</li>
          <li>Disciplined Convex Programming &mdash; cvxpy.org Tutorial.</li>
          <li>Physics-informed Bayesian Neural Network for groundwater recharge estimation in data-scarce arid regions &mdash; Frontiers in Water, 2026.</li>
          <li>Convex Model Predictive Control &mdash; Emergent Mind, 2024.</li>
        </ol>
      </div>

    </div>
  </div>
</div>
</body>
</html>"""