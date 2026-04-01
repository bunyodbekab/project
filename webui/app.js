let backend = null;
let latestState = null;

const topPanel = document.getElementById("topPanel");
const headerTitle = document.getElementById("headerTitle");
const headerMain = document.getElementById("headerMain");
const serviceGrid = document.getElementById("serviceGrid");
const controlsWrap = document.getElementById("controlsWrap");
const pauseButton = document.getElementById("pauseButton");
const pauseText = pauseButton.querySelector(".pause-text");
const pauseSub = document.getElementById("pauseSub");
const pauseIconLeft = document.getElementById("pauseIconLeft");
const pauseIconRight = document.getElementById("pauseIconRight");

const pinModal = document.getElementById("pinModal");
const pinDots = document.getElementById("pinDots");
const pinError = document.getElementById("pinError");
const pinClose = document.getElementById("pinClose");
const pinSubmit = document.getElementById("pinSubmit");
const pinClear = document.getElementById("pinClear");
const pinKeys = document.querySelectorAll(".pin-key");

const fallbackPauseIcon = encodeURI("../icons/⛔.png");
const DEFAULT_BUTTON_COUNT = 7;
const ADMIN_HOLD_MS = 2000;
const ADMIN_MULTI_TAP_WINDOW_MS = 2000;
const ADMIN_MULTI_TAP_COUNT = 4;
const INTERACTION_LOCK_MS = 1000;
let isDebug = false;

let allowedPins = [];
let settings = null; // will be filled from backend/api; defaults only if config is missing
let stopPressed = false;
let adminHoldTimer = null;
let pauseTapCount = 0;
let pauseTapTimer = null;
let interactionLocked = false;
let interactionLockTimer = null;
let addMoneyLocked = false;

function clone(obj) {
  return JSON.parse(JSON.stringify(obj));
}

function lockInteractions() {
  interactionLocked = true;
  if (interactionLockTimer) {
    clearTimeout(interactionLockTimer);
  }
  interactionLockTimer = setTimeout(() => {
    interactionLocked = false;
  }, INTERACTION_LOCK_MS);
}

function safeAddMoney() {
  if (addMoneyLocked) return;
  addMoneyLocked = true;
  setTimeout(() => {
    addMoneyLocked = false;
  }, 250);
  if (!backend || !latestState || !latestState.canAddMoney) {
    return;
  }
  if (typeof backend.addMoney === "function") {
    backend.addMoney();
  }
}

function _normalize_front_settings(raw) {
  const s = raw || {};
  let services = s.services ?? s.service_list ?? s.serviceList ?? [];
  if (!Array.isArray(services) && services && typeof services === "object") {
    services = Object.entries(services).map(([name, cfg]) => ({ name, ...(cfg || {}) }));
  }
  services = services.map((svc, idx) => {
    const pricePerSec = Number(svc.price_per_sec || svc.pricePerSec || 0);
    const secFromPrice = pricePerSec > 0 ? Math.ceil(5000 / Math.max(1, pricePerSec)) : null;
    const seconds = svc.secondsPer5000 ?? svc.seconds_per_5000 ?? secFromPrice ?? 120;
    return {
      ...svc,
      name: svc.name || svc.key || `XIZMAT${idx + 1}`,
      key: svc.key || svc.name || `XIZMAT${idx + 1}`,
      label: svc.label || svc.display_name || svc.name || svc.key || `Xizmat ${idx + 1}`,
      icon: svc.icon || svc.icon_file || "",
      iconUrl: svc.iconUrl || svc.icon_url || "",
      theme: svc.theme || "suv",
      showIcon: svc.showIcon !== false,
      active: svc.active !== false,
      secondsPer5000: Math.max(1, parseInt(seconds || 120, 10)),
    };
  });

  return {
    pin: s.pin ?? s.PIN ?? s.admin_pin ?? "",
    pin2: s.pin2 ?? s.pin_alt ?? s.admin_pin_alt ?? s.pinAlt ?? "",
    buttonCount: parseInt(s.buttonCount ?? s.totalButtons ?? services.length ?? DEFAULT_BUTTON_COUNT, 10) || DEFAULT_BUTTON_COUNT,
    showIcons: s.showIcons ?? s.show_icons ?? true,
    freePause: s.freePause ?? s.free_pause ?? s.pause?.freeSeconds ?? 0,
    paidPause: s.paidPause ?? s.paid_pause ?? s.pause?.paidSecondsPer5000 ?? 1,
    services,
  };
}

function _derive_settings_from_state(state) {
  const services = Array.isArray(state?.services)
    ? state.services.map((svc, idx) => ({
        name: svc.name || svc.key || `XIZMAT${idx + 1}`,
        key: svc.key || svc.name || `XIZMAT${idx + 1}`,
        label: svc.label || svc.name || svc.key || `Xizmat ${idx + 1}`,
        iconUrl: svc.iconUrl || "",
        icon: svc.icon || "",
        theme: svc.theme || "suv",
        showIcon: svc.showIcon !== false,
        active: svc.active !== false,
        secondsPer5000: svc.secondsPer5000 || 120,
      }))
    : [];
  return {
    pin: (state?.admin_pins || [])[0] || "",
    pin2: (state?.admin_pins || [])[1] || "",
    buttonCount: services.length || DEFAULT_BUTTON_COUNT,
    showIcons: true,
    freePause: 0,
    paidPause: 1,
    services,
  };
}

function applySettings(newSettings, source = "unknown") {
  settings = _normalize_front_settings(newSettings || {});
  console.log(`[SETTINGS] applied from ${source}`);
  if (latestState) {
    render(latestState);
  }
}

function refreshSettingsFromBackend() {
  if (backend && typeof backend.getSettings === "function") {
    backend.getSettings((payload) => {
      try {
        const cfg = parsePayload(payload);
        if (cfg) {
          applySettings(cfg, "backend");
          return;
        }
      } catch (e) {
        console.warn("getSettings parse error", e);
      }
      if (latestState) {
        applySettings(_derive_settings_from_state(latestState), "state-fallback");
      }
    });
    return;
  }

  fetch("/api/config")
    .then((r) => r.json())
    .then((cfg) => applySettings(cfg, "api"))
    .catch(() => {
      if (latestState) {
        applySettings(_derive_settings_from_state(latestState), "state-fallback");
      }
    });
}

function parsePayload(payload) {
  if (!payload) {
    return null;
  }
  if (typeof payload === "string") {
    return JSON.parse(payload);
  }
  return payload;
}

function requestState() {
  if (!backend || typeof backend.getState !== "function") {
    return;
  }
  backend.getState((payload) => {
    try {
      const state = parsePayload(payload);
      if (state) {
        render(state);
      }
    } catch (e) {
      console.error("state parse error", e);
    }
  });
}

function renderHeader(state) {
  const color = state.headerColor || "#ffffff";
  const balanceValue = typeof state.balance === "number" ? state.balance : Number(state.balanceText);
  const isZero = !Number.isNaN(balanceValue) && balanceValue <= 0;

  if (state.mode === "idle") {
    if (isZero) {
      headerTitle.textContent = state.title || "XUSH KELIBSIZ";
      headerMain.textContent = state.mainText || state.welcomeText || "XUSH KELIBSIZ";
    } else {
      headerTitle.textContent = "BALANS";
      headerMain.innerHTML = `${state.balanceText || balanceValue || "0"}<span class="unit">SO'M</span>`;
    }
    headerTitle.style.color = color;
    headerMain.style.color = color;
    return;
  }

  headerTitle.textContent = state.title || "";
  headerTitle.style.color = color;
  headerMain.textContent = state.mainText || "00:00";
  headerMain.style.color = color;
}

function resolveIconUrl(iconName) {
  if (!iconName) return null;
  return encodeURI(`../icons/${iconName}`);
}

function mapServicesForRender(state) {
  if (!settings) {
    settings = _normalize_front_settings(_derive_settings_from_state(state));
  }
  const stateServices = Array.isArray(state.services) ? state.services : [];
  const merged = settings.services.map((cfg, idx) => {
    const fromState = stateServices.find((s) => s.key === cfg.name || s.name === cfg.name) || stateServices[idx] || {};

    const key = fromState.key || cfg.key || cfg.name || `service-${idx + 1}`;
    const label = fromState.label || cfg.name || key;
    const name = fromState.name || cfg.name || key;

    const showIcon = settings.showIcons && cfg.showIcon !== false;
    const iconFile = cfg.icon || fromState.icon;
    const iconUrl = showIcon ? (fromState.iconUrl || cfg.iconUrl || (iconFile ? resolveIconUrl(iconFile) : null)) : null;
    const active = (cfg.active !== false) && (fromState.active !== false);

    return {
      ...fromState,
      ...cfg,
      key,
      name,
      label,
      iconUrl,
      active,
    };
  });

  const limit = settings.buttonCount || merged.length;
  const ready = merged.filter((svc, idx) => idx < limit && svc.active !== false);
  console.log("[MAP] services", ready.map((s) => ({ key: s.key, name: s.name, label: s.label, theme: s.theme, icon: s.icon, active: s.active })));
  return ready;
}

function createServiceButton(service, activeKey) {
  const btn = document.createElement("button");
  btn.type = "button";
  const theme = service.theme || "suv";
  btn.className = `service-btn theme-${theme}`;
  if (activeKey && service.key === activeKey) {
    btn.classList.add("is-active");
  }

  const showIcon = settings.showIcons && service.showIcon !== false && !!service.iconUrl;
  if (showIcon) {
    const img = document.createElement("img");
    img.src = service.iconUrl;
    img.alt = service.label || service.key;
    btn.appendChild(img);
  } else {
    btn.classList.add("no-icon");
  }

  const label = document.createElement("span");
  label.className = "service-label";
  label.innerHTML = (service.label || service.key || "").replace(/\n/g, "<br>");
  btn.appendChild(label);

  btn.addEventListener("click", () => {
    console.log("[CLICK] front", service.key, "name", service.name, "label", service.label, "theme", service.theme);
    if (interactionLocked) {
      return;
    }
    if (!backend || typeof backend.selectService !== "function") {
      return;
    }
    lockInteractions();
    backend.selectService(service.key);
  });

  return btn;
}

function renderServices(state) {
  serviceGrid.innerHTML = "";
  const services = mapServicesForRender(state);
  for (const service of services) {
    serviceGrid.appendChild(createServiceButton(service, state.activeService));
  }

  const pauseInline = services.length % 2 === 1;
  pauseButton.classList.toggle("pause-inline", pauseInline);
  pauseButton.classList.toggle("pause-wide", !pauseInline);
  serviceGrid.appendChild(pauseButton);
}

function renderPause(state) {
  const isPause = state.mode === "pause";
  const pauseState = state.pauseState || {};
  const isFree = pauseState.isFree || pauseState.status === "free";
  const label = pauseState.label || (isFree ? "TEKIN PAUZA" : "PAUZA");
  const subText = pauseState.subText || pauseState.remainingText || pauseState.timerText || "";

  pauseButton.classList.toggle("is-active", isPause);
  pauseButton.classList.toggle("pause-free", isPause && isFree);
  pauseButton.classList.toggle("pause-paid", isPause && !isFree);

  pauseText.textContent = label;
  pauseSub.textContent = subText;

  const iconUrl = pauseState.iconUrl || state.pauseIconUrl || fallbackPauseIcon;
  if (pauseIconLeft) pauseIconLeft.src = iconUrl;
  if (pauseIconRight) pauseIconRight.src = iconUrl;
}

function render(state) {
  latestState = state;
  if (!settings) {
    settings = _normalize_front_settings(_derive_settings_from_state(state));
  }
  if (state && typeof state.debug !== "undefined") {
    isDebug = !!state.debug;
  }
   if (Array.isArray(state.admin_pins)) {
    allowedPins = state.admin_pins.filter(Boolean);
  }
  renderHeader(state);
  renderServices(state);
  renderPause(state);
}

function startAdminHold() {
  clearAdminHold();
  console.log("[PAUSE] admin hold timer start", ADMIN_HOLD_MS, "ms");
  adminHoldTimer = setTimeout(() => {
    handleAdminHoldTrigger(true);
  }, ADMIN_HOLD_MS);
}

function handleAdminHoldTrigger(fromTimer = false) {
  console.log("[PAUSE] admin hold trigger", { fromTimer, stopPressed });
  clearAdminHold();
  // Even if stopPressed was flipped by mouseup, we still open the modal after timer.
  stopPressed = false;
  openPinModal();
  if (backend && typeof backend.stopReleased === "function") {
    backend.stopReleased();
  }
}

function clearAdminHold() {
  if (adminHoldTimer) {
    clearTimeout(adminHoldTimer);
    adminHoldTimer = null;
  }
}

function resetPauseTaps() {
  pauseTapCount = 0;
  if (pauseTapTimer) {
    clearTimeout(pauseTapTimer);
    pauseTapTimer = null;
  }
}

function registerPauseTap() {
  pauseTapCount += 1;
  console.log("[PAUSE] tap count", pauseTapCount);
  if (pauseTapTimer) {
    clearTimeout(pauseTapTimer);
  }
  pauseTapTimer = setTimeout(() => {
    resetPauseTaps();
    console.log("[PAUSE] tap window expired");
  }, ADMIN_MULTI_TAP_WINDOW_MS);

  if (pauseTapCount >= ADMIN_MULTI_TAP_COUNT) {
    resetPauseTaps();
    console.log("[PAUSE] multi-tap detected -> " + (isDebug ? "open ADMIN" : "open PIN modal"));
    if (isDebug) {
      window.location.href = "admin.html";
    } else {
      openPinModal();
      if (backend && typeof backend.stopReleased === "function") {
        backend.stopReleased();
      }
    }
  }
}

function startPausePress() {
  if (stopPressed) {
    console.log("[PAUSE] startPausePress ignored because stopPressed already true");
    return;
  }
  stopPressed = true;
  console.log("[PAUSE] startPausePress -> stopPressed true");
  startAdminHold();
  if (backend && typeof backend.stopPressed === "function") {
    console.log("[PAUSE] backend.stopPressed()");
    backend.stopPressed();
  }
}

function stopPausePress() {
  if (!stopPressed) {
    clearAdminHold();
    return;
  }
  registerPauseTap();
  stopPressed = false;
  clearAdminHold();
  if (backend && typeof backend.stopReleased === "function") {
    console.log("[PAUSE] backend.stopReleased()");
    backend.stopReleased();
  }
}

function initActions() {
  topPanel.addEventListener("click", () => {
    safeAddMoney();
  });

  pauseButton.addEventListener("mousedown", startPausePress);
  pauseButton.addEventListener("touchstart", startPausePress, { passive: true });

  pauseButton.addEventListener("mouseup", stopPausePress);
  pauseButton.addEventListener("mouseleave", stopPausePress);
  pauseButton.addEventListener("touchend", stopPausePress, { passive: true });
  pauseButton.addEventListener("touchcancel", stopPausePress, { passive: true });

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && (e.key === "r" || e.key === "R")) {
      e.preventDefault();
      window.location.reload();
      return;
    }
    if (!e.repeat && (e.key === "Enter" || e.key === "NumpadEnter")) {
      safeAddMoney();
    }
  });

  pinSubmit.addEventListener("click", handlePinSubmit);
  pinClose.addEventListener("click", closePinModal);
  pinClear.addEventListener("click", clearPin);
  
  pinKeys.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      addPinDigit(e.target.dataset.key);
    });
  });
}

let pinValue = "";

function addPinDigit(digit) {
  if (pinValue.length < 6) {
    pinValue += digit;
    updatePinDisplay();
    pinError.textContent = "";
  }
}

function clearPin() {
  pinValue = "";
  updatePinDisplay();
  pinError.textContent = "";
}

function updatePinDisplay() {
  const filled = pinValue.length;
  const dots = Array(6).fill("•")
    .map((d, i) => i < filled ? "●" : "•")
    .join(" ");
  pinDots.textContent = dots;
}

function toggleModal(modal, open) {
  modal.setAttribute("aria-hidden", open ? "false" : "true");
}

function openPinModal() {
  pinError.textContent = "";
  pinValue = "";
  updatePinDisplay();
  toggleModal(pinModal, true);
}

function closePinModal() {
  toggleModal(pinModal, false);
  pinValue = "";
}

function handlePinSubmit() {
  const pins = (allowedPins && allowedPins.length > 0)
    ? allowedPins
    : [settings?.pin, settings?.pin2].filter(Boolean);
  if (!pins.includes(pinValue)) {
    pinError.textContent = "Noto'g'ri PIN";
    pinValue = "";
    updatePinDisplay();
    return;
  }
  closePinModal();
  // Redirect to admin.html after successful PIN entry
  window.location.href = "admin.html";
}

function initWebChannel() {
  if (!window.qt || !qt.webChannelTransport) {
    setTimeout(initWebChannel, 200);
    return;
  }

  new QWebChannel(qt.webChannelTransport, (channel) => {
    backend = channel.objects.backend;

    refreshSettingsFromBackend();

    if (backend && backend.stateChanged) {
      backend.stateChanged.connect((payload) => {
        try {
          const state = parsePayload(payload);
          if (state) {
            render(state);
          }
        } catch (e) {
          console.error("stateChanged parse error", e);
        }
      });
    }

    requestState();
    setInterval(requestState, 700);
  });
}

initActions();
initWebChannel();
