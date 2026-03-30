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
const SETTINGS_KEY = "moyka.settings.v1";
const ADMIN_HOLD_MS = 2000;
const INTERACTION_LOCK_MS = 1000;

const DEFAULT_SETTINGS = {
  pin: "1234",
  buttonCount: 7,
  showIcons: true,
  freePause: 5,
  paidPause: 120,
  services: [
    { name: "SUV", icon: "suv.png", secondsPer5000: 120, theme: "suv", active: true },
    { name: "OSMOS", icon: "osmos.png", secondsPer5000: 120, theme: "osmos", active: true },
    { name: "AKTIV", icon: "aktiv.png", secondsPer5000: 120, theme: "aktiv", active: true },
    { name: "PENA", icon: "pena.png", secondsPer5000: 120, theme: "pena", active: true },
    { name: "NANO", icon: "nano.png", secondsPer5000: 120, theme: "nano", active: true },
    { name: "VOSK", icon: "vosk.png", secondsPer5000: 120, theme: "vosk", active: true },
    { name: "QURITISH", icon: "quritish.png", secondsPer5000: 120, theme: "quritish", active: true },
  ],
};

let settings = loadSettings();
let stopPressed = false;
let adminHoldTimer = null;
let interactionLocked = false;
let interactionLockTimer = null;

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

function _normalize_front_settings(settings) {
  if (!settings) settings = {};
  return {
    pin: settings.pin ?? settings.PIN ?? "1234",
    buttonCount: DEFAULT_SETTINGS.buttonCount,
    showIcons: settings.showIcons ?? settings.show_icons ?? true,
    freePause: settings.freePause ?? settings.free_pause ?? settings.pause?.freeSeconds ?? DEFAULT_SETTINGS.freePause,
    paidPause: settings.paidPause ?? settings.paid_pause ?? settings.pause?.paidSecondsPer5000 ?? DEFAULT_SETTINGS.paidPause,
    services: settings.services ?? settings.service_list ?? DEFAULT_SETTINGS.services
  };
}

function loadSettings() {
  try {
    const stored = localStorage.getItem(SETTINGS_KEY);
    if (stored) {
      return _normalize_front_settings(JSON.parse(stored));
    }
  } catch (e) {
    console.warn("settings parse error", e);
  }
  return _normalize_front_settings(DEFAULT_SETTINGS);
}

function saveSettings() {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch (e) {
    console.warn("settings save error", e);
  }

  if (backend && typeof backend.updateFrontSettings === "function") {
    backend.updateFrontSettings(settings);
  }
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
  const stateServices = Array.isArray(state.services) ? state.services : [];
  const merged = settings.services.map((cfg, idx) => {
    const fromState = stateServices.find((s) => s.key === cfg.name || s.name === cfg.name) || stateServices[idx] || {};

    const key = fromState.key || cfg.key || cfg.name || `service-${idx + 1}`;
    const label = fromState.label || cfg.name || key;
    const name = fromState.name || cfg.name || key;

    const showIcon = settings.showIcons && cfg.showIcon !== false;
    const iconFile = cfg.icon || fromState.icon;
    const iconUrl = showIcon ? resolveIconUrl(iconFile) : null;
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
  renderHeader(state);
  renderServices(state);
  renderPause(state);
}

function startAdminHold() {
  clearAdminHold();
  adminHoldTimer = setTimeout(() => {
    stopPausePress();
    openPinModal();
  }, ADMIN_HOLD_MS);
}

function clearAdminHold() {
  if (adminHoldTimer) {
    clearTimeout(adminHoldTimer);
    adminHoldTimer = null;
  }
}

function startPausePress() {
  if (stopPressed) return;
  stopPressed = true;
  startAdminHold();
  if (backend && typeof backend.stopPressed === "function") {
    backend.stopPressed();
  }
}

function stopPausePress() {
  if (!stopPressed) {
    clearAdminHold();
    return;
  }
  stopPressed = false;
  clearAdminHold();
  if (backend && typeof backend.stopReleased === "function") {
    backend.stopReleased();
  }
}

function initActions() {
  topPanel.addEventListener("click", () => {
    if (!backend || !latestState || !latestState.canAddMoney) {
      return;
    }
    if (typeof backend.addMoney === "function") {
      backend.addMoney();
    }
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
    if (e.key === "Enter" || e.key === "NumpadEnter") {
      if (backend && latestState && latestState.canAddMoney && typeof backend.addMoney === "function") {
        backend.addMoney();
      }
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
  if (pinValue !== settings.pin) {
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
