const $ = id => document.getElementById(id);
const el = (tag, text, cls) => {
  const e = document.createElement(tag);
  if (text) e.textContent = text;
  if (cls) e.className = cls;
  return e;
};

// Theme switcher
function applyTheme(theme) {
  if (theme === 'auto') {
    document.documentElement.removeAttribute('data-theme');
  } else {
    document.documentElement.setAttribute('data-theme', theme);
  }
  // Update icon visibility
  ['light', 'dark', 'auto'].forEach(t => {
    const icon = $('theme-icon-' + t);
    if (icon) icon.classList.toggle('active', t === theme);
  });
  // Update dropdown active state
  const dropdown = $('theme-dropdown');
  if (dropdown) {
    dropdown.querySelectorAll('button').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.theme === theme);
    });
  }
}

function initTheme() {
  const saved = localStorage.getItem('ser2tcp_theme') || 'auto';
  const btn = $('theme-btn');
  const dropdown = $('theme-dropdown');
  if (btn && dropdown) {
    btn.onclick = e => {
      e.stopPropagation();
      dropdown.classList.toggle('open');
    };
    dropdown.querySelectorAll('button').forEach(b => {
      b.onclick = () => {
        const theme = b.dataset.theme;
        localStorage.setItem('ser2tcp_theme', theme);
        applyTheme(theme);
        dropdown.classList.remove('open');
      };
    });
    document.addEventListener('click', () => dropdown.classList.remove('open'));
  }
  applyTheme(saved);
}

// Apply theme immediately to avoid flash
(function() {
  const saved = localStorage.getItem('ser2tcp_theme');
  if (saved && saved !== 'auto') {
    document.documentElement.setAttribute('data-theme', saved);
  }
})();

// Hash password with SHA-256 and random salt (same format as server)
async function hashPassword(password) {
  const salt = Array.from(crypto.getRandomValues(new Uint8Array(16)))
    .map(b => b.toString(16).padStart(2, '0')).join('');
  const data = new TextEncoder().encode(salt + password);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hash = Array.from(new Uint8Array(hashBuffer))
    .map(b => b.toString(16).padStart(2, '0')).join('');
  return `sha256:${salt}:${hash}`;
}

let token = localStorage.getItem('ser2tcp_token');
let username = localStorage.getItem('ser2tcp_user');
let isAdmin = false;
let detectedPorts = [];
let usedPorts = [];  // [{address, port, index}] from status
let usedEndpoints = [];  // [{endpoint, index}] from status

function setCredentials(t, u) {
  token = t;
  username = u;
  if (t) {
    localStorage.setItem('ser2tcp_token', t);
    localStorage.setItem('ser2tcp_user', u);
  } else {
    localStorage.removeItem('ser2tcp_token');
    localStorage.removeItem('ser2tcp_user');
  }
  updateUserInfo();
}

function updateUserInfo() {
  const info = $('user-info');
  const name = $('user-name');
  if (username) {
    name.textContent = username;
    info.classList.remove('hidden');
  } else {
    info.classList.add('hidden');
  }
}

// --- API ---
function api(method, path, body) {
  const opts = { method, headers: {}, cache: 'no-store' };
  if (token) opts.headers['Authorization'] = 'Bearer ' + token;
  if (body) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  return fetch(path, opts).then(r => {
    if (r.status === 401) {
      setCredentials(null, null);
      showLogin();
      return Promise.reject('unauthorized');
    }
    return r.json().then(d => r.ok ? d : Promise.reject(d.error || 'Error'));
  });
}

// --- Views ---
function showLogin() {
  $('login-view').classList.remove('hidden');
  $('app').classList.add('hidden');
  document.querySelector('.topbar').classList.add('hidden');
}

function showApp(initialData) {
  $('login-view').classList.add('hidden');
  $('app').classList.remove('hidden');
  document.querySelector('.topbar').classList.remove('hidden');
  isAdmin = initialData?.admin || false;
  // Show/hide Users tab based on admin status
  const usersTab = document.querySelector('nav button[data-tab="users"]');
  if (usersTab) usersTab.classList.toggle('hidden', !isAdmin);
  updateUserInfo();
  const hash = location.hash.slice(1);
  if (hash === 'users' && !isAdmin) {
    switchTab('ports', initialData);
  } else if (['users', 'settings'].includes(hash)) {
    switchTab(hash);
  } else {
    // ports tab - check for edit/new
    switchTab('ports', initialData, hash);
  }
}

// --- Login/Logout ---
function doLogin() {
  const login = $('login-user').value;
  const password = $('login-pass').value;
  const errEl = $('login-error');
  errEl.classList.add('hidden');
  fetch('/api/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({login, password})
  }).then(r => r.json()).then(data => {
    if (data.token) {
      setCredentials(data.token, login);
      $('login-pass').value = '';
      showApp();
    } else {
      errEl.textContent = data.error || 'Login failed';
      errEl.classList.remove('hidden');
    }
  });
}

function doLogout() {
  api('POST', '/api/logout').catch(() => {});
  setCredentials(null, null);
  showLogin();
}

// --- Tabs ---
function switchTab(tab, data, hash) {
  document.querySelectorAll('nav button[data-tab]').forEach(
    b => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('[id^="tab-"]').forEach(
    t => t.classList.toggle('hidden', t.id !== 'tab-' + tab));
  if (tab === 'ports') loadPorts(data, hash);
  else if (tab === 'users') loadUsers();
  else if (tab === 'settings') loadSettings();
  if (!hash) {
    const newPath = tab === 'ports' ? location.pathname : '#' + tab;
    if (location.hash !== (tab === 'ports' ? '' : '#' + tab))
      history.pushState(null, '', newPath);
  }
}

// --- Ports ---
const MATCH_ATTRS = [
  'vid', 'pid', 'serial_number', 'manufacturer', 'product', 'location'
];
const PROTOCOLS = ['TCP', 'TELNET', 'SSL', 'SOCKET', 'WEBSOCKET'];
const CONTROL_SIGNALS = ['rts', 'dtr', 'cts', 'dsr', 'ri', 'cd'];
const BAUDRATES = [300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200,
  230400, 460800, 921600];
const BYTESIZES = {8: 'EIGHTBITS', 7: 'SEVENBITS', 6: 'SIXBITS', 5: 'FIVEBITS'};
const PARITIES = ['NONE', 'EVEN', 'ODD', 'MARK', 'SPACE'];
const STOPBITS = {'1': 'ONE', '1.5': 'ONE_POINT_FIVE', '2': 'TWO'};

function loadPorts(statusData, hash) {
  const root = $('ports-content');
  const render = (status, detected) => {
    detectedPorts = detected || [];
    usedPorts = [];
    usedEndpoints = [];
    status.ports.forEach((p, i) => {
      (p.servers || []).forEach(s => {
        if (s.port) usedPorts.push({address: s.address, port: s.port, index: i});
        if (s.endpoint) usedEndpoints.push({endpoint: s.endpoint, index: i});
      });
    });
    root.replaceChildren();
    if (!status.ports.length) {
      root.appendChild(el('p', 'No ports configured', 'empty'));
    }
    status.ports.forEach((p, i) => root.appendChild(renderPortCard(p, i)));
    renderDetectedSection();
    // Open editor if hash indicates
    if (hash) {
      const editMatch = hash.match(/^edit\/(.+)$/);
      if (editMatch) {
        const name = decodeURIComponent(editMatch[1]);
        // Find port by name or fallback to index if name is "portN"
        let idx = status.ports.findIndex(p => p.name === name);
        if (idx < 0) {
          const indexMatch = name.match(/^port(\d+)$/);
          if (indexMatch) idx = parseInt(indexMatch[1]);
        }
        if (idx >= 0 && idx < status.ports.length) {
          const config = buildConfigFromStatus(status.ports[idx]);
          showPortEditor(idx, config, true);
        }
      } else if (hash === 'new') {
        addPort();
      }
    }
  };
  if (statusData) {
    api('GET', '/api/detect').then(detected => {
      render(statusData, detected);
    }).catch(() => render(statusData, []));
  } else {
    Promise.all([
      api('GET', '/api/status'),
      api('GET', '/api/detect').catch(() => [])
    ]).then(([status, detected]) => {
      render(status, detected);
    }).catch(() => {
      root.replaceChildren(el('p', 'Failed to load ports', 'empty'));
    });
  }
}

function renderPortCard(port, index) {
  const ser = port.serial || {};
  let name = port.name || ser.port || '';
  if (!name && ser.match) {
    name = 'match: ' + Object.entries(ser.match)
      .map(([k,v]) => k + '=' + v).join(', ');
  }
  // Show device path if match resolved or name hides it
  let subtitle = '';
  if (ser.port) {
    if (ser.match || port.name) subtitle = ser.port;
  } else if (ser.match) {
    // Try to find matching device from detected ports
    const matching = detectedPorts.filter(p =>
      Object.entries(ser.match).every(([k, v]) => {
        const pv = (p[k] || '').toUpperCase();
        const mv = v.toUpperCase().replace(/\*/g, '.*');
        try { return new RegExp('^' + mv + '$').test(pv); }
        catch { return pv === mv; }
      }));
    if (matching.length === 1) subtitle = matching[0].device;
    else if (matching.length > 1)
      subtitle = matching.map(p => p.device).join(', ');
  }
  const connected = ser.connected;
  const div = el('div');
  div.className = 'section';
  div.dataset.portIndex = index;
  // Determine port availability
  let portExists = true;
  if (!connected) {
    if (ser.match) {
      portExists = detectedPorts.some(p =>
        Object.entries(ser.match).every(([k, v]) => {
          const pv = (p[k] || '').toUpperCase();
          const mv = v.toUpperCase().replace(/\*/g, '.*');
          try { return new RegExp('^' + mv + '$').test(pv); }
          catch { return pv === mv; }
        }));
    } else if (ser.port) {
      portExists = detectedPorts.some(p => p.device === ser.port);
    }
  }
  const h = el('h2');
  const dot = el('span', '\u25cf');
  dot.className = connected ? 'dot-on' : (portExists ? 'dot-off' : 'dot-err');
  h.appendChild(dot);
  if (port.name) {
    h.appendChild(document.createTextNode(' ' + name));
  } else {
    h.appendChild(document.createTextNode(' Port ' + index + ': ' + name));
  }
  div.appendChild(h);
  let info = '';
  if (subtitle) info += subtitle + ' \u2014 ';
  if (ser.baudrate) info += ser.baudrate + ' \u2014 ';
  info += connected ? 'connected' : 'disconnected';
  div.appendChild(el('p', info));
  // Signal indicators (clickable for RTS/DTR)
  if (port.signals) {
    const sigDiv = el('div', null, 'signal-indicators');
    CONTROL_SIGNALS.forEach(sig => {
      const on = port.signals[sig];
      const clickable = sig === 'rts' || sig === 'dtr';
      const badge = el('span', sig.toUpperCase(),
        'signal-badge ' + (on ? 'signal-on' : 'signal-off')
        + (clickable ? ' signal-click' : ''));
      if (clickable) {
        badge.title = sig.toUpperCase() + ': click to toggle';
        badge.onclick = () => {
          badge.classList.add('signal-busy');
          api('PUT', '/api/ports/' + index + '/signals',
              {[sig]: !on}).then(() => loadPorts()).catch(e => {
            badge.classList.remove('signal-busy');
            if (e !== 'unauthorized') alert(e);
          });
        };
      }
      sigDiv.appendChild(badge);
    });
    div.appendChild(sigDiv);
  }
  // Monitor link (requires port name)
  if (port.name) {
    const monDiv = el('div', null, 'ws-links');
    monDiv.innerHTML = '<a href="/monitor/' + encodeURIComponent(port.name)
      + '" class="detect-link" target="_blank" rel="noopener">Monitor</a>';
    div.appendChild(monDiv);
  }
  // Show configured port or match
  if (ser.match) {
    const matchDiv = el('div', null, 'port-match-detail');
    matchDiv.appendChild(el('span', 'match:', 'port-match-label'));
    Object.entries(ser.match).forEach(([k, v]) => {
      const row = el('div', null, 'port-match-row');
      row.appendChild(el('span', k, 'port-match-key'));
      row.appendChild(el('span', v, 'port-match-val'));
      matchDiv.appendChild(row);
    });
    div.appendChild(matchDiv);
  } else if (ser.port && port.name) {
    div.appendChild(el('p', 'port: ' + ser.port, 'port-config-detail'));
  }
  const ul = el('ul');
  (port.servers || []).forEach((s, si) => {
    const proto = (s.protocol || 'tcp').toUpperCase();
    const addr = proto === 'WEBSOCKET' ? '/ws/' + s.endpoint
      : proto === 'SOCKET' ? s.address : s.address + ':' + s.port;
    const li = el('li');
    li.appendChild(document.createTextNode(proto + ' \u2014 ' + addr));
    if (proto === 'WEBSOCKET') {
      const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = scheme + '//' + location.host + '/ws/' + s.endpoint;
      const urlEl = el('div', wsUrl, 'port-config-detail');
      urlEl.style.cursor = 'pointer';
      urlEl.title = 'Click to copy';
      urlEl.onclick = e => {
        e.stopPropagation();
        navigator.clipboard.writeText(wsUrl);
        urlEl.textContent = 'Copied!';
        setTimeout(() => { urlEl.textContent = wsUrl; }, 1000);
      };
      li.appendChild(urlEl);
      if (s.data !== false) {
        const tokenParam = s.token
          ? '?token=' + encodeURIComponent(s.token) : '';
        const linksDiv = el('div', null, 'ws-links');
        linksDiv.innerHTML = '<a href="/xterm/' + s.endpoint + tokenParam
          + '" class="detect-link" target="_blank" rel="noopener">Terminal</a>'
          + '<a href="/raw/' + s.endpoint + tokenParam
          + '" class="detect-link" target="_blank" rel="noopener">Raw</a>';
        li.appendChild(linksDiv);
      }
      if (s.data === false)
        li.appendChild(el('div', 'control only', 'control-signals'));
    }
    if (s.control) {
      const ctlDiv = el('div', null, 'control-signals');
      const setParts = [];
      if (s.control.rts) setParts.push('RTS');
      if (s.control.dtr) setParts.push('DTR');
      if (setParts.length)
        ctlDiv.appendChild(el('div', 'ctrl: ' + setParts.join(', ')));
      else
        ctlDiv.appendChild(el('div', 'ctrl: escape only'));
      if (s.control.signals && s.control.signals.length)
        ctlDiv.appendChild(el('div', 'report: '
          + s.control.signals.map(s => s.toUpperCase()).join(', ')));
      li.appendChild(ctlDiv);
    }
    const clients = s.connections || [];
    if (clients.length) {
      const cul = el('ul');
      clients.forEach((c, ci) => {
        const cli = el('li');
        cli.appendChild(document.createTextNode(c.address + ' '));
        const dcBtn = document.createElement('button');
        dcBtn.className = 'btn-disconnect';
        dcBtn.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14">'
          + '<path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12'
          + ' 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"'
          + ' fill="currentColor"/></svg>';
        dcBtn.title = 'Disconnect ' + c.address;
        dcBtn.onclick = () => disconnectClient(index, si, ci);
        cli.appendChild(dcBtn);
        cul.appendChild(cli);
      });
      li.appendChild(cul);
    }
    ul.appendChild(li);
  });
  div.appendChild(ul);
  const editBtn = document.createElement('button');
  editBtn.className = 'btn-edit';
  editBtn.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18">'
    + '<path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25z'
    + 'M20.71 7.04a1 1 0 000-1.41l-2.34-2.34a1 1 0 00-1.41 0'
    + 'l-1.83 1.83 3.75 3.75 1.83-1.83z" fill="currentColor"/></svg>';
  editBtn.title = 'Edit';
  editBtn.onclick = () => editPort(index);
  div.appendChild(editBtn);
  return div;
}

function renderDetectedSection() {
  const root = $('detected-ports');
  root.replaceChildren();
  if (!detectedPorts.length) return;
  const sec = el('div', null, 'detected-section');
  sec.appendChild(el('h3', 'Detected serial ports'));
  const grid = el('div', null, 'detected-grid');
  detectedPorts.forEach(p => {
    const card = el('div', null, 'section detected-card');
    // Header: device path + add button
    const header = el('div', null, 'port-card-header');
    header.appendChild(el('div', p.device, 'port-card-title'));
    if (p.description) header.appendChild(el('div', p.description, 'port-card-desc'));
    const addBtn = el('button', '+ Add', 'btn btn-primary detected-add-btn');
    addBtn.title = 'Add new port with ' + p.device;
    addBtn.onclick = () => addPortFromDetected(p, null);
    card.appendChild(header);
    // Match attributes
    const attrs = MATCH_ATTRS.filter(a => p[a]);
    if (attrs.length) {
      const dl = el('dl', null, 'detect-attrs');
      attrs.forEach(a => {
        dl.appendChild(el('dt', a));
        const dd = document.createElement('dd');
        const matchLink = el('a', p[a]);
        matchLink.href = '#';
        matchLink.className = 'detect-link';
        matchLink.title = 'Add new port with match ' + a + '=' + p[a];
        matchLink.onclick = e => { e.preventDefault(); addPortFromDetected(p, a); };
        dd.appendChild(matchLink);
        dl.appendChild(dd);
      });
      card.appendChild(dl);
    }
    card.appendChild(addBtn);
    grid.appendChild(card);
  });
  sec.appendChild(grid);
  root.appendChild(sec);
}

// --- Port Editor ---
function editPort(index) {
  // Fetch current config from the status data
  api('GET', '/api/status').then(status => {
    const port = status.ports[index];
    if (!port) return;
    // Build config from status
    const config = buildConfigFromStatus(port);
    showPortEditor(index, config);
  });
}

function nextFreePort(start) {
  const used = new Set(usedPorts.map(u => u.port));
  let p = start || 10001;
  while (used.has(p)) p++;
  return p;
}

function addPortFromDetected(detected, matchAttr) {
  const config = {
    serial: {port: detected.device},
    servers: [{protocol: 'tcp', address: '0.0.0.0', port: nextFreePort()}],
  };
  if (matchAttr) {
    config.serial.match = {};
    config.serial.match[matchAttr] = detected[matchAttr];
  }
  showPortEditor(null, config);
}

function addPort() {
  const config = {
    serial: {port: ''},
    servers: [{protocol: 'tcp', address: '0.0.0.0', port: nextFreePort()}],
  };
  showPortEditor(null, config);
}

function buildConfigFromStatus(port) {
  const ser = port.serial || {};
  const config = {serial: {}};
  if (port.name) config.name = port.name;
  if (port.max_connections !== undefined) config.max_connections = port.max_connections;
  if (ser.match) {
    config.serial.match = {...ser.match};
  }
  if (ser.port) config.serial.port = ser.port;
  if (ser.baudrate) config.serial.baudrate = ser.baudrate;
  if (ser.bytesize) config.serial.bytesize = ser.bytesize;
  if (ser.parity) config.serial.parity = ser.parity;
  if (ser.stopbits) config.serial.stopbits = ser.stopbits;
  config.servers = (port.servers || []).map(s => {
    const srv = {protocol: s.protocol.toLowerCase()};
    if (s.data === false) srv.data = false;
    if (s.protocol === 'WEBSOCKET') {
      if (s.endpoint) srv.endpoint = s.endpoint;
      if (s.token) srv.token = s.token;
    } else {
      srv.address = s.address;
      if (s.port !== undefined) srv.port = s.port;
      if (s.ssl) srv.ssl = s.ssl;
    }
    if (s.control) srv.control = s.control;
    if (s.max_connections !== undefined) srv.max_connections = s.max_connections;
    return srv;
  });
  if (!config.servers.length) {
    config.servers = [{protocol: 'tcp', address: '0.0.0.0', port: 10001}];
  }
  return config;
}

function showPortEditor(index, config, skipHistory) {
  const root = $('ports-content');
  // Find existing card or append
  let container;
  if (index !== null) {
    container = root.querySelector('[data-port-index="' + index + '"]');
  }
  if (!container) {
    container = el('div');
    root.appendChild(container);
  }
  container.className = 'port-edit';
  container.dataset.portIndex = index !== null ? index : 'new';
  container.replaceChildren();
  // Update URL with name
  if (!skipHistory) {
    const name = config.name || (index !== null ? 'port' + index : null);
    const hash = name ? '#edit/' + encodeURIComponent(name) : '#new';
    history.pushState(null, '', hash);
  }

  const title = index !== null ? 'Edit Port ' + index : 'New Port';
  container.appendChild(el('h3', title));

  // Name field
  const nameRow = el('div', null, 'field-row');
  nameRow.appendChild(el('label', 'Name:'));
  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.id = 'edit-name';
  nameInput.placeholder = '';
  nameInput.value = config.name || '';
  nameRow.appendChild(nameInput);
  container.appendChild(nameRow);

  // --- Serial section ---
  container.appendChild(el('h3', 'Serial'));

  // Port field with datalist
  const portRow = el('div', null, 'field-row');
  portRow.appendChild(el('label', 'Port:'));
  const portInput = document.createElement('input');
  portInput.type = 'text';
  portInput.id = 'edit-port';
  portInput.setAttribute('list', 'detected-ports-list');
  portInput.value = config.serial.port || '';
  portInput.oninput = () => fillMatchFromPort(portInput.value);
  portRow.appendChild(portInput);
  container.appendChild(portRow);

  // Datalist for port
  const datalist = document.createElement('datalist');
  datalist.id = 'detected-ports-list';
  detectedPorts.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.device;
    if (p.description) opt.textContent = p.description;
    datalist.appendChild(opt);
  });
  container.appendChild(datalist);

  // Match attributes
  const matchDiv = el('div');
  matchDiv.id = 'edit-match-section';
  const hasMatch = !!config.serial.match;
  MATCH_ATTRS.forEach(attr => {
    const row = el('div', null, 'match-row');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.dataset.matchAttr = attr;
    cb.className = 'match-cb';
    const matchVal = config.serial.match ? config.serial.match[attr] : '';
    const detectedVal = getDetectedAttr(config.serial.port, attr);
    cb.checked = !!matchVal;
    row.appendChild(cb);
    row.appendChild(el('label', attr + ':'));
    const input = document.createElement('input');
    input.type = 'text';
    input.dataset.matchAttr = attr;
    input.className = 'match-input';
    input.value = matchVal || detectedVal || '';
    input.disabled = !cb.checked;
    input.setAttribute('list', 'match-list-' + attr);
    row.appendChild(input);
    // Datalist for this attribute
    const dl = document.createElement('datalist');
    dl.id = 'match-list-' + attr;
    const seen = new Set();
    detectedPorts.forEach(p => {
      const v = p[attr];
      if (v && !seen.has(v)) {
        seen.add(v);
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = p.device;
        dl.appendChild(opt);
      }
    });
    row.appendChild(dl);
    cb.onchange = () => {
      input.disabled = !cb.checked;
      updateMatchMode();
      updateMatchPreview();
    };
    input.oninput = () => updateMatchPreview();
    matchDiv.appendChild(row);
  });
  container.appendChild(matchDiv);

  // Match preview
  const preview = el('div', '', 'match-preview');
  preview.id = 'match-preview';
  container.appendChild(preview);

  // Serial parameters
  container.appendChild(el('h3', 'Parameters'));
  const paramsDiv = el('div', null, 'field-row');

  paramsDiv.appendChild(el('label', 'Baudrate:'));
  const baudSel = document.createElement('select');
  baudSel.id = 'edit-baudrate';
  const emptyOpt = document.createElement('option');
  emptyOpt.value = '';
  emptyOpt.textContent = '(default)';
  baudSel.appendChild(emptyOpt);
  BAUDRATES.forEach(b => {
    const opt = document.createElement('option');
    opt.value = b;
    opt.textContent = b;
    if (config.serial.baudrate === b) opt.selected = true;
    baudSel.appendChild(opt);
  });
  paramsDiv.appendChild(baudSel);
  container.appendChild(paramsDiv);

  const byteRow = el('div', null, 'field-row');
  byteRow.appendChild(el('label', 'Data bits:'));
  const byteSel = document.createElement('select');
  byteSel.id = 'edit-bytesize';
  Object.entries(BYTESIZES).forEach(([bits, name]) => {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = bits;
    if (config.serial.bytesize === name || (!config.serial.bytesize && bits === '8'))
      opt.selected = true;
    byteSel.appendChild(opt);
  });
  byteRow.appendChild(byteSel);
  container.appendChild(byteRow);

  const parityRow = el('div', null, 'field-row');
  parityRow.appendChild(el('label', 'Parity:'));
  const paritySel = document.createElement('select');
  paritySel.id = 'edit-parity';
  PARITIES.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p;
    opt.textContent = p;
    if (config.serial.parity === p) opt.selected = true;
    paritySel.appendChild(opt);
  });
  parityRow.appendChild(paritySel);
  container.appendChild(parityRow);

  const stopRow = el('div', null, 'field-row');
  stopRow.appendChild(el('label', 'Stop bits:'));
  const stopSel = document.createElement('select');
  stopSel.id = 'edit-stopbits';
  Object.entries(STOPBITS).forEach(([bits, name]) => {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = bits;
    if (config.serial.stopbits === name || (!config.serial.stopbits && bits === '1'))
      opt.selected = true;
    stopSel.appendChild(opt);
  });
  stopRow.appendChild(stopSel);
  container.appendChild(stopRow);

  // Port-level max connections
  const portMaxRow = el('div', null, 'field-row');
  portMaxRow.appendChild(el('label', 'Max clients (port):'));
  const portMaxInput = document.createElement('input');
  portMaxInput.type = 'number';
  portMaxInput.id = 'edit-max-connections';
  portMaxInput.min = '0';
  portMaxInput.step = '1';
  portMaxInput.inputMode = 'numeric';
  portMaxInput.placeholder = '0 (unlimited)';
  portMaxInput.value = config.max_connections !== undefined ? config.max_connections : '';
  portMaxInput.title = 'Total clients across all servers on this port (0 = unlimited)';
  portMaxRow.appendChild(portMaxInput);
  container.appendChild(portMaxRow);

  // --- Servers section ---
  container.appendChild(el('h3', 'Servers'));
  const serversDiv = el('div');
  serversDiv.id = 'edit-servers';
  config.servers.forEach((srv, i) => {
    serversDiv.appendChild(renderServerBox(srv, i, config.servers.length));
  });
  container.appendChild(serversDiv);

  // Actions
  const actions = el('div', null, 'edit-actions');
  const saveBtn = el('button', 'Save', 'btn-primary');
  saveBtn.onclick = () => savePort(index);
  actions.appendChild(saveBtn);
  const cancelBtn = el('button', 'Cancel', 'btn-secondary');
  cancelBtn.onclick = () => {
    history.pushState(null, '', location.pathname);
    loadPorts();
  };
  actions.appendChild(cancelBtn);
  if (index !== null) {
    const delBtn = el('button', 'Delete', 'btn-danger');
    delBtn.onclick = () => deletePort(index);
    actions.appendChild(delBtn);
  }
  actions.appendChild(el('span', null, 'spacer'));
  const addSrvBtn = el('button', '+ Add Server', 'btn-secondary');
  addSrvBtn.onclick = () => addServerBox();
  actions.appendChild(addSrvBtn);
  container.appendChild(actions);

  updateMatchMode();
  updateMatchPreview();
}

function getDetectedAttr(port, attr) {
  if (!port) return '';
  const found = detectedPorts.find(p => p.device === port);
  return found ? (found[attr] || '') : '';
}

function fillMatchFromPort(device) {
  const found = detectedPorts.find(p => p.device === device);
  MATCH_ATTRS.forEach(attr => {
    const input = document.querySelector(
      '.match-input[data-match-attr="' + attr + '"]');
    if (!input) return;
    const cb = document.querySelector(
      '.match-cb[data-match-attr="' + attr + '"]');
    if (cb && cb.checked) return;
    input.value = found ? (found[attr] || '') : '';
  });
}

function updateMatchMode() {
  const anyChecked = document.querySelectorAll('.match-cb:checked').length > 0;
  const portInput = $('edit-port');
  if (portInput) portInput.disabled = anyChecked;
}

function updateMatchPreview() {
  const preview = $('match-preview');
  if (!preview) return;
  const match = {};
  document.querySelectorAll('.match-cb:checked').forEach(cb => {
    const attr = cb.dataset.matchAttr;
    const input = document.querySelector('.match-input[data-match-attr="' + attr + '"]');
    if (input && input.value) match[attr] = input.value;
  });
  if (!Object.keys(match).length) {
    preview.textContent = '';
    return;
  }
  const matching = detectedPorts.filter(p => {
    return Object.entries(match).every(([k, v]) => {
      const pv = (p[k] || '').toUpperCase();
      const mv = v.toUpperCase().replace(/\*/g, '.*');
      try { return new RegExp('^' + mv + '$').test(pv); }
      catch { return pv === mv; }
    });
  });
  if (matching.length) {
    preview.textContent = 'Matching: ' + matching.map(p => p.device).join(', ');
  } else {
    preview.textContent = 'No matching ports detected';
  }
}

function renderServerBox(srv, index, total) {
  const box = el('div', null, 'server-box');
  box.dataset.serverIndex = index;

  const removeBtn = el('button', null, 'btn-remove');
  removeBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6h14"/></svg>';
  removeBtn.disabled = total <= 1;
  removeBtn.onclick = () => removeServerBox(box);
  box.appendChild(removeBtn);

  // Protocol
  const protoRow = el('div', null, 'field-row');
  protoRow.appendChild(el('label', 'Protocol:'));
  const protoSel = document.createElement('select');
  protoSel.className = 'srv-protocol';
  PROTOCOLS.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p;
    opt.textContent = p;
    if (srv.protocol.toUpperCase() === p) opt.selected = true;
    protoSel.appendChild(opt);
  });
  protoRow.appendChild(protoSel);
  box.appendChild(protoRow);

  // WebSocket fields
  const wsDiv = el('div');
  wsDiv.className = 'srv-ws-fields';
  const wsRow1 = el('div', null, 'field-row');
  wsRow1.appendChild(el('label', 'Endpoint:'));
  const wsEndpoint = document.createElement('input');
  wsEndpoint.type = 'text';
  wsEndpoint.className = 'srv-endpoint';
  wsEndpoint.placeholder = 'my-device';
  wsEndpoint.value = srv.endpoint || '';
  wsRow1.appendChild(wsEndpoint);
  wsDiv.appendChild(wsRow1);
  const wsRow2 = el('div', null, 'field-row');
  wsRow2.appendChild(el('label', 'Token:'));
  const wsToken = document.createElement('input');
  wsToken.type = 'text';
  wsToken.className = 'srv-token';
  wsToken.placeholder = '(use global auth)';
  wsToken.value = srv.token || '';
  wsRow2.appendChild(wsToken);
  const wsGenBtn = el('button', null, 'btn-icon');
  wsGenBtn.type = 'button';
  wsGenBtn.title = 'Generate token';
  wsGenBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>';
  wsGenBtn.onclick = () => { wsToken.value = crypto.randomUUID(); };
  wsRow2.appendChild(wsGenBtn);
  const wsCopyBtn = el('button', null, 'btn-icon');
  wsCopyBtn.type = 'button';
  wsCopyBtn.title = 'Copy token';
  wsCopyBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
  wsCopyBtn.onclick = () => {
    if (wsToken.value) navigator.clipboard.writeText(wsToken.value).then(() => {
      wsCopyBtn.style.color = 'var(--success)';
      setTimeout(() => { wsCopyBtn.style.color = ''; }, 1000);
    });
  };
  wsRow2.appendChild(wsCopyBtn);
  wsDiv.appendChild(wsRow2);
  box.appendChild(wsDiv);

  // Address + Port (or Path for SOCKET)
  const addrRow = el('div', null, 'field-row');
  const addrLabel = el('label', 'Address:');
  addrRow.appendChild(addrLabel);
  const addrInput = document.createElement('input');
  addrInput.type = 'text';
  addrInput.className = 'srv-address';
  addrInput.value = srv.address || '0.0.0.0';
  addrRow.appendChild(addrInput);
  box.appendChild(addrRow);
  const portRow = el('div', null, 'field-row');
  const portLabel = el('label', 'Port:');
  portLabel.className = 'srv-port-label';
  portRow.appendChild(portLabel);
  const portInput = document.createElement('input');
  portInput.type = 'number';
  portInput.className = 'srv-port';
  portInput.value = srv.port || '';
  portRow.appendChild(portInput);
  box.appendChild(portRow);

  // SSL fields
  const sslDiv = el('div');
  sslDiv.className = 'srv-ssl-fields';
  const ssl = srv.ssl || {};
  [['Certfile:', 'srv-certfile', ssl.certfile],
   ['Keyfile:', 'srv-keyfile', ssl.keyfile],
   ['CA certs:', 'srv-cacerts', ssl.ca_certs]
  ].forEach(([label, cls, val]) => {
    const row = el('div', null, 'field-row');
    row.appendChild(el('label', label));
    const inp = document.createElement('input');
    inp.type = 'text';
    inp.className = cls;
    inp.value = val || '';
    row.appendChild(inp);
    sslDiv.appendChild(row);
  });
  box.appendChild(sslDiv);

  // Control section
  const ctlDiv = el('div');
  ctlDiv.className = 'srv-control-fields';
  const ctl = srv.control || null;
  // Enable checkbox
  const ctlEnableRow = el('div', null, 'field-row');
  const ctlEnableLbl = document.createElement('label');
  ctlEnableLbl.className = 'ctl-signal-label';
  const ctlEnableCb = document.createElement('input');
  ctlEnableCb.type = 'checkbox';
  ctlEnableCb.className = 'ctl-enable';
  ctlEnableCb.checked = !!ctl;
  ctlEnableLbl.appendChild(ctlEnableCb);
  ctlEnableLbl.appendChild(document.createTextNode(' Control protocol'));
  ctlEnableRow.appendChild(ctlEnableLbl);
  ctlDiv.appendChild(ctlEnableRow);
  // Control details (shown when enabled)
  const ctlDetails = el('div');
  ctlDetails.className = 'ctl-details';
  // Forward data checkbox
  const ctlDataRow = el('div', null, 'field-row');
  const ctlDataLbl = document.createElement('label');
  ctlDataLbl.className = 'ctl-signal-label';
  const ctlDataCb = document.createElement('input');
  ctlDataCb.type = 'checkbox';
  ctlDataCb.className = 'srv-data';
  ctlDataCb.checked = srv.data !== false;
  ctlDataLbl.appendChild(ctlDataCb);
  ctlDataLbl.appendChild(document.createTextNode(' Forward serial data'));
  ctlDataRow.appendChild(ctlDataLbl);
  ctlDetails.appendChild(ctlDataRow);
  // Protocol description (changes based on protocol)
  const ctlDesc = el('p', '', 'ctl-desc');
  const ctlMoreBtn = el('a', 'Protocol reference');
  ctlMoreBtn.href = '#';
  ctlMoreBtn.className = 'detect-link';
  ctlMoreBtn.onclick = e => {
    e.preventDefault();
    const dlg = $('ctl-protocol-dlg');
    dlg.classList.toggle('hidden');
  };
  ctlDetails.appendChild(ctlDesc);
  // RTS/DTR write enable
  const ctlWriteRow = el('div', null, 'field-row');
  ctlWriteRow.appendChild(el('label', 'Allow set:'));
  ['rts', 'dtr'].forEach(sig => {
    const lbl = document.createElement('label');
    lbl.className = 'ctl-signal-label';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'ctl-write';
    cb.dataset.signal = sig;
    cb.checked = ctl ? !!ctl[sig] : false;
    lbl.appendChild(cb);
    lbl.appendChild(document.createTextNode(' ' + sig.toUpperCase()));
    ctlWriteRow.appendChild(lbl);
  });
  ctlDetails.appendChild(ctlWriteRow);
  // Report signals
  const ctlSigRow = el('div', null, 'field-row');
  ctlSigRow.appendChild(el('label', 'Report:'));
  const ctlSignals = ctl ? (ctl.signals || []) : [];
  CONTROL_SIGNALS.forEach(sig => {
    const lbl = document.createElement('label');
    lbl.className = 'ctl-signal-label';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'ctl-signal';
    cb.dataset.signal = sig;
    cb.checked = ctlSignals.includes(sig);
    lbl.appendChild(cb);
    lbl.appendChild(document.createTextNode(' ' + sig.toUpperCase()));
    ctlSigRow.appendChild(lbl);
  });
  ctlDetails.appendChild(ctlSigRow);
  // Poll interval
  const pollRow = el('div', null, 'field-row');
  pollRow.appendChild(el('label', 'Poll interval:'));
  const pollSel = document.createElement('select');
  pollSel.className = 'ctl-poll-interval';
  const pollOptions = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000];
  const curPoll = ctl ? Math.round((ctl.poll_interval || 0.1) * 1000) : 100;
  pollOptions.forEach(ms => {
    const opt = document.createElement('option');
    opt.value = ms;
    opt.textContent = ms < 1000 ? ms + ' ms' : (ms / 1000) + ' s';
    if (ms === curPoll) opt.selected = true;
    pollSel.appendChild(opt);
  });
  pollRow.appendChild(pollSel);
  ctlDetails.appendChild(pollRow);
  ctlDiv.appendChild(ctlDetails);
  const updateCtlVisibility = () => {
    ctlDetails.classList.toggle('hidden', !ctlEnableCb.checked);
  };
  ctlEnableCb.onchange = updateCtlVisibility;
  updateCtlVisibility();
  box.appendChild(ctlDiv);

  // IP filter section
  const ipDiv = el('div');
  ipDiv.className = 'srv-ip-filter';
  const ipAllowRow = el('div', null, 'field-row');
  ipAllowRow.appendChild(el('label', 'Allow IPs:'));
  const ipAllowInput = document.createElement('input');
  ipAllowInput.type = 'text';
  ipAllowInput.className = 'srv-allow';
  ipAllowInput.placeholder = '192.168.1.0/24, 10.0.0.5';
  ipAllowInput.value = (srv.allow || []).join(', ');
  ipAllowRow.appendChild(ipAllowInput);
  ipDiv.appendChild(ipAllowRow);
  const ipDenyRow = el('div', null, 'field-row');
  ipDenyRow.appendChild(el('label', 'Deny IPs:'));
  const ipDenyInput = document.createElement('input');
  ipDenyInput.type = 'text';
  ipDenyInput.className = 'srv-deny';
  ipDenyInput.placeholder = '192.168.1.100';
  ipDenyInput.value = (srv.deny || []).join(', ');
  ipDenyRow.appendChild(ipDenyInput);
  ipDiv.appendChild(ipDenyRow);
  box.appendChild(ipDiv);

  // Max connections
  const maxConnRow = el('div', null, 'field-row');
  maxConnRow.appendChild(el('label', 'Max clients:'));
  const maxConnInput = document.createElement('input');
  maxConnInput.type = 'number';
  maxConnInput.className = 'srv-max-connections';
  maxConnInput.min = '0';
  maxConnInput.step = '1';
  maxConnInput.inputMode = 'numeric';
  maxConnInput.placeholder = '0';
  maxConnInput.value = srv.max_connections !== undefined ? srv.max_connections : '';
  maxConnInput.title = '0 = unlimited, default is 5';
  maxConnRow.appendChild(maxConnInput);
  box.appendChild(maxConnRow);

  // Update visibility based on protocol
  const updateProtoFields = () => {
    const proto = protoSel.value;
    const isSocket = proto === 'SOCKET';
    const isSsl = proto === 'SSL';
    const isTelnet = proto === 'TELNET';
    const isWs = proto === 'WEBSOCKET';
    wsDiv.classList.toggle('hidden', !isWs);
    addrRow.classList.toggle('hidden', isWs);
    portRow.classList.toggle('hidden', isWs || isSocket);
    addrLabel.textContent = isSocket ? 'Path:' : 'Address:';
    sslDiv.classList.toggle('hidden', !isSsl);
    ctlDiv.classList.toggle('hidden', isTelnet);
    ipDiv.classList.toggle('hidden', isSocket);
    // Update control description
    ctlDesc.textContent = '';
    if (isWs) {
      ctlDesc.appendChild(document.createTextNode(
        'JSON text frames for signal control. '));
    } else {
      ctlDesc.appendChild(document.createTextNode(
        'Binary escape protocol using 0xFF prefix. '));
      ctlDesc.appendChild(ctlMoreBtn);
    }
    if (isSocket) {
      addrInput.value = addrInput.value === '0.0.0.0' ? '' : addrInput.value;
    }
  };
  const checkConflict = () => {
    const proto = protoSel.value;
    const editIndex = parseInt(
      (document.querySelector('.port-edit') || {}).dataset?.portIndex);
    // Endpoint conflict check
    const ep = wsEndpoint.value.trim();
    if (proto === 'WEBSOCKET' && ep) {
      // Check against other ports
      const epConflict = usedEndpoints.find(u =>
        u.endpoint === ep && u.index !== editIndex);
      // Check against other server boxes in this editor
      let editorDup = false;
      const serversDiv = $('edit-servers');
      if (serversDiv) {
        serversDiv.querySelectorAll('.server-box').forEach(b => {
          if (b === box) return;
          if (b.querySelector('.srv-protocol').value === 'WEBSOCKET'
              && b.querySelector('.srv-endpoint').value.trim() === ep)
            editorDup = true;
        });
      }
      const epErr = epConflict || editorDup;
      wsEndpoint.style.borderColor = epErr ? '#e55' : '';
      wsEndpoint.title = epConflict
        ? 'Endpoint used by Port ' + epConflict.index
        : editorDup ? 'Duplicate endpoint' : '';
    } else {
      wsEndpoint.style.borderColor = '';
      wsEndpoint.title = '';
    }
    // Port conflict check
    if (proto === 'SOCKET' || proto === 'WEBSOCKET') {
      portInput.style.borderColor = '';
      portInput.title = '';
      return;
    }
    const addr = addrInput.value.trim();
    const p = parseInt(portInput.value);
    if (!p) { portInput.style.borderColor = ''; return; }
    const conflict = usedPorts.find(u =>
      u.port === p && u.address === addr && u.index !== editIndex);
    portInput.style.borderColor = conflict ? '#e55' : '';
    portInput.title = conflict
      ? 'Port already used by Port ' + conflict.index : '';
  };
  portInput.oninput = checkConflict;
  addrInput.oninput = checkConflict;
  wsEndpoint.oninput = checkConflict;
  protoSel.onchange = () => { updateProtoFields(); checkConflict(); };
  updateProtoFields();
  checkConflict();

  return box;
}

function addServerBox() {
  const serversDiv = $('edit-servers');
  if (!serversDiv) return;
  const count = serversDiv.children.length;
  // Collect ports already used in this editor
  const editorPorts = new Set();
  serversDiv.querySelectorAll('.srv-port').forEach(
    inp => { if (inp.value) editorPorts.add(parseInt(inp.value)); });
  let p = 10001;
  const globalUsed = new Set(usedPorts.map(u => u.port));
  while (globalUsed.has(p) || editorPorts.has(p)) p++;
  const box = renderServerBox(
    {protocol: 'tcp', address: '0.0.0.0', port: p}, count, count + 1);
  serversDiv.appendChild(box);
  updateRemoveButtons();
}

function removeServerBox(box) {
  box.remove();
  updateRemoveButtons();
}

function updateRemoveButtons() {
  const serversDiv = $('edit-servers');
  if (!serversDiv) return;
  const boxes = serversDiv.querySelectorAll('.server-box');
  boxes.forEach(b => {
    b.querySelector('.btn-remove').disabled = boxes.length <= 1;
  });
}

function collectConfig() {
  const config = {serial: {}, servers: []};

  // Name
  const name = $('edit-name').value.trim();
  if (name) config.name = name;

  // Port-level max connections
  const portMaxConn = $('edit-max-connections').value.trim();
  if (portMaxConn !== '') {
    config.max_connections = parseInt(portMaxConn);
  }

  // Serial
  const anyMatch = document.querySelectorAll('.match-cb:checked').length > 0;
  if (anyMatch) {
    config.serial.match = {};
    document.querySelectorAll('.match-cb:checked').forEach(cb => {
      const attr = cb.dataset.matchAttr;
      const input = document.querySelector(
        '.match-input[data-match-attr="' + attr + '"]');
      if (input && input.value) config.serial.match[attr] = input.value;
    });
  } else {
    const port = $('edit-port').value.trim();
    if (port) config.serial.port = port;
  }

  const baudrate = $('edit-baudrate').value;
  if (baudrate) config.serial.baudrate = parseInt(baudrate);
  const bytesize = $('edit-bytesize').value;
  if (bytesize !== 'EIGHTBITS') config.serial.bytesize = bytesize;
  const parity = $('edit-parity').value;
  if (parity !== 'NONE') config.serial.parity = parity;
  const stopbits = $('edit-stopbits').value;
  if (stopbits !== 'ONE') config.serial.stopbits = stopbits;

  // Servers
  $('edit-servers').querySelectorAll('.server-box').forEach(box => {
    const proto = box.querySelector('.srv-protocol').value.toLowerCase();
    const srv = {protocol: proto};
    if (proto === 'websocket') {
      const endpoint = box.querySelector('.srv-endpoint').value.trim();
      if (endpoint) srv.endpoint = endpoint;
      const wsToken = box.querySelector('.srv-token').value.trim();
      if (wsToken) srv.token = wsToken;
    } else {
      srv.address = box.querySelector('.srv-address').value.trim();
      if (proto !== 'socket') {
        const port = box.querySelector('.srv-port').value;
        if (port) srv.port = parseInt(port);
      }
    }
    if (proto === 'ssl') {
      const ssl = {};
      const certfile = box.querySelector('.srv-certfile').value.trim();
      const keyfile = box.querySelector('.srv-keyfile').value.trim();
      const cacerts = box.querySelector('.srv-cacerts').value.trim();
      if (certfile) ssl.certfile = certfile;
      if (keyfile) ssl.keyfile = keyfile;
      if (cacerts) ssl.ca_certs = cacerts;
      if (Object.keys(ssl).length) srv.ssl = ssl;
    }
    if (proto !== 'telnet' && box.querySelector('.ctl-enable').checked) {
      if (!box.querySelector('.srv-data').checked) srv.data = false;
      const ctl = {};
      box.querySelectorAll('.ctl-write:checked').forEach(
        cb => { ctl[cb.dataset.signal] = true; });
      const signals = [];
      box.querySelectorAll('.ctl-signal:checked').forEach(
        cb => signals.push(cb.dataset.signal));
      if (signals.length) ctl.signals = signals;
      const pollMs = parseInt(box.querySelector('.ctl-poll-interval').value);
      if (pollMs) ctl.poll_interval = pollMs / 1000;
      srv.control = ctl;
    }
    // IP filter
    if (proto !== 'socket') {
      const allowStr = box.querySelector('.srv-allow').value.trim();
      if (allowStr) {
        srv.allow = allowStr.split(',').map(s => s.trim()).filter(s => s);
      }
      const denyStr = box.querySelector('.srv-deny').value.trim();
      if (denyStr) {
        srv.deny = denyStr.split(',').map(s => s.trim()).filter(s => s);
      }
    }
    // Max connections
    const maxConn = box.querySelector('.srv-max-connections').value.trim();
    if (maxConn !== '') {
      srv.max_connections = parseInt(maxConn);
    }
    config.servers.push(srv);
  });

  return config;
}

function savePort(index) {
  const config = collectConfig();
  const method = index !== null ? 'PUT' : 'POST';
  const path = index !== null ? '/api/ports/' + index : '/api/ports';
  api(method, path, config).then(() => {
    history.pushState(null, '', location.pathname);
    loadPorts();
  }).catch(e => {
    if (e !== 'unauthorized') alert(e);
  });
}

function disconnectClient(portIdx, srvIdx, conIdx) {
  api('DELETE', '/api/ports/' + portIdx + '/connections/' + srvIdx + '/' + conIdx)
    .then(() => loadPorts())
    .catch(e => { if (e !== 'unauthorized') alert(e); });
}

function deletePort(index) {
  if (!confirm('Delete port ' + index + '?')) return;
  api('DELETE', '/api/ports/' + index).then(() => {
    history.pushState(null, '', location.pathname);
    loadPorts();
  }).catch(e => {
    if (e !== 'unauthorized') alert(e);
  });
}

// --- Users & Tokens ---
let currentUsers = [];
let currentTokens = [];

function loadUsers() {
  Promise.all([
    api('GET', '/api/users').catch(() => []),
    api('GET', '/api/tokens').catch(() => []),
  ]).then(([users, tokens]) => {
    currentUsers = users;
    currentTokens = tokens;
    renderUsers();
  });
}

function renderUsers() {
  const root = $('users-content');
  root.replaceChildren();

  // Users section
  if (currentUsers.length) {
    const usersHeader = el('h3', 'Users', 'section-header');
    root.appendChild(usersHeader);
    currentUsers.forEach(u => root.appendChild(renderUserCard(u)));
  }

  // Tokens section
  if (currentTokens.length) {
    const tokensHeader = el('h3', 'API Tokens', 'section-header');
    root.appendChild(tokensHeader);
    currentTokens.forEach(t => root.appendChild(renderTokenCard(t)));
  }

  if (!currentUsers.length && !currentTokens.length) {
    root.appendChild(el('p', 'No users or tokens configured', 'empty'));
  }
}

function renderUserCard(user) {
  const card = document.createElement('div');
  card.className = 'section';
  card.dataset.userLogin = user.login;
  const adminBadge = user.admin ? '<span class="badge badge-admin">admin</span>' : '';
  card.innerHTML = `
    <button class="btn-edit" title="Edit">&#9998;</button>
    <h2>${user.login} ${adminBadge}</h2>
  `;
  card.querySelector('.btn-edit').addEventListener('click', () => showUserEditor(user.login, user));
  return card;
}

function renderTokenCard(tok) {
  const card = document.createElement('div');
  card.className = 'section';
  card.dataset.tokenId = tok.token;
  const adminBadge = tok.admin ? '<span class="badge badge-admin">admin</span>' : '';
  const maskedToken = tok.token.slice(0, 8) + '...' + tok.token.slice(-4);
  card.innerHTML = `
    <button class="btn-edit" title="Edit">&#9998;</button>
    <h2>${tok.name} ${adminBadge}</h2>
    <p class="token-value" title="Click to copy">${maskedToken}</p>
  `;
  card.querySelector('.btn-edit').addEventListener('click', () => showTokenEditor(tok.token, tok));
  card.querySelector('.token-value').addEventListener('click', () => {
    navigator.clipboard.writeText(tok.token).then(() => {
      const tv = card.querySelector('.token-value');
      tv.classList.add('copied');
      setTimeout(() => tv.classList.remove('copied'), 1000);
    });
  });
  return card;
}

function showUserEditor(login, user) {
  const container = $('users-content');
  const isNew = login === null;
  let card;
  if (isNew) {
    card = document.createElement('div');
    container.appendChild(card);
  } else {
    card = container.querySelector('[data-user-login="' + login + '"]');
  }
  card.className = 'section user-edit';
  card.dataset.userLogin = isNew ? 'new' : login;
  const title = isNew ? 'New User' : 'Edit User';
  const firstUser = currentUsers.length === 0;
  card.innerHTML = `
    <h3>${title}</h3>
    <div class="field-row">
      <label>Login:</label>
      <input type="text" class="user-login" value="${user.login || ''}" ${isNew ? '' : 'disabled'} autocomplete="off">
    </div>
    <div class="field-row">
      <label>${isNew ? 'Password:' : 'New password:'}</label>
      <input type="password" class="user-password" placeholder="${isNew ? '' : 'leave empty to keep'}" autocomplete="new-password">
    </div>
    <div class="field-row">
      <label><input type="checkbox" class="user-admin" ${user.admin || firstUser ? 'checked' : ''} ${firstUser ? 'disabled' : ''}> Admin</label>
    </div>
    <div class="user-error error hidden"></div>
    <div class="edit-buttons">
      <button type="button" class="btn-primary user-save-btn">Save</button>
      ${!isNew ? '<button type="button" class="btn-danger user-delete-btn">Delete</button>' : ''}
      <button type="button" class="btn btn-secondary user-cancel-btn">Cancel</button>
    </div>
  `;
  card.querySelector('.user-save-btn').addEventListener('click', () => saveUser(isNew ? null : login, card));
  card.querySelector('.user-cancel-btn').addEventListener('click', () => loadUsers());
  if (!isNew) {
    card.querySelector('.user-delete-btn').addEventListener('click', () => deleteUser(login));
  }
  card.querySelector('.user-login').focus();
}

function showTokenEditor(tokenId, tok) {
  const container = $('users-content');
  const isNew = tokenId === null;
  let card;
  if (isNew) {
    card = document.createElement('div');
    container.appendChild(card);
  } else {
    card = container.querySelector('[data-token-id="' + tokenId + '"]');
  }
  card.className = 'section user-edit';
  card.dataset.tokenId = isNew ? 'new' : tokenId;
  const title = isNew ? 'New API Token' : 'Edit API Token';
  const tokenValue = tok.token || crypto.randomUUID();
  card.innerHTML = `
    <h3>${title}</h3>
    <div class="field-row">
      <label>Name:</label>
      <input type="text" class="token-name" value="${tok.name || ''}" autocomplete="off">
    </div>
    <div class="field-row">
      <label>Token:</label>
      <input type="text" class="token-value-input" value="${tokenValue}" autocomplete="off">
      <button type="button" class="btn-icon token-generate-btn" title="Generate"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg></button>
      <button type="button" class="btn-icon token-copy-btn" title="Copy"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button>
    </div>
    <div class="field-row">
      <label><input type="checkbox" class="token-admin" ${tok.admin ? 'checked' : ''}> Admin</label>
    </div>
    <div class="token-error error hidden"></div>
    <div class="edit-buttons">
      <button type="button" class="btn-primary token-save-btn">Save</button>
      ${!isNew ? '<button type="button" class="btn-danger token-delete-btn">Delete</button>' : ''}
      <button type="button" class="btn btn-secondary token-cancel-btn">Cancel</button>
    </div>
  `;
  card.querySelector('.token-generate-btn').addEventListener('click', () => {
    card.querySelector('.token-value-input').value = crypto.randomUUID();
  });
  card.querySelector('.token-copy-btn').addEventListener('click', () => {
    const input = card.querySelector('.token-value-input');
    navigator.clipboard.writeText(input.value).then(() => {
      const btn = card.querySelector('.token-copy-btn');
      const origSvg = btn.innerHTML;
      btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>';
      setTimeout(() => btn.innerHTML = origSvg, 1000);
    });
  });
  card.querySelector('.token-save-btn').addEventListener('click', () => saveToken(isNew ? null : tokenId, card));
  card.querySelector('.token-cancel-btn').addEventListener('click', () => loadUsers());
  if (!isNew) {
    card.querySelector('.token-delete-btn').addEventListener('click', () => deleteToken(tokenId));
  }
  card.querySelector('.token-name').focus();
}


async function saveUser(login, card) {
  const isNew = login === null;
  const newLogin = card.querySelector('.user-login').value.trim();
  const password = card.querySelector('.user-password').value;
  const admin = card.querySelector('.user-admin').checked;
  const errEl = card.querySelector('.user-error');
  errEl.classList.add('hidden');

  if (!newLogin) {
    errEl.textContent = 'Login is required';
    errEl.classList.remove('hidden');
    return;
  }
  if (isNew && !password) {
    errEl.textContent = 'Password is required';
    errEl.classList.remove('hidden');
    return;
  }

  const data = {admin};
  if (isNew) data.login = newLogin;
  if (password) data.password = await hashPassword(password);

  const method = isNew ? 'POST' : 'PUT';
  const path = isNew ? '/api/users' : '/api/users/' + encodeURIComponent(login);

  api(method, path, data).then(response => {
    if (response.token) setCredentials(response.token, newLogin);
    loadUsers();
  }).catch(e => {
    errEl.textContent = e;
    errEl.classList.remove('hidden');
  });
}

function saveToken(tokenId, card) {
  const isNew = tokenId === null;
  const name = card.querySelector('.token-name').value.trim();
  const tokenValue = card.querySelector('.token-value-input').value.trim();
  const admin = card.querySelector('.token-admin').checked;
  const errEl = card.querySelector('.token-error');
  errEl.classList.add('hidden');

  if (!name) {
    errEl.textContent = 'Name is required';
    errEl.classList.remove('hidden');
    return;
  }
  if (!tokenValue) {
    errEl.textContent = 'Token is required';
    errEl.classList.remove('hidden');
    return;
  }

  const data = {name, admin, token: tokenValue};

  const method = isNew ? 'POST' : 'PUT';
  const path = isNew ? '/api/tokens' : '/api/tokens/' + encodeURIComponent(tokenId);

  api(method, path, data).then(() => {
    loadUsers();
  }).catch(e => {
    errEl.textContent = e;
    errEl.classList.remove('hidden');
  });
}

function deleteUser(login) {
  if (!confirm('Delete user ' + login + '?')) return;
  api('DELETE', '/api/users/' + encodeURIComponent(login)).then(() => {
    if (login === username) setCredentials(null, null);
    loadUsers();
  }).catch(e => {
    if (e !== 'unauthorized') alert(e);
  });
}

function deleteToken(tokenId) {
  if (!confirm('Delete this token?')) return;
  api('DELETE', '/api/tokens/' + encodeURIComponent(tokenId)).then(() => {
    loadUsers();
  }).catch(e => {
    if (e !== 'unauthorized') alert(e);
  });
}

function addUser() {
  const firstUser = currentUsers.length === 0;
  showUserEditor(null, {admin: firstUser});
}

function addToken() {
  showTokenEditor(null, {});
}

// --- Settings ---
let currentSettings = null;

function loadSettings() {
  api('GET', '/api/settings').then(data => {
    currentSettings = data;
    renderSettings();
  }).catch(e => {
    if (e !== 'unauthorized') console.error('Failed to load settings:', e);
  });
}

function renderSettings() {
  const container = $('http-servers');
  container.innerHTML = '';

  // Session timeout card
  const timeoutCard = document.createElement('div');
  timeoutCard.className = 'section';
  timeoutCard.dataset.httpIndex = 'session';
  const timeout = currentSettings.session_timeout;
  timeoutCard.innerHTML = `
    <button class="btn-edit" title="Edit">&#9998;</button>
    <h2>Session</h2>
    <dl>
      <dt>Timeout</dt>
      <dd>${timeout != null ? timeout + 's' : 'default'}</dd>
    </dl>
  `;
  timeoutCard.querySelector('.btn-edit').addEventListener('click', () => showSessionEditor());
  container.appendChild(timeoutCard);

  // HTTP server cards
  const servers = currentSettings.http || [];
  servers.forEach((srv, i) => {
    container.appendChild(renderHttpCard(srv, i));
  });
}

function renderHttpCard(srv, index) {
  const card = document.createElement('div');
  card.className = 'section';
  card.dataset.httpIndex = index;
  const ssl = srv.ssl ? ' (SSL)' : '';
  const title = srv.name || `${srv.address}:${srv.port}${ssl}`;
  card.innerHTML = `
    <button class="btn-edit" title="Edit">&#9998;</button>
    <h2>${title}</h2>
    <dl>
      <dt>Address</dt><dd>${srv.address || '0.0.0.0'}:${srv.port}${ssl}</dd>
      ${srv.ssl ? `<dt>Cert</dt><dd>${srv.ssl.certfile || '-'}</dd>` : ''}
    </dl>
  `;
  card.querySelector('.btn-edit').addEventListener('click', () => showHttpEditor(index, srv));
  return card;
}

function showSessionEditor() {
  const container = $('http-servers');
  const existing = container.querySelector('[data-http-index="session"]');
  const card = document.createElement('div');
  card.className = 'section http-edit';
  card.dataset.httpIndex = 'session';
  const timeout = currentSettings.session_timeout;
  card.innerHTML = `
    <h3>Session</h3>
    <div class="field-row">
      <label>Timeout (seconds):</label>
      <input type="number" id="edit-session-timeout" min="0" placeholder="3600" value="${timeout || ''}">
    </div>
    <div class="edit-buttons">
      <button type="button" class="btn-primary" id="save-session-btn">Save</button>
      <button type="button" class="btn btn-secondary" id="cancel-session-btn">Cancel</button>
    </div>
  `;
  existing.replaceWith(card);
  card.querySelector('#save-session-btn').addEventListener('click', () => {
    const val = $('edit-session-timeout').value;
    const t = val.trim() === '' ? null : parseInt(val);
    if (val.trim() !== '' && (isNaN(t) || t < 0)) {
      alert('Invalid timeout value');
      return;
    }
    api('PUT', '/api/settings', {session_timeout: t}).then(() => loadSettings())
      .catch(e => { if (e !== 'unauthorized') alert(e); });
  });
  card.querySelector('#cancel-session-btn').addEventListener('click', () => loadSettings());
}

function showHttpEditor(index, srv) {
  const container = $('http-servers');
  const isNew = index === null;
  let card;
  if (isNew) {
    card = document.createElement('div');
    container.appendChild(card);
  } else {
    card = container.querySelector('[data-http-index="' + index + '"]');
  }
  card.className = 'section http-edit';
  card.dataset.httpIndex = isNew ? 'new' : index;
  const title = isNew ? 'New HTTP Server' : 'Edit HTTP Server';
  card.innerHTML = `
    <h3>${title}</h3>
    <div class="field-row">
      <label>Name:</label>
      <input type="text" class="http-name" value="${srv.name || ''}" placeholder="optional">
    </div>
    <div class="field-row">
      <label>Address:</label>
      <input type="text" class="http-address" value="${srv.address || '0.0.0.0'}" placeholder="0.0.0.0">
    </div>
    <div class="field-row">
      <label>Port:</label>
      <input type="number" class="http-port" value="${srv.port || 8080}" min="1" max="65535">
    </div>
    <div class="field-row">
      <label><input type="checkbox" class="http-ssl" ${srv.ssl ? 'checked' : ''}> SSL</label>
    </div>
    <div class="ssl-fields ${srv.ssl ? '' : 'hidden'}">
      <div class="field-row">
        <label>Certificate:</label>
        <input type="text" class="http-certfile" value="${srv.ssl?.certfile || ''}" placeholder="/path/to/cert.pem">
      </div>
      <div class="field-row">
        <label>Key:</label>
        <input type="text" class="http-keyfile" value="${srv.ssl?.keyfile || ''}" placeholder="/path/to/key.pem">
      </div>
    </div>
    <div class="edit-buttons">
      <button type="button" class="btn-primary http-save-btn">Save</button>
      ${!isNew ? '<button type="button" class="btn-danger http-delete-btn">Delete</button>' : ''}
      <button type="button" class="btn btn-secondary http-cancel-btn">Cancel</button>
    </div>
  `;
  card.querySelector('.http-ssl').addEventListener('change', e => {
    card.querySelector('.ssl-fields').classList.toggle('hidden', !e.target.checked);
  });
  card.querySelector('.http-save-btn').addEventListener('click', () => saveHttpServer(isNew ? null : index, card));
  card.querySelector('.http-cancel-btn').addEventListener('click', () => loadSettings());
  if (!isNew) {
    card.querySelector('.http-delete-btn').addEventListener('click', () => deleteHttpServer(index));
  }
}

function saveHttpServer(index, card) {
  const data = {
    address: card.querySelector('.http-address').value.trim() || '0.0.0.0',
    port: parseInt(card.querySelector('.http-port').value) || 8080,
  };
  const name = card.querySelector('.http-name').value.trim();
  if (name) data.name = name;
  if (card.querySelector('.http-ssl').checked) {
    const certfile = card.querySelector('.http-certfile').value.trim();
    const keyfile = card.querySelector('.http-keyfile').value.trim();
    if (!certfile || !keyfile) {
      alert('SSL requires certificate and key file paths');
      return;
    }
    data.ssl = {certfile, keyfile};
  }
  const method = index === null ? 'POST' : 'PUT';
  const path = index === null ? '/api/settings/http' : '/api/settings/http/' + index;
  api(method, path, data).then(() => {
    loadSettings();
  }).catch(e => {
    if (e !== 'unauthorized') alert(e);
  });
}

function deleteHttpServer(index) {
  if (!confirm('Delete this HTTP server?')) return;
  api('DELETE', '/api/settings/http/' + index).then(() => {
    loadSettings();
  }).catch(e => {
    if (e !== 'unauthorized') alert(e);
  });
}

function addHttpServer() {
  showHttpEditor(null, {address: '0.0.0.0', port: 8080});
}

// --- Init ---
function init() {
  initTheme();
  $('login-btn').addEventListener('click', doLogin);
  $('login-pass').addEventListener('keydown',
    e => { if (e.key === 'Enter') doLogin(); });
  $('logout-btn').addEventListener('click', doLogout);
  $('add-user-btn').addEventListener('click', addUser);
  $('add-token-btn').addEventListener('click', addToken);
  $('add-port-btn').addEventListener('click', addPort);
  $('add-http-btn').addEventListener('click', addHttpServer);

  document.querySelectorAll('nav button[data-tab]').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });
  window.addEventListener('hashchange', () => {
    const tab = location.hash.slice(1);
    if (['ports', 'users', 'settings'].includes(tab)) switchTab(tab);
  });

  api('GET', '/api/status').then(showApp).catch(showLogin);
}

document.addEventListener('DOMContentLoaded', init);
