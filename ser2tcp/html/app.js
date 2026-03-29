const $ = id => document.getElementById(id);
const el = (tag, text, cls) => {
  const e = document.createElement(tag);
  if (text) e.textContent = text;
  if (cls) e.className = cls;
  return e;
};

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
let detectedPorts = [];
let usedPorts = [];  // [{address, port, index}] from status

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
}

function showApp(initialData) {
  $('login-view').classList.add('hidden');
  $('app').classList.remove('hidden');
  updateUserInfo();
  const hash = location.hash.slice(1);
  const tab = ['ports', 'users'].includes(hash) ? hash : 'ports';
  switchTab(tab, tab === 'ports' ? initialData : null);
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
function switchTab(tab, data) {
  document.querySelectorAll('nav button[data-tab]').forEach(
    b => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('[id^="tab-"]').forEach(
    t => t.classList.toggle('hidden', t.id !== 'tab-' + tab));
  if (tab === 'ports') loadPorts(data);
  else if (tab === 'users') loadUsers();
  if (location.hash !== '#' + tab) history.pushState(null, '', '#' + tab);
}

// --- Ports ---
const MATCH_ATTRS = [
  'vid', 'pid', 'serial_number', 'manufacturer', 'product', 'location'
];
const PROTOCOLS = ['TCP', 'TELNET', 'SSL', 'SOCKET'];
const BAUDRATES = [300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200,
  230400, 460800, 921600];
const BYTESIZES = {8: 'EIGHTBITS', 7: 'SEVENBITS', 6: 'SIXBITS', 5: 'FIVEBITS'};
const PARITIES = ['NONE', 'EVEN', 'ODD', 'MARK', 'SPACE'];
const STOPBITS = {'1': 'ONE', '1.5': 'ONE_POINT_FIVE', '2': 'TWO'};

function loadPorts(statusData) {
  const root = $('ports-content');
  const render = (status, detected) => {
    detectedPorts = detected || [];
    usedPorts = [];
    status.ports.forEach((p, i) => {
      (p.servers || []).forEach(s => {
        if (s.port) usedPorts.push({address: s.address, port: s.port, index: i});
      });
    });
    root.replaceChildren();
    if (!status.ports.length) {
      root.appendChild(el('p', 'No ports configured', 'empty'));
    }
    status.ports.forEach((p, i) => root.appendChild(renderPortCard(p, i)));
    renderDetectedSection();
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
  // Show configured port or match
  if (ser.match) {
    const matchStr = Object.entries(ser.match)
      .map(([k,v]) => k + '=' + v).join(', ');
    div.appendChild(el('p', 'match: ' + matchStr, 'port-config-detail'));
  } else if (ser.port && port.name) {
    div.appendChild(el('p', 'port: ' + ser.port, 'port-config-detail'));
  }
  const ul = el('ul');
  (port.servers || []).forEach((s, si) => {
    const proto = (s.protocol || 'tcp').toUpperCase();
    const addr = proto === 'SOCKET' ? s.address : s.address + ':' + s.port;
    const li = el('li', proto + ' \u2014 ' + addr);
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
    } else {
      li.appendChild(el('em', ' no connections'));
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
  const ul = el('ul');
  detectedPorts.forEach(p => {
    const li = el('li');
    // Clickable device name → add port with direct path
    const devLink = el('a', p.device);
    devLink.href = '#';
    devLink.className = 'detect-link';
    devLink.title = 'Add new port with ' + p.device;
    devLink.onclick = e => {
      e.preventDefault();
      addPortFromDetected(p, null);
    };
    li.appendChild(devLink);
    if (p.description) li.appendChild(document.createTextNode(
      ' \u2014 ' + p.description));
    const attrs = MATCH_ATTRS.filter(a => p[a]);
    if (attrs.length) {
      const dl = el('dl');
      attrs.forEach(a => {
        dl.appendChild(el('dt', a));
        // Clickable match value → add port with this match checked
        const dd = document.createElement('dd');
        const matchLink = el('a', p[a]);
        matchLink.href = '#';
        matchLink.className = 'detect-link';
        matchLink.title = 'Add new port with match ' + a + '=' + p[a];
        matchLink.onclick = e => {
          e.preventDefault();
          addPortFromDetected(p, a);
        };
        dd.appendChild(matchLink);
        dl.appendChild(dd);
      });
      li.appendChild(dl);
    }
    ul.appendChild(li);
  });
  sec.appendChild(ul);
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
  if (ser.match) {
    config.serial.match = {...ser.match};
  }
  if (ser.port) config.serial.port = ser.port;
  if (ser.baudrate) config.serial.baudrate = ser.baudrate;
  if (ser.bytesize) config.serial.bytesize = ser.bytesize;
  if (ser.parity) config.serial.parity = ser.parity;
  if (ser.stopbits) config.serial.stopbits = ser.stopbits;
  config.servers = (port.servers || []).map(s => {
    const srv = {
      protocol: s.protocol.toLowerCase(),
      address: s.address,
    };
    if (s.port !== undefined) srv.port = s.port;
    if (s.ssl) srv.ssl = s.ssl;
    return srv;
  });
  if (!config.servers.length) {
    config.servers = [{protocol: 'tcp', address: '0.0.0.0', port: 10001}];
  }
  return config;
}

function showPortEditor(index, config) {
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

  const paramsDiv2 = el('div', null, 'field-row');
  paramsDiv2.appendChild(el('label', 'Data bits:'));
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
  paramsDiv2.appendChild(byteSel);

  paramsDiv2.appendChild(el('label', 'Parity:'));
  const paritySel = document.createElement('select');
  paritySel.id = 'edit-parity';
  PARITIES.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p;
    opt.textContent = p;
    if (config.serial.parity === p) opt.selected = true;
    paritySel.appendChild(opt);
  });
  paramsDiv2.appendChild(paritySel);

  paramsDiv2.appendChild(el('label', 'Stop bits:'));
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
  paramsDiv2.appendChild(stopSel);
  container.appendChild(paramsDiv2);

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
  cancelBtn.onclick = () => loadPorts();
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

  const removeBtn = el('button', '\u00d7', 'btn-remove');
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

  // Address + Port (or Path for SOCKET)
  const addrRow = el('div', null, 'field-row');
  const addrLabel = el('label', 'Address:');
  addrRow.appendChild(addrLabel);
  const addrInput = document.createElement('input');
  addrInput.type = 'text';
  addrInput.className = 'srv-address';
  addrInput.value = srv.address || '0.0.0.0';
  addrRow.appendChild(addrInput);
  const portLabel = el('label', 'Port:');
  portLabel.className = 'srv-port-label';
  addrRow.appendChild(portLabel);
  const portInput = document.createElement('input');
  portInput.type = 'number';
  portInput.className = 'srv-port';
  portInput.value = srv.port || '';
  addrRow.appendChild(portInput);
  box.appendChild(addrRow);

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

  // Update visibility based on protocol
  const updateProtoFields = () => {
    const proto = protoSel.value;
    const isSocket = proto === 'SOCKET';
    const isSsl = proto === 'SSL';
    addrLabel.textContent = isSocket ? 'Path:' : 'Address:';
    portLabel.classList.toggle('hidden', isSocket);
    portInput.classList.toggle('hidden', isSocket);
    sslDiv.classList.toggle('hidden', !isSsl);
    if (isSocket) {
      addrInput.value = addrInput.value === '0.0.0.0' ? '' : addrInput.value;
    }
  };
  const checkConflict = () => {
    const proto = protoSel.value;
    if (proto === 'SOCKET') { portInput.style.borderColor = ''; return; }
    const addr = addrInput.value.trim();
    const p = parseInt(portInput.value);
    if (!p) { portInput.style.borderColor = ''; return; }
    const editIndex = parseInt(
      (document.querySelector('.port-edit') || {}).dataset?.portIndex);
    const conflict = usedPorts.find(u =>
      u.port === p && u.address === addr && u.index !== editIndex);
    portInput.style.borderColor = conflict ? '#e55' : '';
    portInput.title = conflict
      ? 'Port already used by Port ' + conflict.index : '';
  };
  portInput.oninput = checkConflict;
  addrInput.oninput = checkConflict;
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
    srv.address = box.querySelector('.srv-address').value.trim();
    if (proto !== 'socket') {
      const port = box.querySelector('.srv-port').value;
      if (port) srv.port = parseInt(port);
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
    config.servers.push(srv);
  });

  return config;
}

function savePort(index) {
  const config = collectConfig();
  const method = index !== null ? 'PUT' : 'POST';
  const path = index !== null ? '/api/ports/' + index : '/api/ports';
  api(method, path, config).then(() => loadPorts()).catch(e => {
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
  api('DELETE', '/api/ports/' + index).then(() => loadPorts()).catch(e => {
    if (e !== 'unauthorized') alert(e);
  });
}

// --- Users ---
function loadUsers() {
  const root = $('users-content');
  const adminCb = $('new-admin');
  api('GET', '/api/users').then(users => {
    root.replaceChildren();
    if (!users.length) {
      root.replaceChildren(el('p', 'No users configured', 'empty'));
      adminCb.checked = true;
      adminCb.disabled = true;
      return;
    }
    adminCb.checked = false;
    adminCb.disabled = false;
    const table = el('table');
    const thead = el('thead');
    const hr = el('tr');
    ['Login', 'Admin', ''].forEach(t => hr.appendChild(el('th', t)));
    thead.appendChild(hr);
    table.appendChild(thead);
    const tbody = el('tbody');
    users.forEach(u => {
      const tr = el('tr');
      tr.appendChild(el('td', u.login));
      const adminTd = el('td');
      if (u.admin) {
        const b = el('span', 'admin');
        b.className = 'badge badge-admin';
        adminTd.appendChild(b);
      }
      tr.appendChild(adminTd);
      const actionsTd = el('td');
      const chpBtn = el('button', 'Password');
      chpBtn.className = 'btn-primary btn-small';
      chpBtn.onclick = () => changePassword(u.login);
      actionsTd.appendChild(chpBtn);
      actionsTd.appendChild(document.createTextNode(' '));
      const delBtn = el('button', 'Delete');
      delBtn.className = 'btn-danger btn-small';
      delBtn.onclick = () => deleteUser(u.login);
      actionsTd.appendChild(delBtn);
      tr.appendChild(actionsTd);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    root.appendChild(table);
  }).catch(() => {
    root.replaceChildren(el('p', 'Failed to load users', 'empty'));
    adminCb.checked = true;
    adminCb.disabled = true;
  });
}

async function changePassword(login) {
  const pass = prompt('New password for ' + login + ':');
  if (pass) {
    const hashed = await hashPassword(pass);
    api('PUT', '/api/users/' + encodeURIComponent(login), {password: hashed})
      .then(loadUsers)
      .catch(alert);
  }
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

async function addUser() {
  const login = $('new-login').value;
  const password = $('new-pass').value;
  const admin = $('new-admin').checked;
  const errEl = $('user-error');
  errEl.classList.add('hidden');
  if (!login || !password) {
    errEl.textContent = 'Login and password required';
    errEl.classList.remove('hidden');
    return;
  }
  const hashed = await hashPassword(password);
  api('POST', '/api/users', {login, password: hashed, admin}).then(data => {
    if (data.token) setCredentials(data.token, login);
    $('new-login').value = '';
    $('new-pass').value = '';
    $('new-admin').checked = false;
    loadUsers();
  }).catch(e => {
    errEl.textContent = e;
    errEl.classList.remove('hidden');
  });
}

// --- Init ---
function init() {
  $('login-btn').addEventListener('click', doLogin);
  $('login-pass').addEventListener('keydown',
    e => { if (e.key === 'Enter') doLogin(); });
  $('logout-btn').addEventListener('click', doLogout);
  $('add-user-btn').addEventListener('click', addUser);
  $('add-port-btn').addEventListener('click', addPort);

  document.querySelectorAll('nav button[data-tab]').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });
  window.addEventListener('hashchange', () => {
    const tab = location.hash.slice(1);
    if (['ports', 'users'].includes(tab)) switchTab(tab);
  });

  api('GET', '/api/status').then(showApp).catch(showLogin);
}

document.addEventListener('DOMContentLoaded', init);
