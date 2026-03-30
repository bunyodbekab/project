const BUTTON_COUNT = 7;
const ICON_OPTIONS = [
  { value: 'suv.png', emoji: '🌊', label: 'Suv', theme: 'suv' },
  { value: 'osmos.png', emoji: '💧', label: 'Osmos', theme: 'osmos' },
  { value: 'aktiv.png', emoji: '🧪', label: 'Aktiv', theme: 'aktiv' },
  { value: 'pena.png', emoji: '🫧', label: 'Pena', theme: 'pena' },
  { value: 'nano.png', emoji: '✨', label: 'Nano', theme: 'nano' },
  { value: 'vosk.png', emoji: '🛡️', label: 'Vosk', theme: 'vosk' },
  { value: 'quritish.png', emoji: '💨', label: 'Quritish', theme: 'quritish' }
];

let bridge;
let kbdInput = '';
let activeInput = null;

window.addEventListener('load', () => {
  initWebChannel();
});

function initWebChannel() {
  if (!window.qt || !qt.webChannelTransport) {
    setTimeout(initWebChannel, 200);
    return;
  }

  new QWebChannel(qt.webChannelTransport, (channel) => {
    bridge = channel.objects.backend;
    if (bridge) {
      initAdmin();
    }
  });
}

function initAdmin() {
  loadSettings();
  setupEventListeners();
  loadTotalEarned();
  setupVirtualKeyboard();
}

function loadTotalEarned() {
  if (bridge && bridge.getState) {
    bridge.getState((state) => {
      try {
        const stateObj = JSON.parse(state);
        const total = stateObj.total_earned || 0;
        document.getElementById('totalEarned').textContent = 'Jami: ' + total.toLocaleString('uz-UZ') + " so'm";
      } catch (e) {
        console.log('Could not parse state', e);
      }
    });
  }
}

function loadSettings() {
  const stored = JSON.parse(localStorage.getItem('moyka.settings.v1') || '{}');
  
  if (bridge && bridge.getSettings) {
    bridge.getSettings((settings) => {
      const normalized = _normalize_front_settings(settings);
      hydrateAdminForm(normalized);
    });
  } else {
    hydrateAdminForm(stored);
  }
}

function _normalize_front_settings(settings) {
  if (!settings) return {};
  return {
    pin: settings.pin ?? settings.PIN ?? '1234',
    buttonCount: BUTTON_COUNT,
    showIcons: settings.showIcons ?? settings.show_icons ?? true,
    freePause: parseInt(settings.freePause ?? settings.free_pause ?? settings.pause?.freeSeconds ?? 5) || 5,
    paidPause: parseInt(settings.paidPause ?? settings.paid_pause ?? settings.pause?.paidSecondsPer5000 ?? 120) || 120,
    services: settings.services ?? settings.service_list ?? []
  };
}

function hydrateAdminForm(settings) {
  document.getElementById('adminPin').value = settings.pin || '1234';
  document.getElementById('toggleIcons').checked = settings.showIcons !== false;
  document.getElementById('freePause').value = settings.freePause || 5;
  document.getElementById('paidPause').value = settings.paidPause || 120;
  
  renderServiceConfigList(settings.services || []);
}

function renderServiceConfigList(services) {
  const list = document.getElementById('serviceConfigList');
  list.innerHTML = '';
  
  const count = BUTTON_COUNT;
  
  for (let i = 0; i < count; i++) {
    const service = services[i] || {
      name: `Xizmat ${i + 1}`,
      icon: 'suv.png',
      secondsPer5000: 120,
      theme: 'suv',
      active: true
    };
    
    const row = document.createElement('div');
    row.className = 'service-row';
    
    // Build custom select UI for icons
    const currentIcon = ICON_OPTIONS.find((ic) => ic.value === service.icon) || ICON_OPTIONS[0];
    const optionsHTML = ICON_OPTIONS.map((icon) => {
      const selected = service.icon === icon.value ? 'data-selected="true"' : '';
      return `<button type="button" class="select-option" data-value="${icon.value}" data-theme="${icon.theme}" ${selected}>${icon.emoji} ${icon.label}</button>`;
    }).join('');
    
    row.innerHTML = `
      <input type="text" class="service-name" value="${service.name || ''}" placeholder="Xizmat nomi" />
      <div class="custom-select" data-value="${currentIcon.value}">
        <button type="button" class="custom-select-toggle">${currentIcon.emoji} ${currentIcon.label}</button>
        <div class="custom-select-options">${optionsHTML}</div>
      </div>
      <input type="hidden" class="service-icon-value" value="${currentIcon.value}" data-theme="${currentIcon.theme}" />
      <input type="number" class="service-duration" value="${service.secondsPer5000 || 120}" min="1" />
      <div class="service-toggle">
        <input type="checkbox" class="service-active" ${service.active !== false ? 'checked' : ''} />
      </div>
    `;
    list.appendChild(row);
    row.querySelectorAll('input').forEach((el) => {
      el.addEventListener('focus', () => {
        activeInput = el;
        updateKeyboardDisplay();
      });
    });

    attachCustomSelect(row);
  }

  if (!activeInput || !document.body.contains(activeInput)) {
    activeInput = document.getElementById('adminPin');
    updateKeyboardDisplay();
  }
}

function attachCustomSelect(row) {
  const select = row.querySelector('.custom-select');
  const toggle = row.querySelector('.custom-select-toggle');
  const options = row.querySelectorAll('.select-option');
  const hidden = row.querySelector('.service-icon-value');
  if (!select || !toggle || !hidden) return;

  toggle.addEventListener('click', (e) => {
    e.stopPropagation();
    document.querySelectorAll('.custom-select.open').forEach((el) => {
      if (el !== select) el.classList.remove('open');
    });
    select.classList.toggle('open');
  });

  options.forEach((opt) => {
    opt.addEventListener('click', (e) => {
      e.stopPropagation();
      const val = opt.getAttribute('data-value');
      const theme = opt.getAttribute('data-theme');
      hidden.value = val;
      hidden.setAttribute('data-theme', theme || 'suv');
      toggle.textContent = opt.textContent;
      select.setAttribute('data-value', val);
      select.classList.remove('open');
    });
  });

  document.addEventListener('click', () => {
    select.classList.remove('open');
  });
}

function setupEventListeners() {
  document.getElementById('adminClose').addEventListener('click', goBack);
  document.getElementById('adminSave').addEventListener('click', saveSettings);
  document.getElementById('resetDefaults').addEventListener('click', resetToDefaults);
  document.getElementById('adminPin').addEventListener('focus', () => {
    activeInput = document.getElementById('adminPin');
    updateKeyboardDisplay();
  });
  document.getElementById('adminPin').addEventListener('input', () => {
    kbdInput = document.getElementById('adminPin').value.slice(0, 6);
    document.getElementById('adminPin').value = kbdInput;
    updateKeyboardDisplay();
  });
}

function setupVirtualKeyboard() {
  const kbdKeys = document.querySelectorAll('.kbd-key');
  kbdKeys.forEach(btn => {
    btn.addEventListener('click', () => {
      handleVirtualKey(btn.getAttribute('data-key'));
    });
  });

  document.addEventListener('focusin', (e) => {
    if (e.target && e.target.tagName === 'INPUT') {
      activeInput = e.target;
      updateKeyboardDisplay();
    }
  });

  activeInput = document.getElementById('adminPin');
  updateKeyboardDisplay();
}

function updateKeyboardDisplay() {
  const display = document.getElementById('keyboardDisplay');
  if (!activeInput) {
    display.textContent = 'Fokus: yo\'q';
    return;
  }

  if (activeInput.id === 'adminPin') {
    const value = activeInput.value || '';
    const masked = Array(6).fill('○').map((c, i) => (i < value.length ? '●' : '○')).join('');
    display.textContent = `PIN: ${masked}`;
  } else {
    const preview = (activeInput.value || '').toString();
    display.textContent = `${activeInput.placeholder || 'Matn'}: ${preview}`;
  }
}

function handleVirtualKey(key) {
  if (!key) return;
  if (!activeInput) {
    activeInput = document.getElementById('adminPin');
  }
  if (!activeInput) return;

  if (activeInput.tagName !== 'INPUT') {
    return;
  }

  if (key === 'CLEAR') {
    activeInput.value = '';
  } else if (key === 'BACKSPACE') {
    activeInput.value = activeInput.value.slice(0, -1);
  } else if (key === 'SPACE') {
    activeInput.value += ' ';
  } else {
    if (activeInput.type === 'number' && !/^[0-9.]$/.test(key)) {
      return;
    }
    if (activeInput.id === 'adminPin' && activeInput.value.length >= 6) {
      return;
    }
    activeInput.value += key;
  }

  if (activeInput.id === 'adminPin') {
    kbdInput = activeInput.value;
  }
  updateKeyboardDisplay();
}

function collectServices() {
  const rows = document.querySelectorAll('.service-row');
  const services = [];
  
  rows.forEach((row) => {
    services.push({
      name: row.querySelector('.service-name').value,
      icon: row.querySelector('.service-icon-value').value,
      secondsPer5000: parseInt(row.querySelector('.service-duration').value) || 120,
      theme: (row.querySelector('.service-icon-value').getAttribute('data-theme') || 'suv').replace('.png', ''),
      active: row.querySelector('.service-active').checked
    });
  });
  
  return services;
}

function saveSettings() {
  const freePause = parseInt(document.getElementById('freePause').value) || 5;
  const paidPause = parseInt(document.getElementById('paidPause').value) || 120;
  const settings = {
    pin: document.getElementById('adminPin').value || '1234',
    buttonCount: BUTTON_COUNT,
    totalButtons: BUTTON_COUNT,
    showIcons: document.getElementById('toggleIcons').checked,
    show_icons: document.getElementById('toggleIcons').checked,
    freePause,
    free_pause: freePause,
    paidPause,
    paid_pause: paidPause,
    pause: { freeSeconds: freePause, paidSecondsPer5000: paidPause },
    services: collectServices()
  };
  
  localStorage.setItem('moyka.settings.v1', JSON.stringify(settings));
  
  if (bridge && bridge.updateFrontSettings) {
    bridge.updateFrontSettings(settings);
  }
  
  const status = document.getElementById('adminStatus');
  status.textContent = 'Saqlandi! ✓';
  setTimeout(() => {
    status.textContent = '';
  }, 2000);
}

function resetToDefaults() {
  if (confirm('Barcha sozlamalar standartga qaytadi. Rostmi?')) {
    const defaults = {
      pin: '1234',
      buttonCount: BUTTON_COUNT,
      totalButtons: BUTTON_COUNT,
      showIcons: true,
      show_icons: true,
      freePause: 5,
      paidPause: 120,
      pause: { freeSeconds: 5, paidSecondsPer5000: 120 },
      services: [
        { name: 'SUV', icon: 'suv.png', secondsPer5000: 120, theme: 'suv', active: true },
        { name: 'OSMOS', icon: 'osmos.png', secondsPer5000: 120, theme: 'osmos', active: true },
        { name: 'AKTIV', icon: 'aktiv.png', secondsPer5000: 120, theme: 'aktiv', active: true },
        { name: 'PENA', icon: 'pena.png', secondsPer5000: 120, theme: 'pena', active: true },
        { name: 'NANO', icon: 'nano.png', secondsPer5000: 120, theme: 'nano', active: true },
        { name: 'VOSK', icon: 'vosk.png', secondsPer5000: 120, theme: 'vosk', active: true },
        { name: 'QURITISH', icon: 'quritish.png', secondsPer5000: 120, theme: 'quritish', active: true }
      ]
    };
    
    localStorage.setItem('moyka.settings.v1', JSON.stringify(defaults));
    if (bridge && bridge.updateFrontSettings) {
      bridge.updateFrontSettings(defaults);
    }
    hydrateAdminForm(defaults);
  }
}

function goBack() {
  window.location.href = 'index.html';
}
