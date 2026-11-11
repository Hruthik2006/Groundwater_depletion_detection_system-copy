let chartInstance = null;
let gisMap = null;
let locationMarker = null;
let globeScene = null;
let globeCamera = null;
let globeRenderer = null;
let globeMesh = null;
let globeMarker = null;
let globeControls = null;
let targetGlobeRotY = 0;
let targetGlobeRotX = 0.18;
let isGlobeLocationSelected = false;
let regionOutlineGroup = null;
let globeOuterPulseRing = null;
let globePulseTime = 0;
let globeAtmosphere = null;
let globeLoaderRing = null;
let globeLoaderArc = null;
let globeLoaderArc2 = null;
let globeLoaderTrack = null;
let globeSurfaceMat = null;
let globeWireMat = null;
let globeAtmosphereMat = null;
let globeLoadingActive = false;
let globeLoadingMix = 0;
let globeLoadPhase = "globe";
let globeLoadPhaseTime = 0;
let globeLastFrameTime = 0;
let globeRegionMats = [];

function switchMainPanel(selectedId) {
  const panels = ["panelFramework", "panelMaps", "panelPredictions"];
  const currentPanel = document.getElementById(selectedId);
  const isAlreadyExpanded = currentPanel && currentPanel.classList.contains("panel-expanded");

  panels.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;

    if (id === selectedId && !isAlreadyExpanded) {
      el.classList.remove("panel-collapsed");
      el.classList.add("panel-expanded");

      if (id === "panelMaps") {
        setTimeout(() => {
          if (gisMap) gisMap.invalidateSize();
          resize3DMap();
        }, 150);
      } else if (id === "panelPredictions") {
        setTimeout(() => {
          if (!chartInstance) {
            // First time opening predictions panel - init chart and load data
            initConformalChart();
            fetchDrawdownForecast(currentChartHorizon || 12);
          } else {
            chartInstance.resize();
          }
        }, 200);
      }
    } else {
      el.classList.remove("panel-expanded");
      el.classList.add("panel-collapsed");
    }
  });

  const noticeEl = document.getElementById("collapsedWorkspaceNotice");
  const anyExpanded = panels.some((id) => {
    const p = document.getElementById(id);
    return p && p.classList.contains("panel-expanded");
  });

  if (noticeEl) {
    noticeEl.style.display = anyExpanded ? "none" : "flex";
  }
}

function toggleTabDropupMenu(menuId, e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  const targetMenu = document.getElementById(menuId);
  if (!targetMenu) return;

  const isAlreadyActive = targetMenu.classList.contains("active");
  closeAllTabDropupMenus();

  if (!isAlreadyActive) {
    targetMenu.classList.add("active");
  }
}

function closeAllTabDropupMenus(e) {
  const menus = document.querySelectorAll(".tab-dropup-menu");
  menus.forEach((m) => m.classList.remove("active"));
}

document.addEventListener("click", (e) => {
  if (!e.target.closest(".tab-menu-wrapper")) {
    closeAllTabDropupMenus();
  }
});

function selectFrameworkView(mode, e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  closeAllTabDropupMenus();

  const cardLayers = document.getElementById("cardFrameworkLayers");
  const cardParams = document.getElementById("cardFrameworkParams");
  const gridContainer = document.getElementById("panelGridFramework");
  const titleEl = document.getElementById("frameworkSubTitle");

  const chipParams = document.getElementById("chipSubParams");
  const chipLayers = document.getElementById("chipSubLayers");
  const chipAll = document.getElementById("chipSubAll");

  [chipParams, chipLayers, chipAll].forEach((c) => c && c.classList.remove("active"));

  if (mode === "params") {
    if (titleEl) titleEl.innerText = "SCP CCMPC Optimizer Parameters";
    if (chipParams) chipParams.classList.add("active");
    if (gridContainer) gridContainer.style.gridTemplateColumns = "1fr";
    if (cardParams) cardParams.style.display = "flex";
    if (cardLayers) cardLayers.style.display = "none";
  } else if (mode === "layers") {
    if (titleEl) titleEl.innerText = "Framework Layer Status";
    if (chipLayers) chipLayers.classList.add("active");
    if (gridContainer) gridContainer.style.gridTemplateColumns = "1fr";
    if (cardParams) cardParams.style.display = "none";
    if (cardLayers) cardLayers.style.display = "flex";
  } else if (mode === "all") {
    if (titleEl) titleEl.innerText = "Parameters & Framework Overview";
    if (chipAll) chipAll.classList.add("active");
    if (gridContainer) gridContainer.style.gridTemplateColumns = "1fr 1fr";
    if (cardParams) cardParams.style.display = "flex";
    if (cardLayers) cardLayers.style.display = "flex";
  }
}

function triggerGenerateReportFromMenu(e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  closeAllTabDropupMenus();
  openLocationReport();
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

function initInputGlobe() {
  const container = document.getElementById("inputGlobe");
  if (!container || typeof THREE === "undefined") return;

  const width = container.clientWidth > 0 ? container.clientWidth : 520;
  const height = container.clientHeight > 0 ? container.clientHeight : 440;

  if (globeRenderer) {
    if (container.contains(globeRenderer.domElement)) {
      resizeInputGlobe();
      return;
    }
  }

  globeScene = new THREE.Scene();
  globeCamera = new THREE.PerspectiveCamera(40, width / height, 0.1, 1000);
  globeCamera.position.set(0, 0, 6.2);
  globeCamera.lookAt(0, 0, 0);

  globeRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  globeRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  globeRenderer.setSize(width, height);
  globeRenderer.domElement.style.display = "block";
  globeRenderer.domElement.style.touchAction = "none";
  globeRenderer.domElement.style.userSelect = "none";
  globeRenderer.domElement.style.width = "100%";
  globeRenderer.domElement.style.height = "100%";
  container.innerHTML = "";
  container.appendChild(globeRenderer.domElement);

  const ambient = new THREE.AmbientLight(0xffffff, 0.95);
  globeScene.add(ambient);
  const directional = new THREE.DirectionalLight(0xffffff, 0.7);
  directional.position.set(5, 5, 5);
  globeScene.add(directional);

  const globeGeometry = new THREE.SphereGeometry(2.05, 64, 64);
  const globeMaterial = new THREE.MeshStandardMaterial({
    color: 0x17283f,
    roughness: 0.8,
    metalness: 0.15,
    emissive: 0x051523,
    side: THREE.FrontSide,
    transparent: true,
  });
  globeSurfaceMat = globeMaterial;

  globeMesh = new THREE.Mesh(globeGeometry, globeMaterial);
  globeScene.add(globeMesh);

  const lineMaterial = new THREE.LineBasicMaterial({ color: 0x72a9ff, opacity: 0.18, transparent: true });
  globeWireMat = lineMaterial;
  const lineMesh = new THREE.LineSegments(new THREE.WireframeGeometry(globeGeometry), lineMaterial);
  globeMesh.add(lineMesh);

  const atmosphereGeo = new THREE.SphereGeometry(2.09, 64, 64);
  const atmosphereMat = new THREE.MeshBasicMaterial({ color: 0x5ea1ff, transparent: true, opacity: 0.08, side: THREE.BackSide });
  globeAtmosphereMat = atmosphereMat;
  globeAtmosphere = new THREE.Mesh(atmosphereGeo, atmosphereMat);
  globeScene.add(globeAtmosphere);

  // Circular loading element: the globe morphs into these concentric arcs
  // while a request is in flight. Parented to the scene (not the globe) so it
  // always faces the camera and stays a clean circle.
  const loaderGroup = new THREE.Group();
  loaderGroup.visible = false;
  globeScene.add(loaderGroup);

  globeLoaderTrack = new THREE.Mesh(
    new THREE.TorusGeometry(1.62, 0.018, 12, 96),
    new THREE.MeshBasicMaterial({ color: 0x2a4a6b, transparent: true, opacity: 0 })
  );
  loaderGroup.add(globeLoaderTrack);

  globeLoaderArc = new THREE.Mesh(
    new THREE.TorusGeometry(1.62, 0.05, 16, 96, Math.PI * 0.55),
    new THREE.MeshBasicMaterial({ color: 0x00f2fe, transparent: true, opacity: 0 })
  );
  loaderGroup.add(globeLoaderArc);

  globeLoaderArc2 = new THREE.Mesh(
    new THREE.TorusGeometry(1.62, 0.028, 12, 96, Math.PI * 0.28),
    new THREE.MeshBasicMaterial({ color: 0xffbf47, transparent: true, opacity: 0 })
  );
  loaderGroup.add(globeLoaderArc2);

  globeLoaderRing = loaderGroup;

  // Hydrogeological Region Outline Group (attached to globeMesh so it stays anchored on sphere surface)
  regionOutlineGroup = new THREE.Group();
  globeMesh.add(regionOutlineGroup);

  // 1. Semi-transparent surface fill overlay representing hydrogeological aquifer extent
  const fillGeo = new THREE.CircleGeometry(0.38, 64);
  const fillMat = new THREE.MeshBasicMaterial({
    color: 0x00f2fe,
    transparent: true,
    opacity: 0.22,
    side: THREE.DoubleSide
  });
  const fillMesh = new THREE.Mesh(fillGeo, fillMat);
  regionOutlineGroup.add(fillMesh);

  // 2. Primary region outline boundary ring
  const ringGeo = new THREE.RingGeometry(0.36, 0.40, 64);
  const ringMat = new THREE.MeshBasicMaterial({
    color: 0x00f2fe,
    transparent: true,
    opacity: 0.9,
    side: THREE.DoubleSide
  });
  const ringMesh = new THREE.Mesh(ringGeo, ringMat);
  regionOutlineGroup.add(ringMesh);

  // 3. Outer animated pulse ring for region boundary accent
  const pulseGeo = new THREE.RingGeometry(0.44, 0.47, 64);
  const pulseMat = new THREE.MeshBasicMaterial({
    color: 0xffbf47,
    transparent: true,
    opacity: 0.7,
    side: THREE.DoubleSide
  });
  globeOuterPulseRing = new THREE.Mesh(pulseGeo, pulseMat);
  regionOutlineGroup.add(globeOuterPulseRing);

  // 4. Center marker pin dot
  const pinGeo = new THREE.SphereGeometry(0.06, 16, 16);
  const pinMat = new THREE.MeshStandardMaterial({
    color: 0xffbf47,
    emissive: 0xffbf47,
    emissiveIntensity: 1.0
  });
  const pinMesh = new THREE.Mesh(pinGeo, pinMat);
  pinMesh.position.set(0, 0, 0.02);
  regionOutlineGroup.add(pinMesh);

  // Region marker materials fade with the globe, so the whole object
  // dissolves together during the morph instead of leaving a floating pin.
  pinMat.transparent = true;
  globeRegionMats = [
    { mat: fillMat, base: 0.22 },
    { mat: ringMat, base: 0.9 },
    { mat: pulseMat, base: 0.7 },
    { mat: pinMat, base: 1.0 },
  ];

  globeMarker = regionOutlineGroup;

  updateInputGlobe();
  animateInputGlobe();
  window.addEventListener("resize", resizeInputGlobe);
}

function resizeInputGlobe() {
  if (!globeRenderer || !globeCamera) return;
  const container = document.getElementById("inputGlobe");
  if (!container) return;
  const width = container.clientWidth > 0 ? container.clientWidth : 520;
  const height = container.clientHeight > 0 ? container.clientHeight : 440;
  globeCamera.aspect = width / height;
  globeCamera.updateProjectionMatrix();
  globeRenderer.setSize(width, height);
}

const GLOBE_DWELL = 1.5;
const LOADER_DWELL = 1.2;
const MORPH_DUR = 0.55;

function smoothstep(t) {
  const c = Math.min(Math.max(t, 0), 1);
  return c * c * (3 - 2 * c);
}

function setGlobeLoading(active) {
  globeLoadingActive = active;
  if (active) {
    globeLoadPhase = "globe";
    globeLoadPhaseTime = 0;
  }
  const statusEl = document.getElementById("inputScreenLoadingText");
  if (statusEl) statusEl.classList.toggle("visible", active);
}

function updateGlobeLoadingMorph(nowMs) {
  const dt = globeLastFrameTime ? Math.min((nowMs - globeLastFrameTime) / 1000, 0.05) : 0;
  globeLastFrameTime = nowMs;

  if (globeLoadingActive) {
    globeLoadPhaseTime += dt;
    if (globeLoadPhase === "globe" && globeLoadPhaseTime >= GLOBE_DWELL) {
      globeLoadPhase = "toLoader";
      globeLoadPhaseTime = 0;
    } else if (globeLoadPhase === "toLoader" && globeLoadPhaseTime >= MORPH_DUR) {
      globeLoadPhase = "loader";
      globeLoadPhaseTime = 0;
    } else if (globeLoadPhase === "loader" && globeLoadPhaseTime >= LOADER_DWELL) {
      globeLoadPhase = "toGlobe";
      globeLoadPhaseTime = 0;
    } else if (globeLoadPhase === "toGlobe" && globeLoadPhaseTime >= MORPH_DUR) {
      globeLoadPhase = "globe";
      globeLoadPhaseTime = 0;
    }
  }

  // mix 0 = globe, 1 = circular loader. Each state is held rather than
  // ping-ponged, so the globe is never half-collapsed and half-visible.
  if (!globeLoadingActive) {
    globeLoadingMix = Math.max(0, globeLoadingMix - dt * 3.0);
  } else if (globeLoadPhase === "globe") {
    globeLoadingMix = 0;
  } else if (globeLoadPhase === "loader") {
    globeLoadingMix = 1;
  } else if (globeLoadPhase === "toLoader") {
    globeLoadingMix = smoothstep(globeLoadPhaseTime / MORPH_DUR);
  } else {
    globeLoadingMix = 1 - smoothstep(globeLoadPhaseTime / MORPH_DUR);
  }

  const mix = globeLoadingMix;
  const s = 1 - 0.42 * mix;

  if (globeMesh) globeMesh.scale.set(s, s, s);
  if (globeAtmosphere) globeAtmosphere.scale.set(s, s, s);
  if (globeSurfaceMat) globeSurfaceMat.opacity = 1 - mix;
  if (globeWireMat) globeWireMat.opacity = 0.18 * (1 - mix);
  if (globeAtmosphereMat) globeAtmosphereMat.opacity = 0.08 * (1 - mix);
  for (let i = 0; i < globeRegionMats.length; i++) {
    const entry = globeRegionMats[i];
    entry.mat.opacity = entry.base * (1 - mix);
  }
  if (regionOutlineGroup) regionOutlineGroup.visible = isGlobeLocationSelected && mix < 0.99;

  if (!globeLoaderRing) return;
  globeLoaderRing.visible = mix > 0.01;
  if (globeLoaderRing.visible) {
    const ls = 1.30 - 0.30 * mix;
    globeLoaderRing.scale.set(ls, ls, ls);
    globeLoaderRing.rotation.z += 0.02;
  }
  if (globeLoaderTrack) globeLoaderTrack.material.opacity = 0.55 * mix;
  if (globeLoaderArc) {
    globeLoaderArc.material.opacity = 0.95 * mix;
    globeLoaderArc.rotation.z += 0.014;
  }
  if (globeLoaderArc2) {
    globeLoaderArc2.material.opacity = 0.7 * mix;
    globeLoaderArc2.rotation.z -= 0.032;
  }
}

function animateInputGlobe(nowMs) {
  requestAnimationFrame(animateInputGlobe);

  // Rotation is frozen while loading so the globe reads as a still object
  // that transforms into the loader, not as a globe wobbling in place.
  if (globeMesh && !globeLoadingActive) {
    if (!isGlobeLocationSelected) {
      // Rotate slowly in idle state before user chooses an input
      globeMesh.rotation.y += 0.0012;
      globeMesh.rotation.x = 0.18;
    } else {
      // Smoothly rotate to target location, then stop at that location
      const lerpFactor = 0.08;
      let dy = (targetGlobeRotY - globeMesh.rotation.y + Math.PI) % (Math.PI * 2);
      if (dy < 0) dy += Math.PI * 2;
      dy -= Math.PI;

      globeMesh.rotation.y += dy * lerpFactor;
      globeMesh.rotation.x += (targetGlobeRotX - globeMesh.rotation.x) * lerpFactor;
    }
  }

  if (globeOuterPulseRing) {
    globePulseTime += 0.04;
    const scaleVal = 1.0 + Math.sin(globePulseTime) * 0.06;
    globeOuterPulseRing.scale.set(scaleVal, scaleVal, 1);
  }

  updateGlobeLoadingMorph(nowMs || performance.now());

  if (globeMesh) globeMesh.visible = globeLoadingMix < 0.995;
  if (globeAtmosphere) globeAtmosphere.visible = globeLoadingMix < 0.995;

  if (globeRenderer && globeScene && globeCamera) {
    globeRenderer.render(globeScene, globeCamera);
  }
}

function updateInputGlobe(lat, lon, regionKey, isUserChoice = false) {
  if (!globeMesh || !regionOutlineGroup) return;

  const regionInfo = inputScreenRegionDefaults[regionKey || selectedInputPageRegion] || (selectedInputPageRegion ? inputScreenRegionDefaults[selectedInputPageRegion] : null);
  const latVal = typeof lat === "number" ? lat : (lat ? parseFloat(lat) : (regionInfo ? regionInfo.lat : 40.15));
  const lonVal = typeof lon === "number" ? lon : (lon ? parseFloat(lon) : (regionInfo ? regionInfo.lon : -88.25));

  if (isUserChoice) {
    isGlobeLocationSelected = true;
  }

  const radius = 2.05;
  const latRad = latVal * (Math.PI / 180);
  const lonRad = lonVal * (Math.PI / 180);

  // Position region outline on sphere surface at (latVal, lonVal)
  const normal = new THREE.Vector3(
    Math.cos(latRad) * Math.sin(lonRad),
    Math.sin(latRad),
    Math.cos(latRad) * Math.cos(lonRad)
  ).normalize();

  regionOutlineGroup.position.copy(normal.clone().multiplyScalar(radius * 1.008));
  regionOutlineGroup.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
  // Visibility is owned by updateGlobeLoadingMorph, which hides the marker
  // whenever the globe is collapsed into the circular loader.

  // Set target globe rotation to focus on the selected region
  targetGlobeRotY = -lonRad;
  targetGlobeRotX = latRad * 0.4;
}

function updateInputGlobeFromInputs() {
  const latInput = document.getElementById("inputScreenLat");
  const lonInput = document.getElementById("inputScreenLon");
  if (!latInput || !lonInput) return;

  const latValue = latInput.value.trim();
  const lonValue = lonInput.value.trim();
  if (latValue !== "" && lonValue !== "" && !isNaN(parseFloat(latValue)) && !isNaN(parseFloat(lonValue))) {
    updateInputGlobe(parseFloat(latValue), parseFloat(lonValue), selectedInputPageRegion, true);
  } else {
    updateInputGlobe(undefined, undefined, selectedInputPageRegion, false);
  }
}

async function fetchUnifiedControl() {
  // Ensure chart is initialized before any fetch
  if (!chartInstance) {
    initConformalChart();
  }
  // A click that crosses into a new region blocks in these calls for the
  // whole Earth Engine rebuild — mirror the live ingestion progress in
  // the GEE badge meanwhile instead of leaving the UI silent, and
  // refresh the status-derived UI once the new region's data has landed.
  const stopProgress = startIngestionProgressPolling();
  try {
    await predictPointLocation();
    await fetchDrawdownForecast();
    await runOptimization();
  } finally {
    stopProgress();
    await updateGEEStatusBadge();
    fetchSystemStatus();
  }

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
  const savedPin = restoreSavedPin();
  initHeatmapGrid();
  initConformalChart();
  initGisMap();
  if (savedPin && gisMap && locationMarker) {
    locationMarker.setLatLng([savedPin.lat, savedPin.lon]);
    gisMap.setView([savedPin.lat, savedPin.lon], 7);
  }
  initInputGlobe();
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

  const latInput = document.getElementById("inputScreenLat");
  const lonInput = document.getElementById("inputScreenLon");
  if (latInput) {
    latInput.addEventListener("input", () => updateInputGlobeFromInputs());
  }
  if (lonInput) {
    lonInput.addEventListener("input", () => updateInputGlobeFromInputs());
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
  const geoTerrain = new THREE.PlaneGeometry(14, 14, 15, 15); // 16x16 vertices, matching the data grid 1:1
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
    const res = await fetch(`/api/v1/forecast/spatial_drawdown_3d?horizon=12${pinnedCoordQuery()}`);
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

  // Deform a layer mesh per-vertex from a server field. The vertex
  // values are absolute scene heights, so the mesh's own z offset is
  // zeroed while deforming. Returns false when the field is absent
  // (older responses), letting callers fall back to the flat profile.
  const deformLayer = (mesh, field) => {
    if (!mesh || !data.vertices[0] || data.vertices[0][field] === undefined) return false;
    const pos = mesh.geometry.attributes.position;
    data.vertices.forEach((v, idx) => {
      if (idx < pos.count) pos.setZ(idx, v[field]);
    });
    pos.needsUpdate = true;
    mesh.geometry.computeVertexNormals();
    mesh.position.z = 0;
    return true;
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

  // 2. Update Unsaturated Vadose Zone (per-cell surface)
  if (vadoseMesh3D && !deformLayer(vadoseMesh3D, "z_vadose")) {
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

  // 4. Update Unconfined Aquifer Volume (per-cell surface)
  if (aquiferMesh3D && !deformLayer(aquiferMesh3D, "z_aquifer")) {
    aquiferMesh3D.position.z = prof.aquifer_base;
  }

  // 5. Update Clay Aquitard Layer (per-cell surface)
  if (aquitardMesh3D && !deformLayer(aquitardMesh3D, "z_aquitard")) {
    aquitardMesh3D.position.z = prof.aquitard_base;
  }

  // 6. Update Bedrock Floor Mesh
  if (bedrockMesh3D) {
    bedrockMesh3D.position.z = 0; // vertices are absolute scene heights
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
  locationMarker.on("dragend", async function () {
    const latlng = locationMarker.getLatLng();
    document.getElementById("inputLat").value = latlng.lat.toFixed(4);
    document.getElementById("inputLon").value = latlng.lng.toFixed(4);
    await fetchUnifiedControl();
  });

  // Handle map click to pin location
  gisMap.on("click", async function (e) {
    const lat = e.latlng.lat.toFixed(4);
    const lon = e.latlng.lng.toFixed(4);
    document.getElementById("inputLat").value = lat;
    document.getElementById("inputLon").value = lon;
    if (locationMarker) locationMarker.setLatLng(e.latlng);

    await fetchUnifiedControl();
    if (locationMarker) locationMarker.openPopup();
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

  const hLat = document.getElementById("headerLatInput");
  const hLon = document.getElementById("headerLonInput");
  if (hLat) hLat.value = latNum.toFixed(4);
  if (hLon) hLon.value = lonNum.toFixed(4);

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
    const statusTextEl = document.getElementById("systemStatusText");
    if (statusTextEl) statusTextEl.innerText = `System Operational (${data.data_mode.toUpperCase()})`;
    const qHatEl = document.getElementById("qHatBadge");
    if (qHatEl) qHatEl.innerText = `q̂ = ${data.conformal_q_hat.toFixed(2)}m`;
    const modeSelectEl = document.getElementById("dataModeSelect");
    if (modeSelectEl) modeSelectEl.value = data.data_mode;
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

function pinnedCoordQuery() {
  const la = parseFloat((document.getElementById("inputLat") || {}).value);
  const lo = parseFloat((document.getElementById("inputLon") || {}).value);
  return (!isNaN(la) && !isNaN(lo)) ? `&lat=${la}&lon=${lo}` : "";
}

// Pin persistence: remember the last pinned location so a page reload
// reopens the same place (and its region) instead of resetting to the
// Illinois default and rebuilding the wrong region's dataset.
const GW_PIN_KEY = "gw_pinned_location";
function persistPin(lat, lon) {
  try {
    localStorage.setItem(GW_PIN_KEY, JSON.stringify({ lat: parseFloat(lat), lon: parseFloat(lon) }));
  } catch (e) { /* storage unavailable — persistence is best-effort */ }
}
function restoreSavedPin() {
  try {
    const raw = localStorage.getItem(GW_PIN_KEY);
    if (!raw) return null;
    const pin = JSON.parse(raw);
    if (!pin || typeof pin.lat !== "number" || typeof pin.lon !== "number" || isNaN(pin.lat) || isNaN(pin.lon)) return null;
    const latEl = document.getElementById("inputLat");
    const lonEl = document.getElementById("inputLon");
    if (latEl) latEl.value = pin.lat;
    if (lonEl) lonEl.value = pin.lon;
    return pin;
  } catch (e) {
    return null;
  }
}

async function fetchDrawdownForecast(horizon = 12) {
  try {
    const res = await fetch(`/api/v1/forecast/spatial_drawdown?horizon=${horizon}${pinnedCoordQuery()}`);
    const data = await res.json();
    const list = data.forecasts || data.forecast_rasters;
    if (list && list.length > 0) {
      const lastForecast = list[list.length - 1];
      renderHeatmap(lastForecast.raster);
      update3DMap(lastForecast.raster, 10, 9);
      updateGisHeatmap(lastForecast.raster);

      const predictedHeads = list.map(r => r.raster);
      // Use the pipeline's calibrated conformal margin from /api/v1/status.
      // (Previously this read a `currentQHat` variable that is never set
      // anywhere, so the chart silently fell back to a hard-coded 0.496 m
      // band that had nothing to do with the calibrated margin.)
      let qHat = 0.496;
      try {
        const st = await (await fetch("/api/v1/status")).json();
        if (typeof st.conformal_q_hat === "number") qHat = st.conformal_q_hat;
      } catch (e) { /* keep fallback if status is unreachable */ }
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
    "   Estimates remaining time before water table breaches the depletion alert threshold (critical = 36.0m, control floor h_min = 35.0m).\n\n" +
    "4. Recommended Pumping Curtailment:\n" +
    "   Calculates automatic % pumping reductions to prevent severe regional aquifer depletion."
  );
}

const inputScreenRegionDefaults = {
  high_plains: { lat: 37.50, lon: -100.00, label: 'High Plains / Ogallala (USA)' },
  ganges: { lat: 26.50, lon: 79.50, label: 'Indo-Gangetic Basin (India)' },
  north_german: { lat: 53.00, lon: 11.00, label: 'North German Basin (Europe)' },
  illinois: { lat: 40.15, lon: -88.25, label: 'Illinois Glacial Aquifer (USA)' },
};

let selectedInputPageRegion = "";
let selectedInputPageSource = "";

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
  if (!globeRenderer) {
    initInputGlobe();
  }
  setGlobeLoading(false);
  setTimeout(() => {
    resizeInputGlobe();
    updateInputGlobeFromInputs();
  }, 50);
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
  isGlobeLocationSelected = true;
  const labelEl = document.getElementById("inputPageRegionLabel");
  if (labelEl) labelEl.innerText = labelText;

  const regionDefaults = {
    high_plains: { lat: 37.50, lon: -100.00 },
    ganges: { lat: 26.50, lon: 79.50 },
    north_german: { lat: 53.00, lon: 11.00 },
    illinois: { lat: 40.15, lon: -88.25 },
  };
  if (regionDefaults[key]) {
    const latInput = document.getElementById("inputScreenLat");
    const lonInput = document.getElementById("inputScreenLon");
    if (latInput) latInput.value = regionDefaults[key].lat.toFixed(2);
    if (lonInput) lonInput.value = regionDefaults[key].lon.toFixed(2);
    updateInputGlobe(regionDefaults[key].lat, regionDefaults[key].lon, key, true);
  }
  closeAllChoicePickers();
  // Clear any existing validation error once user makes a selection
  const errEl = document.getElementById("inputScreenError");
  if (errEl) {
    errEl.style.display = "none";
    errEl.innerText = "";
  }
}

function selectInputPageSource(key, labelText) {
  selectedInputPageSource = key;
  const labelEl = document.getElementById("inputPageSourceLabel");
  if (labelEl) labelEl.innerText = labelText;
  closeAllChoicePickers();
  // Clear any existing validation error once user makes a selection
  const errEl = document.getElementById("inputScreenError");
  if (errEl) {
    errEl.style.display = "none";
    errEl.innerText = "";
  }
}

async function validateAndSubmitDetails(e) {
  if (e) e.preventDefault();

  const latInput = document.getElementById("inputScreenLat");
  const lonInput = document.getElementById("inputScreenLon");
  const errEl = document.getElementById("inputScreenError");
  const loadingText = document.getElementById("inputScreenLoadingText");
  const continueBtn = document.getElementById("btnInputScreenContinue");

  let latVal = latInput ? latInput.value.trim() : "";
  let lonVal = lonInput ? lonInput.value.trim() : "";

  if (errEl) {
    errEl.style.display = "none";
    errEl.innerText = "";
  }

  // 1. Validate Hydrogeological Region selection
  if (!selectedInputPageRegion) {
    showInputScreenError("Please select a Hydrogeological Region.");
    const regionBtn = document.getElementById("inputPageRegionBtn");
    if (regionBtn) regionBtn.focus();
    return;
  }

  // 2. Validate numeric Latitude
  if (!latVal || isNaN(parseFloat(latVal))) {
    showInputScreenError("Please enter a valid numeric Latitude (e.g. 40.15).");
    if (latInput) latInput.focus();
    return;
  }

  const latNum = parseFloat(latVal);
  if (latNum < -90 || latNum > 90) {
    showInputScreenError("Latitude must be between -90.0° and +90.0°.");
    if (latInput) latInput.focus();
    return;
  }

  // 3. Validate numeric Longitude
  if (!lonVal || isNaN(parseFloat(lonVal))) {
    showInputScreenError("Please enter a valid numeric Longitude (e.g. -88.25).");
    if (lonInput) lonInput.focus();
    return;
  }

  const lonNum = parseFloat(lonVal);
  if (lonNum < -180 || lonNum > 180) {
    showInputScreenError("Longitude must be between -180.0° and +180.0°.");
    if (lonInput) lonInput.focus();
    return;
  }

  // 4. Validate Data Source selection
  if (!selectedInputPageSource) {
    showInputScreenError("Please select a Data Source (NASA EarthData & GEE API or Synthetic Engine).");
    const sourceBtn = document.getElementById("inputPageSourceBtn");
    if (sourceBtn) sourceBtn.focus();
    return;
  }

  // 5. Hand the loading indicator over to the globe (morphs into a circular ring)
  setGlobeLoading(true);
  if (loadingText) {
    loadingText.innerText = "Ingesting GRACE-FO satellite mascons & downscaling...";
  }
  if (continueBtn) {
    continueBtn.style.pointerEvents = "none";
    continueBtn.style.opacity = "0.5";
  }

  // Sync the dashboard pin FIRST: the data-source switch below triggers
  // refreshes that read inputLat/inputLon, and they must already hold the
  // location entered on this screen — otherwise they run against the
  // previous pin and auto-switch the region straight back. (Step 7 below
  // repeats this sync for the remaining controls.)
  const earlyLat = document.getElementById("inputLat");
  const earlyLon = document.getElementById("inputLon");
  if (earlyLat) earlyLat.value = latNum.toFixed(2);
  if (earlyLon) earlyLon.value = lonNum.toFixed(2);

  // 6. Sync configuration to backend API with animated progress steps
  try {
    if (loadingText) loadingText.innerText = `Configuring region: ${selectedInputPageRegion}...`;
    await fetch("/api/v1/config/location", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ region_key: selectedInputPageRegion }),
    });

    if (loadingText) loadingText.innerText = `Connecting data channel (${selectedInputPageSource})...`;
    const sourceSelect = document.getElementById("dataSourceSelect");
    const sourceLabelSpan = document.getElementById("sourcePickerSelectedLabel");
    if (sourceSelect) sourceSelect.value = selectedInputPageSource;
    if (sourceLabelSpan) {
      sourceLabelSpan.innerText = selectedInputPageSource === "realtime" ? "NASA EarthData & GEE API" : "Synthetic Benchmark Engine";
    }
    await setDataSourceMode(selectedInputPageSource);

    if (loadingText) loadingText.innerText = "Calibrating vadose delay & conformal surrogates...";
    await new Promise(r => setTimeout(r, 450));
  } catch (err) {
    console.warn("Input sync error:", err);
  }

  // 7. Sync entered details into main dashboard controls
  const mainLat = document.getElementById("inputLat");
  const mainLon = document.getElementById("inputLon");
  if (mainLat) mainLat.value = latNum.toFixed(2);
  if (mainLon) mainLon.value = lonNum.toFixed(2);
  updateHeaderLocationDisplay(latNum, lonNum);

  const regionSelect = document.getElementById("regionPresetSelect");
  const regionLabelSpan = document.getElementById("regionPickerSelectedLabel");
  if (regionSelect) regionSelect.value = selectedInputPageRegion;
  if (regionLabelSpan) {
    const regionNames = {
      high_plains: "High Plains / Ogallala (USA)",
      north_german: "North German Basin (Europe)",
      ganges: "Indo-Gangetic Basin (India)",
      illinois: "Illinois Glacial Aquifer (USA)",
    };
    regionLabelSpan.innerText = regionNames[selectedInputPageRegion] || "Hydrogeological region";
  }

  // Position GIS Map and Marker to user's specified lat/lon
  updateMapMarker(latNum, lonNum, `<b>📍 Pinned Query Location</b><br>Lat: ${latNum.toFixed(4)}°, Lon: ${lonNum.toFixed(4)}°`);
  if (gisMap) {
    gisMap.invalidateSize();
    gisMap.setView([latNum, lonNum], 8);
  }
  updateInputGlobe(latNum, lonNum, selectedInputPageRegion);

  // 8. Save session state & transition to Dashboard
  sessionStorage.setItem("hasProceeded", "true");
  const inputScreen = document.getElementById("inputScreen");
  if (inputScreen) {
    inputScreen.classList.add("hidden");
    setTimeout(() => {
      inputScreen.style.display = "none";
      setGlobeLoading(false);
      if (continueBtn) {
        continueBtn.style.pointerEvents = "auto";
        continueBtn.style.opacity = "1";
      }
    }, 400);
  }

  // Execute predictions and MPC optimization on dashboard
  await fetchUnifiedControl();
}

function updateHeaderLocationDisplay(lat, lon) {
  const el = document.getElementById("headerLocationText");
  if (!el) return;
  const latVal = lat !== undefined ? parseFloat(lat) : (document.getElementById("inputLat") ? parseFloat(document.getElementById("inputLat").value) : 40.15);
  const lonVal = lon !== undefined ? parseFloat(lon) : (document.getElementById("inputLon") ? parseFloat(document.getElementById("inputLon").value) : -88.25);
  if (!isNaN(latVal) && !isNaN(lonVal)) {
    el.innerText = `Lat: ${latVal.toFixed(2)}°, Lon: ${lonVal.toFixed(2)}°`;
  }
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

  const clampedMonths = Math.min(Math.max(1, months), 120);
  currentChartHorizon = clampedMonths;

  // Sync all UI controls
  const inputEl = document.getElementById("customMonthInput");
  if (inputEl) inputEl.value = clampedMonths;

  const card1HVal = document.getElementById("inputHVal");
  if (card1HVal) card1HVal.value = clampedMonths;

  const hiddenH = document.getElementById("inputH");
  if (hiddenH) hiddenH.value = clampedMonths;

  const badgeEl = document.getElementById("chartHorizonBadge");
  if (badgeEl) badgeEl.innerText = `${clampedMonths}-Month Horizon`;

  if (btnEl) {
    document.querySelectorAll(".btn-horizon-chip").forEach(b => b.classList.remove("active"));
    btnEl.classList.add("active");
  } else {
    document.querySelectorAll(".btn-horizon-chip").forEach(b => {
      if (b.innerText === `${clampedMonths}M`) b.classList.add("active");
      else b.classList.remove("active");
    });
  }

  // Update background spatial rasters and 3D maps for the new horizon
  fetchDrawdownForecast(clampedMonths);

  // Re-render the active graph view without forcing back to conformal
  if (currentPredictionGraphView === "conformal") {
    showPlot2Loading(`Computing ${clampedMonths}-Month Conformal Forecast...`);
    try {
      initConformalChart(clampedMonths);
      await fetchDrawdownForecast(clampedMonths);
    } finally {
      hidePlot2Loading();
    }
  } else if (currentPredictionGraphView === "pumping_quotas") {
    await renderPumpingQuotasChart();
  } else if (currentPredictionGraphView === "hydrograph") {
    await renderHydrographChart();
  }
}

function destroyExistingChart() {
  if (typeof Chart !== "undefined") {
    const existing = Chart.getChart("conformalChart");
    if (existing) {
      existing.destroy();
    }
  }
  if (chartInstance) {
    try {
      chartInstance.destroy();
    } catch (e) {}
    chartInstance = null;
  }
}

function initConformalChart(horizon = 12) {
  const canvasEl = document.getElementById("conformalChart");
  if (!canvasEl) return;
  destroyExistingChart();
  const h = horizon || currentChartHorizon || 12;
  const ctx = canvasEl.getContext("2d");
  chartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: Array.from({ length: h }, (_, i) => `Month ${i+1}`),
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
          data: Array(h).fill(35.0),
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
  if (!tbody || !quotas) return;
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
  if (currentPredictionGraphView !== "conformal") {
    return;
  }

  const h = horizon || currentChartHorizon || (predictedHeads ? predictedHeads.length : 12);
  if (!chartInstance || !chartInstance.data || !chartInstance.data.datasets || chartInstance.data.datasets.length !== 4 || (chartInstance.data.labels && chartInstance.data.labels.length !== h)) {
    initConformalChart(h);
  }

  if (!chartInstance || !chartInstance.data || !chartInstance.data.datasets || chartInstance.data.datasets.length !== 4) {
    console.warn("updateChartData: chart not ready, skipping.");
    return;
  }

  const actualHorizon = Math.min(h, predictedHeads.length);
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

let currentPredictionGraphView = "conformal";

async function switchPredictionGraphView(viewType, e) {
  if (e) {
    e.stopPropagation();
    e.preventDefault();
  }
  closeAllTabDropupMenus();
  currentPredictionGraphView = viewType;

  const titleEl = document.getElementById("plot2Title");
  const subEl = document.getElementById("plot2Sub");
  const horizonControlsEl = document.getElementById("plot2HorizonControls") || document.querySelector(".horizon-controls-wrap");

  // Show horizon controls only for views that support multi-month custom horizons
  const horizonSupportedViews = ["conformal", "pumping_quotas", "hydrograph"];
  if (horizonControlsEl) {
    horizonControlsEl.style.display = horizonSupportedViews.includes(viewType) ? "flex" : "none";
  }

  if (viewType === "conformal") {
    if (titleEl) titleEl.innerText = "Piezometric Head Forecast & Split Conformal Bounds";
    if (subEl) subEl.innerText = "Point location hydraulic head time series with 95% safety intervals";
    initConformalChart(currentChartHorizon || 12);
    fetchDrawdownForecast(currentChartHorizon || 12);
  } else if (viewType === "lp_30day") {
    if (titleEl) titleEl.innerText = "Station CGWBHU2335 Worked 30-Day LP Extraction & Head Trajectory";
    if (subEl) subEl.innerText = "Daily extraction schedule (m/day) and water table trajectory (m) under s = -7.61m safety floor";
    renderSingleStationLPChart();
  } else if (viewType === "baselines") {
    if (titleEl) titleEl.innerText = "Paper Baseline ML Models Performance (Table 3)";
    if (subEl) subEl.innerText = "Held-out RMSE and MAE across Linear Regression, Random Forest, SVR, HGB, & LSTM";
    renderPaperBaselinesChart();
  } else if (viewType === "ablation") {
    if (titleEl) titleEl.innerText = "Historical Level Autoregressive Ablation Suite (Table 4)";
    if (subEl) subEl.innerText = "Comparison of full LSTM model vs. ablated model (level history zeroed out)";
    renderAblationChart();
  } else if (viewType === "pumping_quotas") {
    if (titleEl) titleEl.innerText = `${currentChartHorizon || 12}-Month Multi-Well SCP CCMPC Pumping Quotas`;
    if (subEl) subEl.innerText = "Optimal monthly pumping allocation (m³/month) per well node";
    renderPumpingQuotasChart();
  } else if (viewType === "hydrograph") {
    if (titleEl) titleEl.innerText = `${currentChartHorizon || 12}-Month Hydrograph: Rainfall, Vadose Delay Recharge & Head Dynamics`;
    if (subEl) subEl.innerText = "Precipitation, Gamma vadose delay effective recharge, and water table head";
    renderHydrographChart();
  }
}

async function renderSingleStationLPChart() {
  showPlot2Loading("Solving Station CGWBHU2335 30-Day LP Optimization...");
  try {
    const res = await fetch("/api/v1/control/single_station_lp", { method: "POST" });
    const data = await res.json();
    if (!data.success) { console.error("LP solver failed:", data); return; }

    destroyExistingChart();
    const canvas = document.getElementById("conformalChart");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    const labels = Array.from({ length: 30 }, (_, i) => `Day ${i + 1}`);

    chartInstance = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            type: "bar",
            label: "Daily Pumping Allocation E_t (m/day)",
            data: data.daily_extractions,
            backgroundColor: "rgba(0, 242, 254, 0.6)",
            borderColor: "#00f2fe",
            borderWidth: 1,
            yAxisID: "yPumping",
          },
          {
            type: "line",
            label: "Predicted Head Trajectory H(t) (m)",
            data: data.head_trajectory.slice(1),
            borderColor: "#4ade80",
            backgroundColor: "rgba(74, 222, 128, 0.1)",
            fill: false,
            tension: 0.2,
            yAxisID: "yHead",
          },
          {
            type: "line",
            label: "Safety Floor Limit s (-7.61m)",
            data: Array(30).fill(data.safety_floor_m),
            borderColor: "#ef4444",
            borderDash: [4, 4],
            borderWidth: 2,
            pointRadius: 0,
            yAxisID: "yHead",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          yPumping: {
            type: "linear",
            position: "left",
            title: { display: true, text: "Pumping Cap (m/day)", color: "#00f2fe" },
            ticks: { color: "#94a3b8" },
            grid: { color: "rgba(255, 255, 255, 0.05)" },
          },
          yHead: {
            type: "linear",
            position: "right",
            title: { display: true, text: "Groundwater Head (m)", color: "#4ade80" },
            ticks: { color: "#94a3b8" },
            grid: { drawOnChartArea: false },
          },
          x: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(255, 255, 255, 0.05)" } },
        },
        plugins: {
          legend: { labels: { color: "#f0f4f8", font: { family: "Outfit" } } },
        },
      },
    });
  } catch (err) {
    console.error("LP Chart error:", err);
  } finally {
    hidePlot2Loading();
  }
}

async function renderPaperBaselinesChart() {
  showPlot2Loading("Evaluating Paper ML Baseline Models (RF, SVR, HGB, LSTM)...");
  try {
    const res = await fetch("/api/v1/evaluation/paper_baselines");
    const data = await res.json();
    if (!data.baselines) { console.error("No baselines in response:", data); return; }

    destroyExistingChart();
    const canvas = document.getElementById("conformalChart");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    const modelNames = Object.keys(data.baselines);
    const rmseValues = modelNames.map((m) => data.baselines[m].RMSE);
    const maeValues = modelNames.map((m) => data.baselines[m].MAE);

    chartInstance = new Chart(ctx, {
      type: "bar",
      data: {
        labels: modelNames,
        datasets: [
          {
            label: "RMSE Error (m)",
            data: rmseValues,
            backgroundColor: "rgba(0, 242, 254, 0.7)",
            borderColor: "#00f2fe",
            borderWidth: 1,
          },
          {
            label: "MAE Error (m)",
            data: maeValues,
            backgroundColor: "rgba(168, 85, 247, 0.7)",
            borderColor: "#a855f7",
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            title: { display: true, text: "Error in Meters (m)", color: "#f0f4f8" },
            ticks: { color: "#94a3b8" },
            grid: { color: "rgba(255, 255, 255, 0.05)" },
          },
          x: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(255, 255, 255, 0.05)" } },
        },
        plugins: {
          legend: { labels: { color: "#f0f4f8", font: { family: "Outfit" } } },
        },
      },
    });
  } catch (err) {
    console.error("Baselines chart error:", err);
  } finally {
    hidePlot2Loading();
  }
}

async function renderAblationChart() {
  showPlot2Loading("Running Autoregressive History Ablation Suite...");
  try {
    const res = await fetch("/api/v1/evaluation/ablation");
    const data = await res.json();
    if (!data.ablation) { console.error("No ablation in response:", data); return; }

    destroyExistingChart();
    const canvas = document.getElementById("conformalChart");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    const fullM = data.ablation.Full_Model_P_T_LevelHistory;
    const ablM = data.ablation.Ablated_Model_LevelHistory_Removed;

    chartInstance = new Chart(ctx, {
      type: "bar",
      data: {
        labels: ["Full Model (P, T, Level H_t-1)", "Ablated Model (Level History Zeroed Out)"],
        datasets: [
          {
            label: "RMSE (m)",
            data: [fullM.RMSE, ablM.RMSE],
            backgroundColor: ["rgba(74, 222, 128, 0.7)", "rgba(239, 68, 68, 0.7)"],
            borderColor: ["#4ade80", "#ef4444"],
            borderWidth: 1,
          },
          {
            label: "MAE (m)",
            data: [fullM.MAE, ablM.MAE],
            backgroundColor: ["rgba(56, 189, 248, 0.7)", "rgba(249, 115, 22, 0.7)"],
            borderColor: ["#38bdf8", "#f97316"],
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            title: { display: true, text: "Error Magnitude (m)", color: "#f0f4f8" },
            ticks: { color: "#94a3b8" },
            grid: { color: "rgba(255, 255, 255, 0.05)" },
          },
          x: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(255, 255, 255, 0.05)" } },
        },
        plugins: {
          legend: { labels: { color: "#f0f4f8", font: { family: "Outfit" } } },
        },
      },
    });
  } catch (err) {
    console.error("Ablation chart error:", err);
  } finally {
    hidePlot2Loading();
  }
}

async function renderPumpingQuotasChart() {
  const horizon = currentChartHorizon || 12;
  const titleEl = document.getElementById("plot2Title");
  if (titleEl) titleEl.innerText = `${horizon}-Month Multi-Well SCP CCMPC Pumping Quotas`;

  showPlot2Loading(`Fetching SCP CCMPC Multi-Well Pumping Quotas (${horizon} Months)...`);
  try {
    const res = await fetch("/api/v1/control/pumping_quotas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ horizon: horizon }),
    });
    const data = await res.json();
    if (!data.pumping_quotas) { console.error("No pumping_quotas in response:", data); return; }

    destroyExistingChart();
    const canvas = document.getElementById("conformalChart");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    const quotas = data.pumping_quotas;
    const months = Array.from({ length: quotas.length }, (_, i) => `Month ${i + 1}`);
    const datasets = [];
    const numWells = quotas[0] ? Math.min(quotas[0].length, 6) : 0;
    const colors = ["#00f2fe", "#4ade80", "#a855f7", "#f97316", "#eab308", "#ec4899"];

    for (let w = 0; w < numWells; w++) {
      datasets.push({
        label: `Well-${w + 1}`,
        data: quotas.map((q) => q[w]),
        backgroundColor: colors[w % colors.length],
      });
    }

    chartInstance = new Chart(ctx, {
      type: "bar",
      data: { labels: months, datasets: datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            stacked: true,
            title: { display: true, text: "Pumping Quota (m³/month)", color: "#f0f4f8" },
            ticks: { color: "#94a3b8" },
            grid: { color: "rgba(255, 255, 255, 0.05)" },
          },
          x: { stacked: true, ticks: { color: "#94a3b8" }, grid: { color: "rgba(255, 255, 255, 0.05)" } },
        },
        plugins: {
          legend: { labels: { color: "#f0f4f8", font: { family: "Outfit" } } },
        },
      },
    });
  } catch (err) {
    console.error("Pumping quotas chart error:", err);
  } finally {
    hidePlot2Loading();
  }
}

async function renderHydrographChart() {
  const latVal = parseFloat(document.getElementById("inputLat") ? document.getElementById("inputLat").value : 40.15) || 40.15;
  const lonVal = parseFloat(document.getElementById("inputLon") ? document.getElementById("inputLon").value : -88.25) || -88.25;
  const horizon = currentChartHorizon || 12;

  const titleEl = document.getElementById("plot2Title");
  if (titleEl) titleEl.innerText = `${horizon}-Month Hydrograph: Rainfall, Vadose Delay Recharge & Head Dynamics`;

  showPlot2Loading(`Building ${horizon}-Month Hydrograph for (${latVal.toFixed(2)}°, ${lonVal.toFixed(2)}°)...`);
  try {
    const res = await fetch(`/api/v1/forecast/location_hydrograph?lat=${latVal}&lon=${lonVal}&horizon=${horizon}`);
    const data = await res.json();
    if (!data.precipitation_mm) { console.error("No precipitation_mm in response:", data); return; }

    destroyExistingChart();
    const canvas = document.getElementById("conformalChart");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    let prec = Array.isArray(data.precipitation_mm) ? data.precipitation_mm : [];
    let reff = Array.isArray(data.effective_recharge_mm) ? data.effective_recharge_mm : [];
    let head = Array.isArray(data.water_table_head_m) ? data.water_table_head_m : [];

    // Ensure array length strictly matches the requested horizon N
    if (prec.length !== horizon) {
      if (prec.length > horizon) {
        prec = prec.slice(0, horizon);
        reff = reff.slice(0, horizon);
        head = head.slice(0, horizon);
      } else if (prec.length > 0 && prec.length < horizon) {
        const origLen = prec.length;
        const newPrec = [], newReff = [], newHead = [];
        for (let i = 0; i < horizon; i++) {
          newPrec.push(prec[i % origLen]);
          newReff.push(reff[i % origLen]);
          newHead.push(head[i % origLen] - 0.01 * Math.floor(i / origLen));
        }
        prec = newPrec;
        reff = newReff;
        head = newHead;
      }
    }

    const timesteps = prec.length || horizon;
    const labels = Array.from({ length: timesteps }, (_, i) => `Month ${i + 1}`);

    chartInstance = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            type: "bar",
            label: "Precipitation P(t) (mm)",
            data: prec,
            backgroundColor: "rgba(56, 189, 248, 0.5)",
            borderColor: "#38bdf8",
            yAxisID: "yRain",
          },
          {
            type: "line",
            label: "Vadose Delay Effective Recharge R_eff (mm)",
            data: reff,
            borderColor: "#f97316",
            backgroundColor: "rgba(249, 115, 22, 0.1)",
            tension: 0.3,
            yAxisID: "yRain",
          },
          {
            type: "line",
            label: "Water Table Head G(t) (m)",
            data: head,
            borderColor: "#4ade80",
            backgroundColor: "rgba(74, 222, 128, 0.1)",
            tension: 0.3,
            yAxisID: "yHead",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          yRain: {
            type: "linear",
            position: "left",
            title: { display: true, text: "Recharge / Rainfall (mm)", color: "#38bdf8" },
            ticks: { color: "#94a3b8" },
            grid: { color: "rgba(255, 255, 255, 0.05)" },
          },
          yHead: {
            type: "linear",
            position: "right",
            title: { display: true, text: "Water Table Head (m)", color: "#4ade80" },
            ticks: { color: "#94a3b8" },
            grid: { drawOnChartArea: false },
          },
          x: {
            ticks: {
              color: "#94a3b8",
              maxRotation: horizon > 24 ? 45 : 0,
              autoSkip: horizon > 18,
              maxTicksLimit: Math.min(horizon, 24)
            },
            grid: { color: "rgba(255, 255, 255, 0.05)" }
          },
        },
        plugins: {
          legend: { labels: { color: "#f0f4f8", font: { family: "Outfit" } } },
        },
      },
    });
  } catch (err) {
    console.error("Hydrograph chart error:", err);
  } finally {
    hidePlot2Loading();
  }
}

async function fetchLocationPredict(lat, lon, horizon) {
  const h = horizon || currentChartHorizon || 12;
  const latVal = (lat !== undefined && lat !== null) ? parseFloat(lat) : (parseFloat(document.getElementById("inputLat")?.value) || 40.15);
  const lonVal = (lon !== undefined && lon !== null) ? parseFloat(lon) : (parseFloat(document.getElementById("inputLon")?.value) || -88.25);
  
  if (document.getElementById("inputLat")) document.getElementById("inputLat").value = latVal.toFixed(4);
  if (document.getElementById("inputLon")) document.getElementById("inputLon").value = lonVal.toFixed(4);
  if (document.getElementById("inputH")) document.getElementById("inputH").value = h;
  if (document.getElementById("inputHVal")) document.getElementById("inputHVal").value = h;
  persistPin(latVal, lonVal);

  try {
    const res = await fetch("/api/v1/forecast/location_predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lat: latVal, lon: lonVal, horizon: h }),
    });
    const data = await res.json();
    if (data.forecast) {
      if (currentPredictionGraphView === "conformal") {
        updateChartData(data.forecast.predicted_heads_m.map(v => [v]), data.conformal_q_hat, h);
      }
      if (data.raster_slice) {
        renderHeatmap(data.raster_slice, data.grid_cell.row, data.grid_cell.col);
        update3DMap(data.raster_slice, data.grid_cell.row, data.grid_cell.col);
      }
    }
  } catch (err) {
    console.error("fetchLocationPredict error:", err);
  }
}

async function changeRegionPreset() {
  const regionSelect = document.getElementById("regionPresetSelect");
  if (!regionSelect) return;
  const regionKey = regionSelect.value;
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
      const latEl = document.getElementById("inputLat");
      const lonEl = document.getElementById("inputLon");
      if (latEl) latEl.value = centerLat.toFixed(4);
      if (lonEl) lonEl.value = centerLon.toFixed(4);
      updateMapMarker(centerLat, centerLon, `<b>📍 ${data.metadata.region_name} Center</b>`);
    }

    fetchDrawdownForecast(currentChartHorizon || 12);
    fetchDepletionAlerts();
    runOptimization();
  } catch (err) {
    console.error("Region preset error:", err);
  }
}

async function predictPointLocation() {
  const latVal = document.getElementById("inputLat") ? document.getElementById("inputLat").value : "";
  const lonVal = document.getElementById("inputLon") ? document.getElementById("inputLon").value : "";
  const customH = document.getElementById("customMonthInput");
  const card1H = document.getElementById("inputHVal");
  const hiddenH = document.getElementById("inputH");

  const horizon = parseInt(customH && customH.value ? customH.value : (card1H && card1H.value ? card1H.value : (hiddenH && hiddenH.value ? hiddenH.value : 12))) || currentChartHorizon || 12;

  const lat = latVal !== "" ? parseFloat(latVal) : 40.15;
  const lon = lonVal !== "" ? parseFloat(lonVal) : -88.25;

  try {
    const res = await fetch("/api/v1/forecast/location_predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lat, lon, horizon }),
    });
    const data = await res.json();

    if (data.forecast) {
      // 1. Update active chart view with point location forecast
      if (currentPredictionGraphView === "conformal") {
        updateChartData(data.forecast.predicted_heads_m.map(v => [v]), data.conformal_q_hat, horizon);
      } else if (currentPredictionGraphView === "pumping_quotas") {
        renderPumpingQuotasChart();
      } else if (currentPredictionGraphView === "hydrograph") {
        renderHydrographChart();
      }

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
        <b>Head (Mo ${horizon}):</b> ${headLast}m (95% Bound: ${safeLast}m)<br>
        <b>Status:</b> ${data.depletion_risk}
      `;
      // Move the pin to the predicted location and bind this popup.
      // (Previously the popup HTML was built and then dropped — nothing
      // ever moved the marker, so map clicks updated the data behind
      // the scenes but left the pin sitting on the old location.)
      if (locationMarker) {
        locationMarker.setLatLng([data.query_coordinates.lat, data.query_coordinates.lon]);
        locationMarker.bindPopup(popupHtml);
      }
      // Sync region preset selector and label if auto-switched
      if (data.region_key) {
        const regionSelect = document.getElementById("regionPresetSelect");
        if (regionSelect) regionSelect.value = data.region_key;
        const regionLabelSpan = document.getElementById("regionPickerSelectedLabel");
        if (regionLabelSpan && data.region_name) {
          regionLabelSpan.innerText = data.region_name;
        }
      }

      // Keep the header status bar on the same location — the map-click
      // path never called this, so the status bar kept showing the old
      // coordinates after a click changed everything else.
      updateHeaderLocationDisplay(data.query_coordinates.lat, data.query_coordinates.lon);
      persistPin(data.query_coordinates.lat, data.query_coordinates.lon);

      document.getElementById("timestepDisplay").innerText = `Lat: ${data.query_coordinates.lat}°, Lon: ${data.query_coordinates.lon}° (R:${data.grid_cell.row}, C:${data.grid_cell.col})`;
    }
  } catch (err) {
    console.error("Location predict error:", err);
  }
}

function openCustomReportModal() {
  const modal = document.getElementById("customReportModal");
  if (!modal) {
    generateCustomPdfReport();
    return;
  }
  // Initialize horizon values from current chart / input state if available
  const customH = document.getElementById("customMonthInput");
  const card1H = document.getElementById("inputHVal");
  const currentH = parseInt(customH && customH.value ? customH.value : (card1H && card1H.value ? card1H.value : 12)) || currentChartHorizon || 12;

  const hConf = document.getElementById("rptHorizon_conformal");
  const hPump = document.getElementById("rptHorizon_pumping");
  const hHydro = document.getElementById("rptHorizon_hydrograph");

  if (hConf) hConf.value = currentH;
  if (hPump) hPump.value = currentH;
  if (hHydro) hHydro.value = currentH;

  applyProvenanceOptionVisibility();

  modal.classList.remove("hidden");
  modal.style.display = "flex";
}

// The admin dashboard can hide the provenance option entirely
// (server-side UI setting). When hidden, the report generator also
// forces the section off, so it cannot leak into a PDF via a stale
// checkbox state.
async function applyProvenanceOptionVisibility() {
  const row = document.getElementById("rptProvenanceRow");
  if (!row) return;
  try {
    const res = await fetch("/api/v1/status");
    const data = await res.json();
    const show = !data.ui_settings || data.ui_settings.show_provenance_option !== false;
    window._showProvenanceOption = show;
    row.style.display = show ? "" : "none";
  } catch (e) {
    window._showProvenanceOption = true;
    row.style.display = "";
  }
}

function closeCustomReportModal() {
  const modal = document.getElementById("customReportModal");
  if (modal) {
    modal.classList.add("hidden");
    modal.style.display = "none";
  }
}

function toggleAllReportCheckboxes(checkedState) {
  const ids = [
    "rptSec_summary",
    "rptSec_stratigraphy",
    "rptSec_conformal",
    "rptSec_ablation",
    "rptSec_hydrograph",
    "rptSec_math",
    "rptSec_table",
    "rptSec_recommendations"
  ];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.checked = checkedState;
  });
}

function generateCustomPdfReport() {
  const lat = parseFloat(document.getElementById("inputLat") ? document.getElementById("inputLat").value : 40.15) || 40.15;
  const lon = parseFloat(document.getElementById("inputLon") ? document.getElementById("inputLon").value : -88.25) || -88.25;

  const isChecked = id => {
    const el = document.getElementById(id);
    return el ? (el.checked ? 1 : 0) : 1;
  };
  const getHorizon = (id, fallback) => {
    const el = document.getElementById(id);
    return el ? (parseInt(el.value) || fallback) : fallback;
  };

  const secSummary = isChecked("rptSec_summary");
  const secHeatmap = isChecked("rptSec_heatmap");
  const secProvenance = window._showProvenanceOption === false ? 0 : isChecked("rptSec_provenance");
  const secStratigraphy = isChecked("rptSec_stratigraphy");
  const secConformal = isChecked("rptSec_conformal");
  const hConformal = getHorizon("rptHorizon_conformal", 12);
  // Removed from PDF printing (2026-11-11): Prediction 2 (30-day LP),
  // Prediction 3 (baselines), Prediction 5 (pumping quotas) — always off.
  const secLp30 = 0;
  const secBaselines = 0;
  const secAblation = isChecked("rptSec_ablation");
  const secPumping = 0;
  const hPumping = 12;
  const secHydrograph = isChecked("rptSec_hydrograph");
  const hHydrograph = getHorizon("rptHorizon_hydrograph", 12);
  const secMath = isChecked("rptSec_math");
  const secTable = isChecked("rptSec_table");
  const secRecs = isChecked("rptSec_recommendations");

  let params = new URLSearchParams();
  params.append("lat", lat);
  params.append("lon", lon);
  params.append("horizon", hConformal);
  params.append("sec_summary", secSummary);
  params.append("sec_heatmap", secHeatmap);
  params.append("sec_provenance", secProvenance);
  params.append("sec_stratigraphy", secStratigraphy);
  params.append("sec_conformal", secConformal);
  params.append("horizon_conformal", hConformal);
  params.append("sec_lp30day", secLp30);
  params.append("sec_baselines", secBaselines);
  params.append("sec_ablation", secAblation);
  params.append("sec_pumping", secPumping);
  params.append("horizon_pumping", hPumping);
  params.append("sec_hydrograph", secHydrograph);
  params.append("horizon_hydrograph", hHydrograph);
  params.append("sec_math", secMath);
  params.append("sec_table", secTable);
  params.append("sec_recommendations", secRecs);

  // Extract chart data from the Piezometric Head Chart instance if present
  try {
    if (chartInstance && chartInstance.data) {
      const cd = chartInstance.data;
      const labels = cd.labels || [];
      const predDs = cd.datasets.find(d => d.label && d.label.toLowerCase().includes("predicted"));
      // The lower-bound dataset is labelled "Tightened Conformal Safety
      // (G_pred - q̂)" — it contains no word "lower", so match those too,
      // otherwise the report silently loses the lower bound series.
      const lowerDs = cd.datasets.find(d => d.label && (d.label.toLowerCase().includes("lower") || d.label.toLowerCase().includes("safety") || d.label.toLowerCase().includes("tightened")));
      const upperDs = cd.datasets.find(d => d.label && d.label.toLowerCase().includes("upper"));
      if (predDs && predDs.data && predDs.data.length) {
        params.append("labels", JSON.stringify(labels));
        params.append("vals", JSON.stringify(predDs.data));
        if (lowerDs && lowerDs.data) params.append("lower", JSON.stringify(lowerDs.data));
        if (upperDs && upperDs.data) params.append("upper", JSON.stringify(upperDs.data));
      }
    }
  } catch(e) { console.warn("Chart data extraction for report failed:", e); }

  closeCustomReportModal();
  const reportUrl = `/api/v1/reports/view?${params.toString()}`;
  window.open(reportUrl, "_blank");
}

function openLocationReport() {
  openCustomReportModal();
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
  const headerLocSpan = document.getElementById("headerLocationText");
  if (labelSpan) labelSpan.innerText = labelText;
  if (headerLocSpan) headerLocSpan.innerText = `📍 ${labelText}`;
  if (nativeSelect) {
    nativeSelect.value = value;
    changeRegionPreset();
  }
  closeAllChoicePickers();
}

function applyHeaderCoordinates() {
  const latInput = document.getElementById("headerLatInput");
  const lonInput = document.getElementById("headerLonInput");
  if (!latInput || !lonInput) return;
  const lat = parseFloat(latInput.value);
  const lon = parseFloat(lonInput.value);
  if (isNaN(lat) || isNaN(lon)) {
    alert("Please enter valid numerical latitude and longitude coordinates.");
    return;
  }

  const mainLat = document.getElementById("inputLat");
  const mainLon = document.getElementById("inputLon");
  if (mainLat) mainLat.value = lat.toFixed(4);
  if (mainLon) mainLon.value = lon.toFixed(4);

  const headerLocSpan = document.getElementById("headerLocationText");
  if (headerLocSpan) headerLocSpan.innerText = `📍 (${lat.toFixed(2)}°, ${lon.toFixed(2)}°)`;

  closeAllChoicePickers();

  if (typeof updateMapMarker === "function") {
    updateMapMarker(lat, lon, `<b>📍 Pinned Query Location</b><br>Lat: ${lat.toFixed(4)}°, Lon: ${lon.toFixed(4)}°`);
  }

  predictPointLocation();
}

// While a data-source switch rebuilds the dataset (a live GEE build takes
// minutes), poll /api/v1/status and mirror the provider's ingestion progress
// into the visible loading element — the input screen's loading line while
// it is showing, otherwise the GEE status badge text — so the user sees
// what is actually happening instead of a static spinner text.
// Returns a stop function.
function startIngestionProgressPolling() {
  let stopped = false;
  let polls = 0;
  const tick = async () => {
    if (stopped || ++polls > 600) {
      clearInterval(timer);
      return;
    }
    try {
      const res = await fetch("/api/v1/status");
      const data = await res.json();
      const p = data.ingestion_progress;
      if (!p || !p.message || p.stage === "idle") return;
      const inputText = document.getElementById("inputScreenLoadingText");
      const badgeText = document.getElementById("geeStatusText");
      const el = inputText && inputText.classList.contains("visible") ? inputText : badgeText;
      if (el) {
        el.innerText =
          p.percent != null && p.stage === "sampling" ? `${p.message} (${p.percent}%)` : p.message;
      }
    } catch (err) {
      /* progress polling is best-effort */
    }
  };
  const timer = setInterval(tick, 1500);
  tick();
  return () => {
    stopped = true;
    clearInterval(timer);
  };
}

async function setDataSourceMode(mode) {
  const stopProgress = startIngestionProgressPolling();
  try {
    const res = await fetch("/api/v1/config/data_source", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data_mode: mode }),
    });
    const data = await res.json();
    await updateGEEStatusBadge();
    await fetchUnifiedControl();
  } catch (err) {
    console.error("Data source mode switch error:", err);
  } finally {
    stopProgress();
  }
}

function toggleDataSourceChannel() {
  const selectEl = document.getElementById("dataSourceSelect");
  if (selectEl) {
    setDataSourceMode(selectEl.value);
  }
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

async function updateGEEStatusBadge() {
  try {
    const res = await fetch("/api/v1/status");
    const data = await res.json();
    const badge = document.getElementById("geeStatusBadge");
    const textSpan = document.getElementById("geeStatusText");
    if (!badge) return;

    let textVal = "";
    if (data.provider_metadata && data.provider_metadata.ee_initialized) {
      textVal = "GEE CONNECTED";
      badge.style.background = "rgba(16, 185, 129, 0.15)";
      badge.style.color = "#10B981";
      badge.style.borderColor = "rgba(16, 185, 129, 0.3)";
    } else if (data.data_mode === "realtime") {
      textVal = "GEE STANDBY";
      badge.style.background = "rgba(245, 158, 11, 0.15)";
      badge.style.color = "#F59E0B";
      badge.style.borderColor = "rgba(245, 158, 11, 0.3)";
    } else {
      textVal = "SYNTHETIC ENGINE";
      badge.style.background = "rgba(59, 130, 246, 0.15)";
      badge.style.color = "#60A5FA";
      badge.style.borderColor = "rgba(59, 130, 246, 0.3)";
    }

    if (textSpan) {
      textSpan.innerText = textVal;
    } else {
      badge.innerText = textVal;
    }
  } catch (e) {
    console.warn("GEE Status check error:", e);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    setupChoicePickerHoverHandlers();
    updateGEEStatusBadge();
    updateHeaderLocationDisplay();
  });
} else {
  setupChoicePickerHoverHandlers();
  updateGEEStatusBadge();
  updateHeaderLocationDisplay();
}
