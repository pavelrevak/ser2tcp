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
  const tab = ['status', 'ports', 'users'].includes(hash) ? hash : 'status';
  switchTab(tab, tab === 'status' ? initialData : null);
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
  if (tab === 'status') loadStatus(data);
  else if (tab === 'ports') loadPorts();
  else if (tab === 'users') loadUsers();
  if (location.hash !== '#' + tab) history.pushState(null, '', '#' + tab);
}

// --- Status ---
function loadStatus(data) {
  const root = $('status-content');
  const render = data => {
    root.replaceChildren();
    data.ports.forEach((p, i) => {
      const ser = p.serial || {};
      let name = ser.port || '';
      if (ser.match) {
        name = 'match: ' + Object.entries(ser.match).map(([k,v]) => k+'='+v).join(', ');
      }
      const connected = ser.connected;
      const div = el('div');
      div.className = 'section';
      const h = el('h2');
      h.appendChild(document.createTextNode('Port ' + i + ': ' + name + ' '));
      const badge = el('span', connected ? 'ON' : 'OFF');
      badge.className = 'badge ' + (connected ? 'badge-on' : 'badge-off');
      h.appendChild(badge);
      div.appendChild(h);
      const info = (ser.baudrate ? ser.baudrate + ' — ' : '') + (connected ? 'connected' : 'disconnected');
      div.appendChild(el('p', info));
      const ul = el('ul');
      (p.servers || []).forEach(s => {
        const proto = (s.protocol || 'tcp').toUpperCase();
        const addr = proto === 'SOCKET' ? s.address : s.address + ':' + s.port;
        const li = el('li', proto + ' — ' + addr);
        const clients = s.connections || [];
        if (clients.length) {
          const cul = el('ul');
          clients.forEach(c => cul.appendChild(el('li', c.address)));
          li.appendChild(cul);
        } else {
          li.appendChild(el('em', ' no connections'));
        }
        ul.appendChild(li);
      });
      div.appendChild(ul);
      root.appendChild(div);
    });
  };
  if (data) render(data);
  else api('GET', '/api/status').then(render).catch(() => {
    root.replaceChildren(el('p', 'Failed to load status', 'empty'));
  });
}

// --- Ports ---
function loadPorts() {
  const root = $('ports-content');
  api('GET', '/api/ports').then(ports => {
    root.replaceChildren();
    if (!ports.length) {
      root.replaceChildren(el('p', 'No serial ports detected', 'empty'));
      return;
    }
    const ul = el('ul');
    ports.forEach(p => {
      const li = el('li', p.device);
      const attrs = Object.entries(p).filter(([k]) => k !== 'device');
      if (attrs.length) {
        const dl = el('dl');
        attrs.forEach(([k, v]) => {
          dl.appendChild(el('dt', k));
          dl.appendChild(el('dd', v));
        });
        li.appendChild(dl);
      }
      ul.appendChild(li);
    });
    root.appendChild(ul);
  }).catch(() => {
    root.replaceChildren(el('p', 'Failed to load ports', 'empty'));
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
  $('login-pass').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
  $('logout-btn').addEventListener('click', doLogout);
  $('add-user-btn').addEventListener('click', addUser);

  document.querySelectorAll('nav button[data-tab]').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });
  window.addEventListener('hashchange', () => {
    const tab = location.hash.slice(1);
    if (['status', 'ports', 'users'].includes(tab)) switchTab(tab);
  });

  api('GET', '/api/status').then(showApp).catch(showLogin);
}

document.addEventListener('DOMContentLoaded', init);
