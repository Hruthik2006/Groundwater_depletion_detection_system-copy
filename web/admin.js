document.addEventListener("DOMContentLoaded", () => {
  fetchAdminHistory();
  loadUiSettings();
});

async function loadUiSettings() {
  try {
    const res = await fetch("/api/v1/admin/ui-settings");
    const data = await res.json();
    const toggle = document.getElementById("adminProvenanceToggle");
    const stateEl = document.getElementById("adminProvenanceState");
    const show = !data.ui_settings || data.ui_settings.show_provenance_option !== false;
    if (toggle) toggle.checked = show;
    if (stateEl) {
      stateEl.innerText = show
        ? "Currently: the provenance option is VISIBLE in the PDF generator pop-up."
        : "Currently: the provenance option is HIDDEN in the PDF generator pop-up (and never included in generated reports).";
    }
    const sToggle = document.getElementById("adminSensorsToggle");
    const sStateEl = document.getElementById("adminSensorsState");
    const showSensors = !data.ui_settings || data.ui_settings.show_sensors !== false;
    if (sToggle) sToggle.checked = showSensors;
    if (sStateEl) {
      sStateEl.innerText = showSensors
        ? "Currently: the IoT sensor panel is VISIBLE on the dashboard and the sensor option appears in the PDF generator pop-up."
        : "Currently: the IoT sensor panel is HIDDEN on the dashboard and sensor readings are excluded from generated reports.";
    }
  } catch (err) {
    console.error("UI settings load error:", err);
  }
}

async function toggleSensorsVisibility(checkbox) {
  try {
    const res = await fetch("/api/v1/admin/ui-settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ show_sensors: checkbox.checked }),
    });
    const data = await res.json();
    if (data.status === "success") {
      loadUiSettings();
      fetchAdminHistory();
    } else {
      alert("Could not save the setting.");
      checkbox.checked = !checkbox.checked;
    }
  } catch (err) {
    console.error("UI settings save error:", err);
    checkbox.checked = !checkbox.checked;
  }
}

async function toggleProvenanceVisibility(checkbox) {
  try {
    const res = await fetch("/api/v1/admin/ui-settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ show_provenance_option: checkbox.checked }),
    });
    const data = await res.json();
    if (data.status === "success") {
      loadUiSettings();
      fetchAdminHistory();
    } else {
      alert("Could not save the setting.");
      checkbox.checked = !checkbox.checked;
    }
  } catch (err) {
    console.error("UI settings save error:", err);
    checkbox.checked = !checkbox.checked;
  }
}

async function toggleDataChannel(mode) {
  try {
    const res = await fetch("/api/v1/config/data_source", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data_mode: mode }),
    });
    const data = await res.json();
    alert(data.message);
    fetchAdminHistory();
  } catch (err) {
    console.error("Toggle channel error:", err);
  }
}

async function recalibrateConformal() {
  try {
    const res = await fetch("/api/v1/admin/recalibrate?alpha=0.05", {
      method: "POST",
    });
    const data = await res.json();
    alert(`Recalibration complete! New q̂ margin: ${data.new_q_hat.toFixed(4)}m`);
    fetchAdminHistory();
  } catch (err) {
    console.error("Recalibrate error:", err);
  }
}

async function fetchAdminHistory() {
  try {
    const res = await fetch("/api/v1/admin/history");
    const data = await res.json();
    const tbody = document.getElementById("historyTableBody");
    tbody.innerHTML = "";

    if (!data.history || data.history.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-sub);">No historical events recorded yet.</td></tr>`;
      return;
    }

    data.history.forEach(item => {
      const typeBadge = getTypeBadge(item.event_type);
      const statusText = item.converged !== undefined ? (item.converged ? "<span style='color:#4ade80;'>Converged</span>" : "<span style='color:#f87171;'>Completed</span>") : "N/A";
      const horizonVal = item.horizon ? `${item.horizon} mo` : "-";
      const qHatVal = item.q_hat ? `${item.q_hat.toFixed(2)}m` : "-";
      const quotaVal = item.avg_quota ? `${item.avg_quota} m³` : "-";

      tbody.innerHTML += `
        <tr>
          <td>${item.timestamp}</td>
          <td>${typeBadge}</td>
          <td><span style="font-weight:600; color:var(--accent-cyan);">${item.data_mode.toUpperCase()}</span></td>
          <td>${item.detail}</td>
          <td>${horizonVal}</td>
          <td>${qHatVal}</td>
          <td>${quotaVal}</td>
          <td>${statusText}</td>
        </tr>
      `;
    });
  } catch (err) {
    console.error("History fetch error:", err);
  }
}

function getTypeBadge(type) {
  switch (type) {
    case "SCP_OPTIMIZATION":
      return `<span style="background:rgba(0,242,254,0.15); color:var(--accent-cyan); padding:0.2rem 0.5rem; border-radius:4px;">SCP SOLVE</span>`;
    case "DATA_CHANNEL_SWITCH":
      return `<span style="background:rgba(245,158,11,0.15); color:#f59e0b; padding:0.2rem 0.5rem; border-radius:4px;">CHANNEL SWITCH</span>`;
    case "RECALIBRATE_CONFORMAL":
      return `<span style="background:rgba(127,0,255,0.15); color:var(--accent-purple); padding:0.2rem 0.5rem; border-radius:4px;">RECALIBRATION</span>`;
    default:
      return `<span style="background:rgba(255,255,255,0.05); color:#fff; padding:0.2rem 0.5rem; border-radius:4px;">INIT</span>`;
  }
}
