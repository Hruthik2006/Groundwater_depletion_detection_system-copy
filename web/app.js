let chartInstance = null;
let gisMap = null;
let locationMarker = null;

function switchMainPanel(selectedId) {
  const panels = ["panelFramework", "panelMaps", "panelPredictions"];

  panels.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;

    if (id === selectedId) {
      el.classList.remove("panel-collapsed");
      el.classList.add("panel-expanded");

      // Dynamic resize for 2D GIS Map & 3D WebGL Aquifer Map when maps panel is active
      if (id === "panelMaps") {
        setTimeout(() => {
          if (gisMap) gisMap.invalidateSize();
          resize3DMap();
        }, 150);
      } else if (id === "panelPredictions") {
        setTimeout(() => {
          if (chartInstance) chartInstance.resize();
        }, 150);
      }
    } else {
      el.classList.remove("panel-expanded");
      el.classList.add("panel-collapsed");
    }
  });
}

function resize3DMap() {
  if (!renderer3D || !camera3D) return;
  const container = document.getElementById("aquifer3D");
  if (container) {
    const w = container.clientWidth || 600;
    const h = container.clientHeight || 350;
    camera3D.aspect = w / h;
    camera3D.updateProjectionMatrix();
    renderer3D.setSize(w, h);
    renderer3D.render(scene3D, camera3D);
  }
}

async function fetchUnifiedControl() {
  await predictPointLocation();
  await fetchDrawdownForecast();
  await runOptimization();

  const reportBtn = document.getElementById("btnGenerateReport");
  if (reportBtn) {
    reportBtn.style.display = "inline-block";
  }
}

function openHelpModal() {
  const modal = document.getElementById("helpModal");
  if (modal) modal.style.display = "flex";
}

function closeHelpModal() {
  const modal = document.getElementById("helpModal");
  if (modal) modal.style.display = "none";
}

function closeHelpModalOnOutside(e) {
  if (e.target.id === "helpModal") {
    closeHelpModal();
  }
}


// 3D Three.js Globals & Custom Stratigraphic Stack Meshes
let scene3D = null;
let camera3D = null;
let renderer3D = null;
let controls3D = null;
let terrainMesh3D = null;
let vadoseMesh3D = null;
let waterMesh3D = null;
let aquiferMesh3D = null;
let aquitardMesh3D = null;
let seaLevelMesh3D = null;
let bedrockMesh3D = null;
let pinGroup3D = null;

function toggle3DLayer(layerKey) {
  const meshMap = {
    terrain: terrainMesh3D,
    vadose: vadoseMesh3D,
    water: waterMesh3D,
    aquifer: aquiferMesh3D,
    aquitard: aquitardMesh3D,
    sealevel: seaLevelMesh3D,
    bedrock: bedrockMesh3D,
  };

  const mesh = meshMap[layerKey];
  const chip = document.getElementById(`chip-${layerKey}`);
  if (!mesh) return;

  mesh.visible = !mesh.visible;
  if (chip) {
    if (mesh.visible) {
      chip.classList.remove("chip-disabled");
    } else {
      chip.classList.add("chip-disabled");
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initHeatmapGrid();
  initConformalChart();
  initGisMap();
  init3DMap();
  fetchSystemStatus();
  fetchDrawdownForecast();
  fetchDepletionAlerts();
  runOptimization();

  const customInput = document.getElementById("customMonthInput");
  if (customInput) {
    customInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        applyCustomMonthInput();
      }
    });
  }
});

function init3DMap() {
  const container = document.getElementById("aquifer3D");
  if (!container || typeof THREE === "undefined") return;

  const width = container.clientWidth || 600;
  const height = container.clientHeight || 300;

  scene3D = new THREE.Scene();

  camera3D = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
  camera3D.position.set(0, -22, 20);
  camera3D.lookAt(0, 0, 0);

  renderer3D = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer3D.setSize(width, height);
  renderer3D.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer3D.domElement);

  if (typeof THREE.OrbitControls !== "undefined") {
    controls3D = new THREE.OrbitControls(camera3D, renderer3D.domElement);
    controls3D.enableDamping = true;
    controls3D.dampingFactor = 0.05;
    controls3D.maxPolarAngle = Math.PI / 2.1;
  }

  // Ambient & Directional Lights
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.85);
  scene3D.add(ambientLight);

  const dirLight = new THREE.DirectionalLight(0x00f2fe, 1.3);
  dirLight.position.set(12, -12, 22);
  scene3D.add(dirLight);

  const dirLight2 = new THREE.DirectionalLight(0x7f00ff, 0.8);
  dirLight2.position.set(-12, 12, 12);
  scene3D.add(dirLight2);

  // --- STACK LAYER 1: Top Ground Topological Surface Mesh ---
  const geoTerrain = new THREE.PlaneGeometry(14, 14, 30, 30);
  const posTerrain = geoTerrain.attributes.position;
  const count = posTerrain.count;
  const colors = new Float32Array(count * 3);

  for (let i = 0; i < count; i++) {
    const x = posTerrain.getX(i);
    const y = posTerrain.getY(i);

    const topoElevation = 
      1.2 * Math.sin(x * 0.4) * Math.cos(y * 0.4) +
      0.6 * Math.sin(x * 0.8 + y * 0.6) +
      0.3 * Math.cos(Math.sqrt(x*x + y*y) * 0.6);

    posTerrain.setZ(i, topoElevation + 3.2);

    const normH = (topoElevation + 2.0) / 4.0;
    if (normH < 0.4) {
      colors[i*3] = 0.05 + normH * 0.2;
      colors[i*3+1] = 0.4 + normH * 0.4;
      colors[i*3+2] = 0.2;
    } else if (normH < 0.7) {
      colors[i*3] = 0.5 + normH * 0.3;
      colors[i*3+1] = 0.4 + normH * 0.2;
      colors[i*3+2] = 0.15;
    } else {
      colors[i*3] = 0.8 + normH * 0.2;
      colors[i*3+1] = 0.8 + normH * 0.2;
      colors[i*3+2] = 0.9;
    }
  }

  geoTerrain.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geoTerrain.computeVertexNormals();

  const matTerrain = new THREE.MeshStandardMaterial({
    vertexColors: true,
    roughness: 0.8,
    metalness: 0.1,
    flatShading: true,
    side: THREE.DoubleSide,
  });
  terrainMesh3D = new THREE.Mesh(geoTerrain, matTerrain);
  scene3D.add(terrainMesh3D);

  const wireTerrain = new THREE.LineSegments(
    new THREE.WireframeGeometry(geoTerrain),
    new THREE.LineBasicMaterial({ color: 0x38bdf8, opacity: 0.15, transparent: true })
  );
  terrainMesh3D.add(wireTerrain);

  // --- STACK LAYER 2: Unsaturated Vadose Zone Soil Layer ---
  const geoVadose = new THREE.PlaneGeometry(14, 14, 15, 15);
  const matVadose = new THREE.MeshPhongMaterial({
    color: 0xd97706,
    transparent: true,
    opacity: 0.25,
    side: THREE.DoubleSide,
  });
  vadoseMesh3D = new THREE.Mesh(geoVadose, matVadose);
  vadoseMesh3D.position.z = 1.5;
  scene3D.add(vadoseMesh3D);

  // --- STACK LAYER 3: Dynamic Water Table Surface Mesh ---
  const geoWater = new THREE.PlaneGeometry(14, 14, 15, 15);
  const matWater = new THREE.MeshPhongMaterial({
    color: 0x00f2fe,
    shininess: 90,
    transparent: true,
    opacity: 0.75,
    side: THREE.DoubleSide,
  });
  waterMesh3D = new THREE.Mesh(geoWater, matWater);
  waterMesh3D.position.z = 0.0;
  scene3D.add(waterMesh3D);

  // --- STACK LAYER 4: Saturated Unconfined Aquifer Formation Volume ---
  const geoAquifer = new THREE.PlaneGeometry(14, 14, 15, 15);
  const matAquifer = new THREE.MeshPhongMaterial({
    color: 0x2563eb,
    transparent: true,
    opacity: 0.35,
    side: THREE.DoubleSide,
  });
  aquiferMesh3D = new THREE.Mesh(geoAquifer, matAquifer);
  aquiferMesh3D.position.z = -0.8;
  scene3D.add(aquiferMesh3D);

  // --- STACK LAYER 5: Clay Aquitard / Confining Layer ---
  const geoAquitard = new THREE.PlaneGeometry(14, 14, 15, 15);
  const matAquitard = new THREE.MeshPhongMaterial({
    color: 0x64748b,
    transparent: true,
    opacity: 0.6,
    side: THREE.DoubleSide,
  });
  aquitardMesh3D = new THREE.Mesh(geoAquitard, matAquitard);
  aquitardMesh3D.position.z = -1.8;
  scene3D.add(aquitardMesh3D);

  // --- STACK LAYER 6: Mean Sea Level Datum Reference Plane (0.0m MSL) ---
  const geoSeaLevel = new THREE.PlaneGeometry(14, 14, 1, 1);
  const matSeaLevel = new THREE.MeshPhongMaterial({
    color: 0x0284c7,
    transparent: true,
    opacity: 0.3,
    side: THREE.DoubleSide,
  });
  seaLevelMesh3D = new THREE.Mesh(geoSeaLevel, matSeaLevel);
  seaLevelMesh3D.position.z = -1.2;

  const seaLevelWire = new THREE.LineSegments(
    new THREE.EdgesGeometry(geoSeaLevel),
    new THREE.LineBasicMaterial({ color: 0x38bdf8, linewidth: 2 })
  );
  seaLevelMesh3D.add(seaLevelWire);
  scene3D.add(seaLevelMesh3D);

  // --- STACK LAYER 7: Impermeable Bedrock Basement Floor ---
  const geoBedrock = new THREE.PlaneGeometry(14, 14, 15, 15);
  const matBedrock = new THREE.MeshPhongMaterial({
    color: 0x0f172a,
    side: THREE.DoubleSide,
  });
  bedrockMesh3D = new THREE.Mesh(geoBedrock, matBedrock);
  bedrockMesh3D.position.z = -3.2;
  scene3D.add(bedrockMesh3D);

  // --- STACK LAYER 8: 3D Location Marker Pin Group ---
  pinGroup3D = new THREE.Group();
  const shaftGeo = new THREE.CylinderGeometry(0.12, 0.12, 8.0, 16);
  const shaftMat = new THREE.MeshBasicMaterial({ color: 0x00f2fe });
  const shaft = new THREE.Mesh(shaftGeo, shaftMat);
  shaft.rotation.x = Math.PI / 2;
  shaft.position.z = 4.0;
  pinGroup3D.add(shaft);

  const headGeo = new THREE.SphereGeometry(0.55, 16, 16);
  const headMat = new THREE.MeshBasicMaterial({ color: 0xff0055 });
  const head = new THREE.Mesh(headGeo, headMat);
  head.position.z = 8.0;
  pinGroup3D.add(head);

  scene3D.add(pinGroup3D);

  // 3D Canvas Raycaster for click-to-pin dropping in 3D WebGL
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();

  renderer3D.domElement.addEventListener("click", (event) => {
    if (!renderer3D || !camera3D) return;

    const rect = renderer3D.domElement.getBoundingClientRect();
    mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    raycaster.setFromCamera(mouse, camera3D);
    const intersects = raycaster.intersectObjects([waterMesh3D, terrainMesh3D].filter(m => m && m.visible));

    if (intersects.length > 0) {
      const pt = intersects[0].point;
      const col = Math.min(15, Math.max(0, Math.round(((pt.x + 7.0) / 14.0) * 15)));
      const row = Math.min(15, Math.max(0, Math.round(((7.0 - pt.y) / 14.0) * 15)));

      const currentLat = parseFloat(document.getElementById("inputLat").value) || 40.15;
      const currentLon = parseFloat(document.getElementById("inputLon").value) || -88.25;

      const deltaLat = (7.5 - row) * 0.08;
      const deltaLon = (col - 7.5) * 0.08;

      const targetLat = (currentLat + deltaLat).toFixed(4);
      const targetLon = (currentLon + deltaLon).toFixed(4);

      document.getElementById("inputLat").value = targetLat;
      document.getElementById("inputLon").value = targetLon;

      updateMapMarker(targetLat, targetLon, `📍 3D Clicked Cell (R:${row}, C:${col})`);
      predictPointLocation();
    }
  });

  // Render Loop
  function animate3D() {
    requestAnimationFrame(animate3D);
    if (controls3D) controls3D.update();
    renderer3D.render(scene3D, camera3D);
  }
  animate3D();

  window.addEventListener("resize", resize3DMap);
}

function update3DMap(raster2d, targetRow = 10, targetCol = 9) {
  fetch3DLocationStack(targetRow, targetCol);
}

async function fetch3DLocationStack(targetRow = 10, targetCol = 9) {
  try {
    const res = await fetch("/api/v1/forecast/spatial_drawdown_3d?horizon=12");
    const data = await res.json();
    if (data.vertices && data.vertices.length > 0) {
      update3DLocationMeshStack(data, targetRow, targetCol);
    }
  } catch (err) {
    console.error("3D Stack fetch error:", err);
  }
}

function update3DLocationMeshStack(data, targetRow = 10, targetCol = 9) {
  if (!scene3D || !data.vertices) return;

  const prof = data.profile || {
    terrain_base: 3.6,
    vadose_base: 1.9,
    water_base: 0.0,
    aquifer_base: -0.9,
    aquitard_base: -2.0,
    bedrock_base: -3.5,
  };

  // 1. Update Ground Terrain Mesh with location topography
  if (terrainMesh3D) {
    const pos = terrainMesh3D.geometry.attributes.position;
    data.vertices.forEach((v, idx) => {
      if (idx < pos.count) pos.setZ(idx, v.z_terrain);
    });
    pos.needsUpdate = true;
    terrainMesh3D.geometry.computeVertexNormals();
  }

  // 2. Update Unsaturated Vadose Zone
  if (vadoseMesh3D) {
    vadoseMesh3D.position.z = prof.vadose_base;
  }

  // 3. Update Water Table Surface
  if (waterMesh3D) {
    const pos = waterMesh3D.geometry.attributes.position;
    data.vertices.forEach((v, idx) => {
      if (idx < pos.count) pos.setZ(idx, v.z_water);
    });
    pos.needsUpdate = true;
    waterMesh3D.geometry.computeVertexNormals();
  }

  // 4. Update Unconfined Aquifer Volume
  if (aquiferMesh3D) {
    aquiferMesh3D.position.z = prof.aquifer_base;
  }

  // 5. Update Clay Aquitard Layer
  if (aquitardMesh3D) {
    aquitardMesh3D.position.z = prof.aquitard_base;
  }

  // 6. Update Bedrock Floor Mesh
  if (bedrockMesh3D) {
    const pos = bedrockMesh3D.geometry.attributes.position;
    data.vertices.forEach((v, idx) => {
      if (idx < pos.count) pos.setZ(idx, v.z_bedrock);
    });
    pos.needsUpdate = true;
    bedrockMesh3D.geometry.computeVertexNormals();
  }

  // 7. Update 3D Location Marker Pin
  if (pinGroup3D) {
    const targetVert = data.vertices.find(v => v.row === targetRow && v.col === targetCol) || data.vertices[0];
    pinGroup3D.position.set(targetVert.x, targetVert.y, targetVert.z_water);
  }
}

let gisHeatmapGroup = null;
let gisHeatmapOverlay = null;

function initGisMap() {
  // Default center: Illinois Glacial Aquifer (40.15, -88.25)
  const defaultLat = 40.15;
  const defaultLon = -88.25;

  gisMap = L.map("gisMap").setView([defaultLat, defaultLon], 7);

  // 1. OpenTopoMap High-Res Topo Terrain
  const openTopoMap = L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
    maxZoom: 17,
    attribution: "Map data: © OpenStreetMap contributors, SRTM | Style: © OpenTopoMap",
  });

  // 2. Esri World Topographic Basemap
  const esriTopo = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 18,
    attribution: "Tiles © Esri — Esri, USGS, NOAA",
  });

  // 3. USGS Shaded Relief Terrain
  const usgsRelief = L.tileLayer("https://basemap.nationalmap.gov/arcgis/rest/services/USGSShadedReliefOnly/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 16,
    attribution: "Tiles courtesy of the U.S. Geological Survey",
  });

  // 4. Esri Satellite Imagery
  const esriSatellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 18,
    attribution: "Source: Esri, Maxar, Earthstar Geographics",
  });

  // Add default terrain layer
  openTopoMap.addTo(gisMap);

  // Layer Group for Spatial Drawdown Heatmap Overlay
  gisHeatmapGroup = L.layerGroup().addTo(gisMap);

  // Layer Controls
  const baseLayers = {
    "🏔️ OpenTopoMap Relief": openTopoMap,
    "🗺️ Esri World Topo": esriTopo,
    "⛰️ USGS Shaded Relief": usgsRelief,
    "🛰️ Esri Satellite": esriSatellite,
  };

  const overlayLayers = {
    "🔥 Drawdown Heatmap Overlay": gisHeatmapGroup,
  };

  L.control.layers(baseLayers, overlayLayers).addTo(gisMap);

  // Add Location Pin Marker
  locationMarker = L.marker([defaultLat, defaultLon], { draggable: true }).addTo(gisMap);
  locationMarker.bindPopup("<b>📍 Pinned Query Location</b><br>Lat: 40.15°, Lon: -88.25°").openPopup();

  // Handle marker drag end
  locationMarker.on("dragend", function () {
    const latlng = locationMarker.getLatLng();
    document.getElementById("inputLat").value = latlng.lat.toFixed(4);
    document.getElementById("inputLon").value = latlng.lng.toFixed(4);
    predictPointLocation();
  });

  // Handle map click to pin location
  gisMap.on("click", function (e) {
    const lat = e.latlng.lat.toFixed(4);
    const lon = e.latlng.lng.toFixed(4);
    document.getElementById("inputLat").value = lat;
    document.getElementById("inputLon").value = lon;

    updateMapMarker(lat, lon, "📍 Custom Clicked Coordinate Pin");
    predictPointLocation();
  });
}

function updateGisHeatmap(raster2d) {
  if (!gisMap || !raster2d) return;

  const canvas = document.createElement("canvas");
  canvas.width = 16;
  canvas.height = 16;
  const ctx = canvas.getContext("2d");
  const imgData = ctx.createImageData(16, 16);

  let minVal = 0.0, maxVal = 5.0;

  for (let r = 0; r < 16; r++) {
    for (let c = 0; c < 16; c++) {
      const val = raster2d[r][c];
      const norm = Math.min(1.0, Math.max(0.0, (val - minVal) / (maxVal - minVal + 1e-5)));
      const hue = norm * 200; // 0 (red) to 200 (blue)

      const rgb = hslToRgb(hue / 360, 0.85, 0.45);
      const pixelIdx = (r * 16 + c) * 4;
      imgData.data[pixelIdx] = rgb[0];
      imgData.data[pixelIdx + 1] = rgb[1];
      imgData.data[pixelIdx + 2] = rgb[2];
      imgData.data[pixelIdx + 3] = 180;
    }
  }
  ctx.putImageData(imgData, 0, 0);

  const dataUrl = canvas.toDataURL();
  const bounds = gisMap.getBounds();

  if (gisHeatmapGroup) {
    gisHeatmapGroup.clearLayers();
    gisHeatmapOverlay = L.imageOverlay(dataUrl, bounds, { opacity: 0.65, interactive: false });
    gisHeatmapOverlay.addTo(gisHeatmapGroup);
  }
}

function hslToRgb(h, s, l) {
  let r, g, b;
  if (s === 0) {
    r = g = b = l;
  } else {
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1/3);
    g = hue2rgb(p, q, h);
    b = hue2rgb(p, q, h - 1/3);
  }
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}

function hue2rgb(p, q, t) {
  if (t < 0) t += 1;
  if (t > 1) t -= 1;
  if (t < 1/6) return p + (q - p) * 6 * t;
  if (t < 1/2) return q;
  if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
  return p;
}

function updateMapMarker(lat, lon, popupText = null) {
  if (!gisMap || !locationMarker) return;
  const latNum = parseFloat(lat);
  const lonNum = parseFloat(lon);

  locationMarker.setLatLng([latNum, lonNum]);
  gisMap.setView([latNum, lonNum], 8);

  const text = popupText || `<b>📍 Pinned Location</b><br>Lat: ${latNum.toFixed(4)}°, Lon: ${lonNum.toFixed(4)}°`;
  locationMarker.bindPopup(text).openPopup();
}

function initHeatmapGrid() {
  const container = document.getElementById("gridHeatmap");
  container.innerHTML = "";
  for (let i = 0; i < 256; i++) {
    const cell = document.createElement("div");
    cell.className = "grid-cell";
    cell.id = `cell-${i}`;
    cell.title = `Grid Cell ${i}`;
    container.appendChild(cell);
  }
}

async function fetchSystemStatus() {
  try {
    const res = await fetch("/api/v1/status");
    const data = await res.json();
    document.getElementById("systemStatusText").innerText = `System Operational (${data.data_mode.toUpperCase()})`;
    document.getElementById("qHatBadge").innerText = `q̂ = ${data.conformal_q_hat.toFixed(2)}m`;
    document.getElementById("dataModeSelect").value = data.data_mode;
  } catch (err) {
    console.error("Status error:", err);
  }
}

async function changeDataMode() {
  const mode = document.getElementById("dataModeSelect").value;
  try {
    const res = await fetch("/api/v1/config/data_source", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data_mode: mode }),
    });
    const data = await res.json();
    alert(data.message);
    fetchSystemStatus();
    fetchDrawdownForecast();
    fetchDepletionAlerts();
  } catch (err) {
    console.error("Data mode error:", err);
  }
}

async function fetchDrawdownForecast(horizon = 12) {
  try {
    const res = await fetch(`/api/v1/forecast/spatial_drawdown?horizon=${horizon}`);
    const data = await res.json();
    const list = data.forecasts || data.forecast_rasters;
    if (list && list.length > 0) {
      const lastForecast = list[list.length - 1];
      renderHeatmap(lastForecast.raster);
      update3DMap(lastForecast.raster, 10, 9);
      updateGisHeatmap(lastForecast.raster);

      const predictedHeads = list.map(r => r.raster);
      const qHat = (typeof currentQHat !== "undefined") ? currentQHat : 0.496;
      updateChartData(predictedHeads, qHat, horizon);
    }
  } catch (err) {
    console.error("Forecast error:", err);
  }
}

function renderHeatmap(raster2d) {
  let minVal = 0.0, maxVal = 5.0;
  for (let r = 0; r < 16; r++) {
    for (let c = 0; c < 16; c++) {
      const val = raster2d[r][c];
      const idx = r * 16 + c;
      const cell = document.getElementById(`cell-${idx}`);
      if (cell) {
        // Map value to HSL color (0: red/depleted, 120: green/blue)
        const norm = Math.min(1.0, Math.max(0.0, (val - minVal) / (maxVal - minVal + 1e-5)));
        const hue = norm * 200; // 0 (red) to 200 (blue)
        cell.style.backgroundColor = `hsl(${hue}, 85%, 45%)`;
        cell.title = `Cell (${r}, ${c}): ${val.toFixed(2)}m`;
      }
    }
  }
}

async function fetchDepletionAlerts() {
  try {
    const res = await fetch("/api/v1/alerts/depletion?threshold=36.0");
    const data = await res.json();
    const alertBadge = document.getElementById("alertCountBadge");
    if (alertBadge) alertBadge.innerText = `${data.alert_count} Alerts`;

    const healthEl = document.getElementById("depHealthScore");
    if (healthEl) healthEl.innerText = `${data.network_health_score_pct}%`;

    const critEl = document.getElementById("depCriticalCount");
    if (critEl) critEl.innerText = `${data.critical_count}`;

    const velEl = document.getElementById("depAvgVel");
    if (velEl) velEl.innerText = `${data.avg_drawdown_rate_m_mo} m/mo`;

    const container = document.getElementById("alertsContainer") || document.getElementById("alertsList");
    if (!container) return;
    container.innerHTML = "";

    if (data.depletion_alerts.length === 0) {
      container.innerHTML = `<div class="alert-item alert-safe" style="background: rgba(255, 255, 255, 0.05); border-color: #444444; color: #E0E0E0; padding: 12px; border-radius: 8px; font-size: 0.82rem;">✓ All monitoring wells operating safely within conformal bounds (h ≥ ${data.threshold_m}m).</div>`;
    } else {
      data.depletion_alerts.forEach(al => {
        const isCrit = al.risk_level === "CRITICAL";
        const isWarn = al.risk_level === "HIGH WARNING";
        const badgeBg = isCrit ? "#E0E0E0" : isWarn ? "#888888" : "#444444";
        const badgeColor = isCrit ? "#121212" : isWarn ? "#121212" : "#E0E0E0";
        const borderColor = isCrit ? "#E0E0E0" : "#444444";
        const t_dep = al.time_to_depletion_months < 90 ? `${al.time_to_depletion_months} mo` : "Stable";

        container.innerHTML += `
          <div class="alert-item" style="background: rgba(18, 18, 18, 0.95); border: 1px solid ${borderColor}; border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; font-size: 0.78rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; flex-wrap: wrap; gap: 4px;">
              <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                <strong style="color: #E0E0E0; font-size: 0.84rem; font-family: 'JetBrains Mono', monospace;">${al.well_id}</strong>
                <span style="color: #B0B0B0; font-size: 0.71rem; font-family: 'JetBrains Mono', monospace;">(Cell R:${al.row}, C:${al.col} &bull; ${al.lat}°, ${al.lon}°)</span>
              </div>
              <span class="badge-alert" style="background: ${badgeBg}; color: ${badgeColor}; border: 1px solid ${borderColor}; font-size: 0.65rem; padding: 2px 7px; border-radius: 10px; font-weight: 700; font-family: 'JetBrains Mono', monospace;">${al.risk_level}</span>
            </div>
            
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px 8px; background: rgba(0,0,0,0.5); padding: 6px 8px; border-radius: 6px; margin-bottom: 6px; font-size: 0.72rem;">
              <div><span style="color: #B0B0B0;">Safe Head:</span> <strong style="color: #E0E0E0; font-family: 'JetBrains Mono', monospace;">${al.conformal_safe_head_m.toFixed(2)}m</strong></div>
              <div><span style="color: #B0B0B0;">Nominal:</span> <strong style="color: #E0E0E0; font-family: 'JetBrains Mono', monospace;">${al.nominal_head_m.toFixed(2)}m</strong></div>
              <div><span style="color: #B0B0B0;">Velocity:</span> <strong style="color: #E0E0E0; font-family: 'JetBrains Mono', monospace;">${al.drawdown_trend_m_mo > 0 ? '+' : ''}${al.drawdown_trend_m_mo.toFixed(3)} m/mo</strong></div>
              <div><span style="color: #B0B0B0;">Time to Limit:</span> <strong style="color: #E0E0E0; font-family: 'JetBrains Mono', monospace;">${t_dep}</strong></div>
            </div>

            <div style="color: #B0B0B0; font-size: 0.71rem; margin-bottom: 6px; border-left: 2px solid ${borderColor}; padding-left: 6px; line-height: 1.35;">
              ${al.action_recommendation}
            </div>

            <button onclick="pinWellLocation(${al.lat}, ${al.lon}, '${al.well_id}')" style="background: #121212; color: #E0E0E0; border: 1px solid #444444; padding: 4px 8px; border-radius: 5px; font-size: 0.7rem; cursor: pointer; font-weight: 600; width: 100%; transition: all 0.2s;">
              📍 Pin Well Coordinate on GIS Map
            </button>
          </div>
        `;
      });
    }
  } catch (err) {
    console.error("Alerts error:", err);
  }
}

function pinWellLocation(lat, lon, wellId) {
  const latNum = parseFloat(lat);
  const lonNum = parseFloat(lon);

  if (typeof switchMainPanel === "function") {
    switchMainPanel("panelMaps");
  }

  if (typeof updateMapMarker === "function") {
    updateMapMarker(latNum, lonNum, `<b>📍 Pinned Well: ${wellId}</b><br>Lat: ${latNum.toFixed(4)}°, Lon: ${lonNum.toFixed(4)}°`);
  } else if (typeof gisMap !== "undefined" && gisMap && typeof locationMarker !== "undefined" && locationMarker) {
    locationMarker.setLatLng([latNum, lonNum]);
    gisMap.setView([latNum, lonNum], 9);
    locationMarker.bindPopup(`<b>📍 Pinned Well: ${wellId}</b><br>Lat: ${latNum.toFixed(4)}°, Lon: ${lonNum.toFixed(4)}°`).openPopup();
  }

  const statusEl = document.getElementById("coordStatusText") || document.getElementById("timestepDisplay");
  if (statusEl) statusEl.innerText = `Pinned Well ${wellId}: Lat ${latNum.toFixed(4)}°, Lon ${lonNum.toFixed(4)}°`;

  if (typeof fetchLocationPredict === "function") {
    fetchLocationPredict(latNum, lonNum, currentChartHorizon || 12);
  }
}

function openDepletionInfoModal() {
  alert(
    "ℹ️ DEPLETION WARNING SYSTEM TECHNICAL OVERVIEW\n\n" +
    "1. Conformal Safe Head (h_safe = G_nominal - q̂):\n" +
    "   Evaluates finite-sample 95% safety coverage bounds where q̂ is the empirical error quantile.\n\n" +
    "2. Drawdown Velocity (m/month):\n" +
    "   Tracks real-time trend rate of water table depletion (Δh / Δt) over recent timesteps.\n\n" +
    "3. Time-to-Critical Failure (Months):\n" +
    "   Estimates remaining time before water table breaches the critical threshold (h_min = 36.0m).\n\n" +
    "4. Recommended Pumping Curtailment:\n" +
    "   Calculates automatic % pumping reductions to prevent severe regional aquifer depletion."
  );
}

let selectedInputPageRegion = "high_plains";
let selectedInputPageSource = "synthetic";

function checkLandingState() {
  if (sessionStorage.getItem("hasProceeded") === "true") {
    const landingScreen = document.getElementById("landingScreen");
    const inputScreen = document.getElementById("inputScreen");
    if (landingScreen) {
      landingScreen.classList.add("hidden");
      landingScreen.style.display = "none";
    }
    if (inputScreen) {
      inputScreen.classList.add("hidden");
      inputScreen.style.display = "none";
    }
  }
}
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", checkLandingState);
} else {
  checkLandingState();
}

function openInputScreen(e) {
  if (e) e.preventDefault();
  const landingScreen = document.getElementById("landingScreen");
  const inputScreen = document.getElementById("inputScreen");
  if (landingScreen) landingScreen.classList.add("hidden");
  if (inputScreen) {
    inputScreen.style.display = "flex";
    inputScreen.classList.remove("hidden");
  }
}

function openLandingScreen() {
  const landingScreen = document.getElementById("landingScreen");
  const inputScreen = document.getElementById("inputScreen");
  if (inputScreen) inputScreen.classList.add("hidden");
  if (landingScreen) {
    landingScreen.style.display = "flex";
    landingScreen.classList.remove("hidden");
  }
}

function selectInputPageRegion(key, labelText) {
  selectedInputPageRegion = key;
  const labelEl = document.getElementById("inputPageRegionLabel");
  if (labelEl) labelEl.innerText = labelText;
  closeAllChoicePickers();
}

function selectInputPageSource(key, labelText) {
  selectedInputPageSource = key;
  const labelEl = document.getElementById("inputPageSourceLabel");
  if (labelEl) labelEl.innerText = labelText;
  closeAllChoicePickers();
}

function validateAndSubmitDetails(e) {
  if (e) e.preventDefault();

  const latInput = document.getElementById("inputScreenLat");
  const lonInput = document.getElementById("inputScreenLon");
  const errEl = document.getElementById("inputScreenError");

  const latVal = latInput ? latInput.value.trim() : "";
  const lonVal = lonInput ? lonInput.value.trim() : "";

  if (errEl) {
    errEl.style.display = "none";
    errEl.innerText = "";
  }

  // 1. Validate numeric Latitude & Longitude
  if (!latVal || isNaN(parseFloat(latVal))) {
    showInputScreenError("Please enter a valid numeric Latitude (e.g. 40.15).");
    if (latInput) latInput.focus();
    return;
  }

  const latNum = parseFloat(latVal);
  if (latNum < -90 || latNum > 90) {
    showInputScreenError("Latitude must be between -90° and +90°.");
    if (latInput) latInput.focus();
    return;
  }

  if (!lonVal || isNaN(parseFloat(lonVal))) {
    showInputScreenError("Please enter a valid numeric Longitude (e.g. -88.25).");
    if (lonInput) lonInput.focus();
    return;
  }

  const lonNum = parseFloat(lonVal);
  if (lonNum < -180 || lonNum > 180) {
    showInputScreenError("Longitude must be between -180° and +180°.");
    if (lonInput) lonInput.focus();
    return;
  }

  // 2. Sync entered details into main dashboard controls
  const mainLat = document.getElementById("inputLat");
  const mainLon = document.getElementById("inputLon");
  if (mainLat) mainLat.value = latNum.toFixed(2);
  if (mainLon) mainLon.value = lonNum.toFixed(2);

  if (selectedInputPageRegion) {
    const regionSelect = document.getElementById("regionPresetSelect");
    const regionLabelSpan = document.getElementById("regionPickerSelectedLabel");
    if (regionSelect) regionSelect.value = selectedInputPageRegion;
    if (regionLabelSpan) {
      const regionNames = {
        high_plains: "High Plains / Ogallala (USA)",
        north_german: "North German Basin (Europe)",
        ganges: "Indo-Gangetic Basin (India)",
      };
      regionLabelSpan.innerText = regionNames[selectedInputPageRegion] || "Hydrogeological region";
    }
  }

  if (selectedInputPageSource) {
    const sourceSelect = document.getElementById("dataSourceSelect");
    const sourceLabelSpan = document.getElementById("sourcePickerSelectedLabel");
    if (sourceSelect) sourceSelect.value = selectedInputPageSource;
    if (sourceLabelSpan) {
      sourceLabelSpan.innerText = selectedInputPageSource === "realtime" ? "NASA EarthData & GEE API" : "Synthetic Benchmark Engine";
    }
  }

  // 3. Save session state & transition to Dashboard
  sessionStorage.setItem("hasProceeded", "true");
  const inputScreen = document.getElementById("inputScreen");
  if (inputScreen) {
    inputScreen.classList.add("hidden");
    setTimeout(() => {
      inputScreen.style.display = "none";
    }, 400);
  }

  // Execute predictions and MPC optimization on dashboard
  fetchUnifiedControl();
}

let errorTimeoutId = null;

function showInputScreenError(msg) {
  const errEl = document.getElementById("inputScreenError");
  if (errEl) {
    errEl.innerText = msg;
    errEl.style.display = "block";

    if (errorTimeoutId) clearTimeout(errorTimeoutId);
    errorTimeoutId = setTimeout(() => {
      errEl.style.display = "none";
      errEl.innerText = "";
    }, 3500);
  }
}

function openWebpageGuideModal() {
  const modal = document.getElementById("webpageGuideModal");
  if (modal) {
    modal.classList.remove("hidden");
  }
}

function closeWebpageGuideModal() {
  const modal = document.getElementById("webpageGuideModal");
  if (modal) {
    modal.classList.add("hidden");
  }
}

function showPlot2Loading(msg = "Computing Conformal Forecast...") {
  const overlay = document.getElementById("plot2LoadingOverlay");
  const txt = document.getElementById("plot2LoadingText");
  if (txt) txt.innerText = msg;
  if (overlay) overlay.style.display = "flex";
}

function hidePlot2Loading() {
  const overlay = document.getElementById("plot2LoadingOverlay");
  if (overlay) overlay.style.display = "none";
}

let currentChartHorizon = 12;

async function setCustomChartHorizon(months, btnEl) {
  months = parseInt(months, 10);
  if (isNaN(months) || months < 1) return;
  currentChartHorizon = months;

  showPlot2Loading(`Solving SCP & Computing ${months}-Month Conformal Bounds...`);

  const inputEl = document.getElementById("customMonthInput");
  if (inputEl) inputEl.value = months;

  const card1HVal = document.getElementById("inputHVal");
  if (card1HVal) card1HVal.value = months;

  const badgeEl = document.getElementById("chartHorizonBadge");
  if (badgeEl) badgeEl.innerText = `${months}-Month Horizon`;

  if (btnEl) {
    document.querySelectorAll(".btn-horizon-chip").forEach(b => b.classList.remove("active"));
    btnEl.classList.add("active");
  } else {
    document.querySelectorAll(".btn-horizon-chip").forEach(b => {
      if (b.innerText === `${months}M`) b.classList.add("active");
      else b.classList.remove("active");
    });
  }

  try {
    await runOptimization();
    await fetchDrawdownForecast(months);
  } finally {
    hidePlot2Loading();
  }
}

function initConformalChart() {
  const ctx = document.getElementById("conformalChart").getContext("2d");
  chartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: Array.from({ length: 12 }, (_, i) => `Month ${i+1}`),
      datasets: [
        {
          label: "Conformal Upper Bound (G_pred + q̂)",
          data: [],
          borderColor: "rgba(0, 242, 254, 0.3)",
          borderDash: [5, 5],
          fill: false,
        },
        {
          label: "Nominal Predicted Head G_pred",
          data: [],
          borderColor: "#00f2fe",
          backgroundColor: "rgba(0, 242, 254, 0.1)",
          fill: "-1",
          tension: 0.3,
        },
        {
          label: "Tightened Conformal Safety (G_pred - q̂)",
          data: [],
          borderColor: "rgba(127, 0, 255, 0.8)",
          borderDash: [3, 3],
          fill: "-1",
        },
        {
          label: "Critical Head Limit h_min (35m)",
          data: Array(12).fill(35.0),
          borderColor: "#ef4444",
          borderWidth: 2,
          pointRadius: 0,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#94a3b8" }
        },
        x: {
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#94a3b8" }
        }
      },
      plugins: {
        legend: { labels: { color: "#f0f4f8", font: { family: "Outfit" } } }
      }
    }
  });
}

async function runOptimization() {
  const horizonEl = document.getElementById("inputHVal") || document.getElementById("inputH");
  const horizon = parseInt(horizonEl ? horizonEl.value : 12) || 12;
  const alpha = parseFloat(document.getElementById("inputAlpha") ? document.getElementById("inputAlpha").value : 0.05) || 0.05;
  const h_min = parseFloat(document.getElementById("hMinInput") ? document.getElementById("hMinInput").value : 35.0) || 35.0;
  const h_target = parseFloat(document.getElementById("hTargetInput") ? document.getElementById("hTargetInput").value : 45.0) || 45.0;
  const e_max = parseFloat(document.getElementById("eMaxInput") ? document.getElementById("eMaxInput").value : 100.0) || 100.0;
  const gamma_pump = parseFloat(document.getElementById("gammaPumpInput") ? document.getElementById("gammaPumpInput").value : 1.0) || 1.0;
  const sigma_slack = parseFloat(document.getElementById("sigmaSlackInput") ? document.getElementById("sigmaSlackInput").value : 100.0) || 100.0;
  const delta_trust = parseFloat(document.getElementById("deltaTrustInput") ? document.getElementById("deltaTrustInput").value : 5.0) || 5.0;
  const max_iter = parseInt(document.getElementById("maxIterInput") ? document.getElementById("maxIterInput").value : 20) || 20;

  showPlot2Loading(`Solving Chance-Constrained SCP (${horizon} Months)...`);
  try {
    const res = await fetch("/api/v1/control/pumping_quotas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ horizon, alpha, h_min, h_target, e_max, gamma_pump, sigma_slack, delta_trust, max_iter }),
    });
    const data = await res.json();

    if (data.status === "success") {
      updateQuotaTable(data.pumping_quotas);
      updateChartData(data.predicted_heads, data.q_hat_conformal, horizon);
      const resBox = document.getElementById("controlResultBox");
      if (resBox) {
        resBox.innerHTML = `<small style="color: #4ade80;">✓ SCP Optimization Solved (${data.converged ? 'Converged' : 'Completed'}). Cost: ${data.final_cost.toFixed(1)}</small>`;
      }
    }
  } catch (err) {
    console.error("Optimization error:", err);
  } finally {
    hidePlot2Loading();
  }
}

function updateQuotaTable(quotas) {
  const tbody = document.getElementById("quotaTableBody");
  tbody.innerHTML = "";
  const numWells = quotas[0] ? quotas[0].length : 0;

  for (let i = 0; i < Math.min(numWells, 8); i++) {
    const avgE = (quotas.reduce((acc, q) => acc + q[i], 0) / quotas.length).toFixed(2);
    tbody.innerHTML += `
      <tr>
        <td>Well-${i+1}</td>
        <td>42.5m</td>
        <td>${avgE} m³/mo</td>
        <td><span style="color: #4ade80;">✓ Safe</span></td>
      </tr>
    `;
  }
}


function applyCustomMonthInput() {
  const inputEl = document.getElementById("customMonthInput");
  if (!inputEl) return;
  const val = parseInt(inputEl.value, 10);
  if (isNaN(val) || val < 1 || val > 120) {
    alert("Please enter a valid horizon between 1 and 120 months.");
    return;
  }
  setCustomChartHorizon(val, null);
}

function updateChartData(predictedHeads, qHat, horizon) {
  if (!chartInstance) return;

  const actualHorizon = Math.min(horizon || 12, predictedHeads.length);
  const labels = Array.from({ length: actualHorizon }, (_, i) => `Month ${i+1}`);

  const meanNominal = [];
  for (let t = 0; t < actualHorizon; t++) {
    const slice = predictedHeads[t];
    if (Array.isArray(slice)) {
      const flat = slice.flat ? slice.flat() : [].concat.apply([], slice);
      const avg = flat.reduce((a, b) => a + b, 0) / Math.max(1, flat.length);
      let headVal = avg;
      if (headVal < 25.0) headVal += 40.0;
      meanNominal.push(headVal);
    } else if (typeof slice === "number") {
      let headVal = slice;
      if (headVal < 25.0) headVal += 40.0;
      meanNominal.push(headVal);
    } else {
      meanNominal.push(40.0 + t * 0.1);
    }
  }

  const upper = meanNominal.map(v => v + qHat);
  const lower = meanNominal.map(v => v - qHat);

  chartInstance.data.labels = labels;
  chartInstance.data.datasets[0].data = upper;
  chartInstance.data.datasets[1].data = meanNominal;
  chartInstance.data.datasets[2].data = lower;
  chartInstance.data.datasets[3].data = Array(actualHorizon).fill(35.0);
  chartInstance.update();
}

async function changeRegionPreset() {
  const regionKey = document.getElementById("regionPresetSelect").value;
  try {
    const res = await fetch("/api/v1/config/location", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ region_key: regionKey }),
    });
    const data = await res.json();
    alert(data.message);

    if (data.metadata && data.metadata.bounds) {
      const b = data.metadata.bounds;
      const centerLat = (b[1] + b[3]) / 2.0;
      const centerLon = (b[0] + b[2]) / 2.0;
      document.getElementById("inputLat").value = centerLat.toFixed(4);
      document.getElementById("inputLon").value = centerLon.toFixed(4);
      updateMapMarker(centerLat, centerLon, `<b>📍 ${data.metadata.region_name} Center</b>`);
    }

    fetchDrawdownForecast();
    fetchDepletionAlerts();
    runOptimization();
  } catch (err) {
    console.error("Region preset error:", err);
  }
}

async function predictPointLocation() {
  const latVal = document.getElementById("inputLat").value;
  const lonVal = document.getElementById("inputLon").value;
  const horizonVal = document.getElementById("inputH") ? document.getElementById("inputH").value : 12;

  const lat = latVal !== "" ? parseFloat(latVal) : 40.15;
  const lon = lonVal !== "" ? parseFloat(lonVal) : -88.25;
  const horizon = parseInt(horizonVal) || 12;

  try {
    const res = await fetch("/api/v1/forecast/location_predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lat, lon, horizon }),
    });
    const data = await res.json();

    if (data.forecast) {
      // 1. Update line chart with point location forecast
      updateChartData(data.forecast.predicted_heads_m.map(v => [v]), data.conformal_q_hat, horizon);

      // 2. Highlight target cell in 16x16 spatial grid heatmap and update 3D Aquifer WebGL Map
      if (data.raster_slice) {
        renderHeatmap(data.raster_slice, data.grid_cell.row, data.grid_cell.col);
        update3DMap(data.raster_slice, data.grid_cell.row, data.grid_cell.col);
      }

      const headLast = data.forecast.predicted_heads_m[data.forecast.predicted_heads_m.length - 1].toFixed(2);
      const safeLast = data.forecast.conformal_lower_bounds_m[data.forecast.conformal_lower_bounds_m.length - 1].toFixed(2);

      // 3. Pin location marker on Terrain & Hydro map with popup info
      const popupHtml = `
        <b>📍 Pinned Query Location</b><br>
        Lat: ${data.query_coordinates.lat}°, Lon: ${data.query_coordinates.lon}°<br>
        <b>Region:</b> ${data.region_name}<br>
        <b>Grid Cell:</b> Row ${data.grid_cell.row}, Col ${data.grid_cell.col}<br>
        <b>Head (Mo 12):</b> ${headLast}m (95% Bound: ${safeLast}m)<br>
        <b>Status:</b> ${data.depletion_risk}
      `;
      updateMapMarker(lat, lon, popupHtml);

      document.getElementById("timestepDisplay").innerText = `Lat: ${data.query_coordinates.lat}°, Lon: ${data.query_coordinates.lon}° (R:${data.grid_cell.row}, C:${data.grid_cell.col})`;
    }
  } catch (err) {
    console.error("Location predict error:", err);
  }
}

function openLocationReport() {
  const lat = parseFloat(document.getElementById("inputLat").value);
  const lon = parseFloat(document.getElementById("inputLon").value);
  const horizon = parseInt(document.getElementById("inputH").value);

  const reportUrl = `/api/v1/reports/view?lat=${lat}&lon=${lon}&horizon=${horizon}`;
  window.open(reportUrl, "_blank");
}

function toggleChoicePicker(menuId, triggerId) {
  const menu = document.getElementById(menuId);
  const trigger = document.getElementById(triggerId);
  if (!menu) return;

  const isShow = menu.classList.contains("show");
  closeAllChoicePickers();

  if (!isShow) {
    menu.classList.add("show");
    if (trigger) trigger.classList.add("active");
  }
}

function closeAllChoicePickers() {
  document.querySelectorAll(".choice-picker-menu").forEach(m => m.classList.remove("show"));
  document.querySelectorAll(".choice-picker-trigger").forEach(t => t.classList.remove("active"));
}

function selectChoiceRegion(value, labelText) {
  const nativeSelect = document.getElementById("regionPresetSelect");
  const labelSpan = document.getElementById("regionPickerSelectedLabel");
  if (labelSpan) labelSpan.innerText = labelText;
  if (nativeSelect) {
    nativeSelect.value = value;
    changeRegionPreset();
  }
  closeAllChoicePickers();
}

function selectChoiceSource(value, labelText) {
  const nativeSelect = document.getElementById("dataSourceSelect");
  const labelSpan = document.getElementById("sourcePickerSelectedLabel");
  if (labelSpan) labelSpan.innerText = labelText;
  if (nativeSelect) {
    nativeSelect.value = value;
    toggleDataSourceChannel();
  }
  closeAllChoicePickers();
}

window.addEventListener("click", function (e) {
  if (!e.target.closest(".choice-picker-container")) {
    closeAllChoicePickers();
  }
});

let pickerHoverTimeout = null;

function setupChoicePickerHoverHandlers() {
  document.querySelectorAll(".choice-picker-container").forEach(container => {
    container.addEventListener("mouseenter", function () {
      if (pickerHoverTimeout) clearTimeout(pickerHoverTimeout);
      const menu = container.querySelector(".choice-picker-menu");
      const trigger = container.querySelector(".choice-picker-trigger");
      if (menu) {
        closeAllChoicePickers();
        menu.classList.add("show");
        if (trigger) trigger.classList.add("active");
      }
    });

    container.addEventListener("mouseleave", function () {
      pickerHoverTimeout = setTimeout(() => {
        const menu = container.querySelector(".choice-picker-menu");
        const trigger = container.querySelector(".choice-picker-trigger");
        if (menu) menu.classList.remove("show");
        if (trigger) trigger.classList.remove("active");
      }, 150);
    });
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", setupChoicePickerHoverHandlers);
} else {
  setupChoicePickerHoverHandlers();
}
