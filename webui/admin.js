const BUTTON_COUNT = 7;
const ICON_OPTIONS = [
  "suv.png",
  "osmos.png",
  "aktiv.png",
  "pena.png",
  "nano.png",
  "vosk.png",
  "quritish.png",
];

const THEME_OPTIONS = [
  { value: "suv", swatch: "color-suv" },
  { value: "osmos", swatch: "color-osmos" },
  { value: "aktiv", swatch: "color-aktiv" },
  { value: "pena", swatch: "color-pena" },
  { value: "nano", swatch: "color-nano" },
  { value: "vosk", swatch: "color-vosk" },
  { value: "quritish", swatch: "color-quritish" },
];

let bridge = null;
let activeInput = null;
let kbdInput = "";
let lastConfig = null;

window.addEventListener("load", () => {
  initWebChannel();
});

function initWebChannel() {
  if (!window.qt || !qt.webChannelTransport) {
    // Browser/dev fallback: API orqali ishlaydi.
    initAdmin();
    return;
  }

  new QWebChannel(qt.webChannelTransport, (channel) => {
    bridge = channel.objects.backend;
    initAdmin();
  });
}

function initAdmin() {
  loadSettings();
  setupEventListeners();
  loadTotalEarned();
  setupVirtualKeyboard();
}

function parsePayload(payload) {
  if (!payload) return null;
  if (typeof payload === "string") {
    try {
      return JSON.parse(payload);
    } catch (e) {
      return null;
    }
  }
  return payload;
}

function toInt(value, fallback, minValue = 0) {
  const parsed = parseInt(value, 10);
  if (Number.isNaN(parsed)) return fallback;
  return Math.max(minValue, parsed);
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function iconPath(iconFile) {
  return `../icons/${encodeURIComponent(iconFile || "")}`;
}

function themeExists(theme) {
  return THEME_OPTIONS.some((t) => t.value === theme);
}

function buildPlaceholderService(index) {
  const key = `XIZMAT${index + 1}`;
  const icon = ICON_OPTIONS[index] || ICON_OPTIONS[0];
  const theme = (THEME_OPTIONS[index] || THEME_OPTIONS[0]).value;
  return {
    key,
    name: key,
    label: `XIZMAT ${index + 1}`,
    icon,
    theme,
    active: true,
    secondsPer5000: 120,
  };
}

function normalizeServices(rawServices) {
  let services = rawServices || [];
  if (!Array.isArray(services) && services && typeof services === "object") {
    services = Object.entries(services).map(([name, cfg]) => ({ name, ...(cfg || {}) }));
  }
  if (!Array.isArray(services)) {
    services = [];
  }

  const normalized = services.map((svc, idx) => {
    const key = String(svc.name || svc.key || `XIZMAT${idx + 1}`);
    const pricePerSec = Number(svc.price_per_sec || svc.pricePerSec || 0);
    const secondsFromPrice = pricePerSec > 0 ? Math.ceil(5000 / Math.max(1, pricePerSec)) : null;
    const secondsPer5000 = toInt(
      svc.secondsPer5000 ?? svc.seconds_per_5000 ?? secondsFromPrice ?? svc.duration,
      120,
      1
    );

    const icon = svc.icon || svc.icon_file || ICON_OPTIONS[idx] || ICON_OPTIONS[0];
    const theme = themeExists(svc.theme) ? svc.theme : (THEME_OPTIONS[idx] || THEME_OPTIONS[0]).value;

    return {
      key,
      name: key,
      label: svc.label || svc.display_name || key,
      icon,
      theme,
      active: svc.active !== false,
      secondsPer5000,
    };
  });

  const result = normalized.slice(0, BUTTON_COUNT);
  while (result.length < BUTTON_COUNT) {
    result.push(buildPlaceholderService(result.length));
  }

  return result;
}

function _normalize_front_settings(raw) {
  const cfg = raw || {};
  return {
    pin: String(cfg.pin ?? cfg.PIN ?? cfg.admin_pin ?? "1234"),
    pin2: String(cfg.pin2 ?? cfg.pin_alt ?? cfg.admin_pin_alt ?? cfg.pinAlt ?? "5678"),
    showIcons: cfg.showIcons ?? cfg.show_icons ?? true,
    freePause: toInt(cfg.freePause ?? cfg.free_pause ?? cfg.pause?.freeSeconds, 5, 0),
    paidPause: toInt(cfg.paidPause ?? cfg.paid_pause ?? cfg.pause?.paidSecondsPer5000, 120, 1),
    bonusPercent: toInt(cfg.bonusPercent ?? cfg.bonus?.percent, 0, 0),
    bonusThreshold: toInt(cfg.bonusThreshold ?? cfg.bonus?.threshold, 0, 0),
    services: normalizeServices(cfg.services),
  };
}

function loadTotalEarned() {
  const update = (obj) => {
    const total = obj?.total_earned || 0;
    document.getElementById("totalEarned").textContent =
      "Jami: " + total.toLocaleString("uz-UZ") + " so'm";
  };

  if (bridge && bridge.getState) {
    bridge.getState((state) => {
      const parsed = parsePayload(state);
      if (parsed) update(parsed);
    });
    return;
  }

  fetch("/api/state")
    .then((r) => r.json())
    .then((obj) => update(obj))
    .catch(() => {});
}

function loadSettings() {
  const hydrate = (configOrSettings, source = "") => {
    const parsed = parsePayload(configOrSettings) || {};
    if (parsed && typeof parsed === "object") {
      lastConfig = parsed;
    }
    const normalized = _normalize_front_settings(parsed);
    hydrateAdminForm(normalized);
    if (source) {
      setStatus(`Sozlamalar: ${source}`, "info", 1500);
    }
  };

  if (bridge && bridge.getSettings) {
    bridge.getSettings((payload) => {
      const parsed = parsePayload(payload);
      if (parsed) {
        hydrate(parsed, "backend");
      } else {
        setStatus("Sozlamalarni o'qib bo'lmadi", "error", 2000);
      }
    });
    return;
  }

  fetch("/api/config")
    .then((r) => {
      if (!r.ok) throw new Error("config xato");
      return r.json();
    })
    .then((cfg) => hydrate(cfg, "config.json"))
    .catch(() => {
      setStatus("Config topilmadi", "error", 2500);
    });
}

function hydrateAdminForm(settings) {
  document.getElementById("adminPin").value = settings.pin || "1234";
  document.getElementById("adminPin2").value = settings.pin2 || "5678";
  document.getElementById("toggleIcons").checked = settings.showIcons !== false;
  document.getElementById("freePause").value = settings.freePause || 5;
  document.getElementById("paidPause").value = settings.paidPause || 120;
  document.getElementById("bonusPercent").value = settings.bonusPercent || 0;
  document.getElementById("bonusThreshold").value = settings.bonusThreshold || 0;

  renderServiceConfigList(settings.services || []);
}

function renderIconToggle(icon) {
  return `<img src="${iconPath(icon)}" alt="" class="icon-preview" />`;
}

function renderThemeToggle(theme) {
  const selected = THEME_OPTIONS.find((t) => t.value === theme) || THEME_OPTIONS[0];
  return `<span class="theme-dot ${selected.swatch}"></span>`;
}

function renderServiceConfigList(services) {
  const list = document.getElementById("serviceConfigList");
  list.innerHTML = "";

  const normalized = normalizeServices(services);

  for (let i = 0; i < BUTTON_COUNT; i++) {
    const service = normalized[i] || buildPlaceholderService(i);
    const safeLabel = escapeHtml(service.label || service.key);

    const iconOptionsHtml = ICON_OPTIONS.map((icon) => {
      const selected = icon === service.icon ? 'data-selected="true"' : "";
      return `
        <button type="button" class="select-option icon-option" data-value="${icon}" ${selected} aria-label="${icon}">
          <img src="${iconPath(icon)}" alt="" />
        </button>
      `;
    }).join("");

    const themeOptionsHtml = THEME_OPTIONS.map((theme) => {
      const selected = theme.value === service.theme ? 'data-selected="true"' : "";
      return `
        <button type="button" class="select-option theme-option" data-value="${theme.value}" ${selected} aria-label="${theme.value}">
          <span class="theme-dot ${theme.swatch}"></span>
        </button>
      `;
    }).join("");

    const row = document.createElement("div");
    row.className = "service-row";
    row.dataset.serviceKey = service.key;
    row.dataset.theme = service.theme;

    row.innerHTML = `
      <input type="hidden" class="service-key" value="${service.key}" />
      <input type="text" class="service-name" value="${safeLabel}" placeholder="Xizmat nomi" />

      <div class="custom-select icon-select" data-value="${service.icon}">
        <button type="button" class="custom-select-toggle icon-toggle" aria-label="Icon tanlash">
          ${renderIconToggle(service.icon)}
        </button>
        <div class="custom-select-options icon-options">${iconOptionsHtml}</div>
      </div>
      <input type="hidden" class="service-icon-value" value="${service.icon}" />

      <div class="custom-select theme-select" data-value="${service.theme}">
        <button type="button" class="custom-select-toggle theme-toggle" aria-label="Rang tanlash">
          ${renderThemeToggle(service.theme)}
        </button>
        <div class="custom-select-options theme-options">${themeOptionsHtml}</div>
      </div>
      <input type="hidden" class="service-theme-value" value="${service.theme}" />

      <input type="number" class="service-duration" value="${service.secondsPer5000}" min="1" />
      <div class="service-toggle">
        <input type="checkbox" class="service-active" ${service.active !== false ? "checked" : ""} />
      </div>
    `;

    list.appendChild(row);

    row.querySelectorAll("input").forEach((el) => {
      el.addEventListener("focus", () => {
        activeInput = el;
        updateKeyboardDisplay();
      });
    });

    attachRowCustomSelects(row);
    applyRowTheme(row);
  }

  if (!activeInput || !document.body.contains(activeInput)) {
    activeInput = document.getElementById("adminPin");
    updateKeyboardDisplay();
  }
}

function closeAllCustomSelects() {
  document.querySelectorAll(".custom-select.open").forEach((el) => {
    el.classList.remove("open");
  });
}

function markSelectOption(selectEl, value) {
  selectEl.querySelectorAll(".select-option").forEach((option) => {
    const isSelected = option.getAttribute("data-value") === value;
    if (isSelected) {
      option.setAttribute("data-selected", "true");
    } else {
      option.removeAttribute("data-selected");
    }
  });
}

function attachCustomSelect(selectEl, onSelect) {
  if (!selectEl) return;

  const toggle = selectEl.querySelector(".custom-select-toggle");
  const options = selectEl.querySelectorAll(".select-option");

  if (!toggle) return;

  toggle.addEventListener("click", (e) => {
    e.stopPropagation();
    const isOpen = selectEl.classList.contains("open");
    closeAllCustomSelects();
    if (!isOpen) {
      selectEl.classList.add("open");
    }
  });

  options.forEach((opt) => {
    opt.addEventListener("click", (e) => {
      e.stopPropagation();
      const value = opt.getAttribute("data-value");
      if (!value) return;
      onSelect(value, opt);
      markSelectOption(selectEl, value);
      selectEl.setAttribute("data-value", value);
      selectEl.classList.remove("open");
    });
  });
}

function attachRowCustomSelects(row) {
  const iconSelect = row.querySelector(".icon-select");
  const iconHidden = row.querySelector(".service-icon-value");
  const iconToggle = row.querySelector(".icon-toggle");

  const themeSelect = row.querySelector(".theme-select");
  const themeHidden = row.querySelector(".service-theme-value");
  const themeToggle = row.querySelector(".theme-toggle");

  attachCustomSelect(iconSelect, (value) => {
    if (iconHidden) iconHidden.value = value;
    if (iconToggle) iconToggle.innerHTML = renderIconToggle(value);
  });

  attachCustomSelect(themeSelect, (value) => {
    if (themeHidden) themeHidden.value = value;
    if (themeToggle) themeToggle.innerHTML = renderThemeToggle(value);
    row.dataset.theme = value;
    applyRowTheme(row);
  });
}

function applyRowTheme(row) {
  if (!row) return;
  const theme = row.dataset.theme || THEME_OPTIONS[0].value;
  THEME_OPTIONS.forEach((item) => row.classList.remove(`theme-${item.value}`));
  row.classList.add(`theme-${theme}`);
}

function setStatus(text, tone = "info", autoHideMs = 0) {
  const status = document.getElementById("adminStatus");
  if (!status) return;

  const colors = {
    success: "#22c55e",
    warn: "#f59e0b",
    error: "#ef4444",
    info: "#60a5fa",
  };
  const backgrounds = {
    success: "rgba(34,197,94,0.15)",
    warn: "rgba(245,158,11,0.2)",
    error: "rgba(239,68,68,0.18)",
    info: "rgba(96,165,250,0.18)",
  };

  status.textContent = text || "";
  status.style.visibility = text ? "visible" : "hidden";

  if (text) {
    const color = colors[tone] || colors.info;
    status.style.backgroundColor = backgrounds[tone] || backgrounds.info;
    status.style.borderColor = color;
    status.style.color = color;
  }

  if (autoHideMs > 0 && text) {
    setTimeout(() => {
      status.textContent = "";
      status.style.visibility = "hidden";
    }, autoHideMs);
  }
}

function mapExistingServices(rawServices) {
  if (rawServices && !Array.isArray(rawServices) && typeof rawServices === "object") {
    return JSON.parse(JSON.stringify(rawServices));
  }
  if (Array.isArray(rawServices)) {
    const mapped = {};
    rawServices.forEach((svc) => {
      if (!svc || typeof svc !== "object") return;
      const key = svc.name || svc.key;
      if (!key) return;
      mapped[key] = { ...svc };
    });
    return mapped;
  }
  return {};
}

function buildConfigPayload(settings) {
  const base = lastConfig && typeof lastConfig === "object" ? JSON.parse(JSON.stringify(lastConfig)) : {};
  const baseServices = mapExistingServices(base.services);

  const servicesObj = {};
  (settings.services || []).forEach((svc) => {
    const key = svc.name || svc.key;
    if (!key) return;

    const label = String(svc.label || svc.display_name || key);
    const seconds = toInt(svc.secondsPer5000 || svc.seconds_per_5000, 120, 1);
    const pricePerSec = Math.max(1, Math.ceil(5000 / Math.max(1, seconds)));
    const existing = baseServices[key] || {};

    servicesObj[key] = {
      ...existing,
      display_name: label,
      duration: toInt(svc.duration, seconds, 1),
      price_per_sec: pricePerSec,
      icon: String(svc.icon || existing.icon || ICON_OPTIONS[0]),
      theme: String(svc.theme || existing.theme || THEME_OPTIONS[0].value),
      active: svc.active !== false,
    };
  });

  return {
    ...base,
    admin_pin: settings.pin || "1234",
    admin_pin_alt: settings.pin2 || "5678",
    show_icons: settings.showIcons !== false,
    bonus: settings.bonus || { percent: 0, threshold: 0 },
    pause: settings.pause || { freeSeconds: 5, paidSecondsPer5000: 120 },
    services: servicesObj,
  };
}

function collectServices() {
  const rows = document.querySelectorAll(".service-row");
  const services = [];

  rows.forEach((row) => {
    const key = row.getAttribute("data-service-key") || row.querySelector(".service-key")?.value || "";
    const nameInput = row.querySelector(".service-name");
    const iconEl = row.querySelector(".service-icon-value");
    const themeEl = row.querySelector(".service-theme-value");
    const durationEl = row.querySelector(".service-duration");
    const activeEl = row.querySelector(".service-active");

    services.push({
      key,
      name: key,
      label: nameInput ? nameInput.value : key,
      display_name: nameInput ? nameInput.value : key,
      icon: iconEl ? iconEl.value : ICON_OPTIONS[0],
      theme: themeEl ? themeEl.value : THEME_OPTIONS[0].value,
      secondsPer5000: toInt(durationEl?.value, 120, 1),
      duration: toInt(durationEl?.value, 120, 1),
      active: activeEl ? activeEl.checked : true,
      showIcon: true,
    });
  });

  return services;
}

function collectFormSettings() {
  const freePause = toInt(document.getElementById("freePause").value, 5, 0);
  const paidPause = toInt(document.getElementById("paidPause").value, 120, 1);
  const bonusPercent = toInt(document.getElementById("bonusPercent").value, 0, 0);
  const bonusThreshold = toInt(document.getElementById("bonusThreshold").value, 0, 0);

  return {
    pin: document.getElementById("adminPin").value || "1234",
    pin2: document.getElementById("adminPin2").value || "5678",
    totalButtons: BUTTON_COUNT,
    buttonCount: BUTTON_COUNT,
    showIcons: document.getElementById("toggleIcons").checked,
    show_icons: document.getElementById("toggleIcons").checked,
    freePause,
    free_pause: freePause,
    paidPause,
    paid_pause: paidPause,
    pause: { freeSeconds: freePause, paidSecondsPer5000: paidPause },
    bonusPercent,
    bonusThreshold,
    bonus: { percent: bonusPercent, threshold: bonusThreshold },
    services: collectServices(),
  };
}

function saveSettings() {
  const settings = collectFormSettings();

  if (bridge && bridge.updateFrontSettings) {
    bridge.updateFrontSettings(settings);
    lastConfig = buildConfigPayload(settings);
    setStatus("Saqlandi! ✓", "success", 2000);
    return;
  }

  const payload = buildConfigPayload(settings);
  fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
    .then((r) => r.json())
    .then((res) => {
      if (res?.config) {
        lastConfig = res.config;
      } else {
        lastConfig = payload;
      }
      setStatus("Saqlandi! ✓", "success", 2000);
    })
    .catch(() => {
      setStatus("Saqlashda xato", "error", 2500);
    });
}

function resetToDefaults() {
  if (!confirm("Barcha sozlamalar standartga qaytadi. Rostmi?")) {
    return;
  }

  if (bridge && bridge.resetConfigToDefaults) {
    bridge.resetConfigToDefaults(() => {
      loadSettings();
      setStatus("Standart sozlamalar tiklandi", "warn", 2000);
    });
    return;
  }

  fetch("/api/config/reset", { method: "POST" })
    .then((r) => r.json())
    .then((res) => {
      if (res?.config) {
        lastConfig = res.config;
      }
      const payload = res?.settings || res?.config || null;
      if (payload) {
        hydrateAdminForm(_normalize_front_settings(payload));
      }
      setStatus("Standart sozlamalar tiklandi", "warn", 2000);
    })
    .catch(() => {
      setStatus("Standartga qaytarishda xato", "error", 2500);
    });
}

function setupEventListeners() {
  document.getElementById("adminClose").addEventListener("click", goBack);
  document.getElementById("adminSave").addEventListener("click", saveSettings);
  document.getElementById("resetDefaults").addEventListener("click", resetToDefaults);

  document.getElementById("adminPin").addEventListener("focus", () => {
    activeInput = document.getElementById("adminPin");
    updateKeyboardDisplay();
  });
  document.getElementById("adminPin").addEventListener("input", () => {
    kbdInput = document.getElementById("adminPin").value.slice(0, 6);
    document.getElementById("adminPin").value = kbdInput;
    updateKeyboardDisplay();
  });

  document.getElementById("adminPin2").addEventListener("focus", () => {
    activeInput = document.getElementById("adminPin2");
    updateKeyboardDisplay();
  });
  document.getElementById("adminPin2").addEventListener("input", () => {
    const val = document.getElementById("adminPin2").value.slice(0, 6);
    document.getElementById("adminPin2").value = val;
    updateKeyboardDisplay();
  });

  document.addEventListener("click", () => {
    closeAllCustomSelects();
  });

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && (e.key === "r" || e.key === "R")) {
      e.preventDefault();
      window.location.reload();
    }
  });
}

function setupVirtualKeyboard() {
  const kbdKeys = document.querySelectorAll(".kbd-key");
  kbdKeys.forEach((btn) => {
    btn.addEventListener("click", () => {
      handleVirtualKey(btn.getAttribute("data-key"));
    });
  });

  document.addEventListener("focusin", (e) => {
    if (e.target && e.target.tagName === "INPUT") {
      activeInput = e.target;
      updateKeyboardDisplay();
    }
  });

  activeInput = document.getElementById("adminPin");
  updateKeyboardDisplay();
}

function updateKeyboardDisplay() {
  const display = document.getElementById("keyboardDisplay");
  if (!activeInput) {
    display.textContent = "Fokus: yo'q";
    return;
  }

  if (activeInput.id === "adminPin") {
    const value = activeInput.value || "";
    const masked = Array(6)
      .fill("○")
      .map((c, i) => (i < value.length ? "●" : "○"))
      .join("");
    display.textContent = `PIN: ${masked}`;
    return;
  }

  if (activeInput.id === "adminPin2") {
    const value = activeInput.value || "";
    const masked = Array(6)
      .fill("○")
      .map((c, i) => (i < value.length ? "●" : "○"))
      .join("");
    display.textContent = `PIN 2: ${masked}`;
    return;
  }

  const preview = (activeInput.value || "").toString();
  display.textContent = `${activeInput.placeholder || "Matn"}: ${preview}`;
}

function handleVirtualKey(key) {
  if (!key) return;
  if (!activeInput) {
    activeInput = document.getElementById("adminPin");
  }
  if (!activeInput || activeInput.tagName !== "INPUT") return;

  if (key === "CLEAR") {
    activeInput.value = "";
  } else if (key === "BACKSPACE") {
    activeInput.value = activeInput.value.slice(0, -1);
  } else if (key === "SPACE") {
    activeInput.value += " ";
  } else {
    if (activeInput.type === "number" && !/^[0-9]$/.test(key)) {
      return;
    }
    if ((activeInput.id === "adminPin" || activeInput.id === "adminPin2") && activeInput.value.length >= 6) {
      return;
    }
    activeInput.value += key;
  }

  if (activeInput.id === "adminPin") {
    kbdInput = activeInput.value;
  }
  updateKeyboardDisplay();
}

function goBack() {
  window.location.href = "index.html";
}
