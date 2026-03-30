let backend = null;
let latestState = null;

const topPanel = document.getElementById("topPanel");
const headerTitle = document.getElementById("headerTitle");
const headerMain = document.getElementById("headerMain");
const serviceGrid = document.getElementById("serviceGrid");
const pauseButton = document.getElementById("pauseButton");
const pauseIconLeft = document.getElementById("pauseIconLeft");
const pauseIconRight = document.getElementById("pauseIconRight");

const fallbackPauseIcon = encodeURI("../icons/⛔.png");

let stopPressed = false;

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

  if (state.mode === "idle") {
    headerTitle.textContent = "BALANS";
    headerTitle.style.color = color;
    headerMain.innerHTML = `${state.balanceText}<span class="unit">SO'M</span>`;
    headerMain.style.color = color;
    return;
  }

  headerTitle.textContent = state.title || "";
  headerTitle.style.color = color;
  headerMain.textContent = state.mainText || "00:00";
  headerMain.style.color = color;
}

function createServiceButton(service, activeKey) {
  const btn = document.createElement("button");
  btn.type = "button";
  const theme = service.theme || "suv";
  btn.className = `service-btn theme-${theme}`;
  if (activeKey && service.key === activeKey) {
    btn.classList.add("is-active");
  }

  if (service.iconUrl) {
    const img = document.createElement("img");
    img.src = service.iconUrl;
    img.alt = service.label;
    btn.appendChild(img);
  }

  const label = document.createElement("span");
  label.className = "service-label";
  label.innerHTML = (service.label || service.key || "").replace(/\n/g, "<br>");
  btn.appendChild(label);

  btn.addEventListener("click", () => {
    if (!backend || typeof backend.selectService !== "function") {
      return;
    }
    backend.selectService(service.key);
  });

  return btn;
}

function renderServices(state) {
  serviceGrid.innerHTML = "";
  const services = state.services || [];
  for (const service of services) {
    serviceGrid.appendChild(createServiceButton(service, state.activeService));
  }
}

function renderPause(state) {
  const isPause = state.mode === "pause";
  pauseButton.classList.toggle("is-active", isPause);

   const iconUrl = state.pauseIconUrl || fallbackPauseIcon;
   if (pauseIconLeft) {
     pauseIconLeft.src = iconUrl;
   }
   if (pauseIconRight) {
     pauseIconRight.src = iconUrl;
   }
}

function render(state) {
  latestState = state;
  renderHeader(state);
  renderServices(state);
  renderPause(state);
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

  const press = () => {
    if (!backend || stopPressed) {
      return;
    }
    stopPressed = true;
    if (typeof backend.stopPressed === "function") {
      backend.stopPressed();
    }
  };

  const release = () => {
    if (!backend || !stopPressed) {
      return;
    }
    stopPressed = false;
    if (typeof backend.stopReleased === "function") {
      backend.stopReleased();
    }
  };

  pauseButton.addEventListener("mousedown", press);
  pauseButton.addEventListener("touchstart", press, { passive: true });

  pauseButton.addEventListener("mouseup", release);
  pauseButton.addEventListener("mouseleave", release);
  pauseButton.addEventListener("touchend", release, { passive: true });
  pauseButton.addEventListener("touchcancel", release, { passive: true });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === "NumpadEnter") {
      if (backend && latestState && latestState.canAddMoney && typeof backend.addMoney === "function") {
        backend.addMoney();
      }
    }
  });
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
