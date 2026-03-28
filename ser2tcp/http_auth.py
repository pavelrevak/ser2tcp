"""Authentication and session management"""

import hashlib as _hashlib
import secrets as _secrets
import time as _time


DEFAULT_SESSION_TIMEOUT = 3600


def hash_password(password):
    """Hash password with SHA-256 and random salt"""
    salt = _secrets.token_hex(16)
    h = _hashlib.sha256((salt + password).encode()).hexdigest()
    return f"sha256:{salt}:{h}"


def ensure_hashed(password):
    """Return password as hash - hash if plain, keep if already hashed"""
    if password.startswith('sha256:'):
        return password
    return hash_password(password)


def verify_password(password, stored):
    """Verify password against stored hash"""
    if not stored.startswith('sha256:'):
        return False
    parts = stored.split(':')
    if len(parts) != 3:
        return False
    salt = parts[1]
    expected = parts[2]
    h = _hashlib.sha256((salt + password).encode()).hexdigest()
    return _secrets.compare_digest(h, expected)


class SessionManager():
    """Manage authentication sessions"""

    def __init__(self, config):
        self._users = {}
        self._tokens = {}
        self._sessions = {}
        self._default_timeout = config.get(
            'session_timeout', DEFAULT_SESSION_TIMEOUT)
        for user in config.get('users', []):
            self._users[user['login']] = user
        for token_cfg in config.get('tokens', []):
            self._tokens[token_cfg['token']] = token_cfg

    @property
    def is_empty(self):
        """True if no users and no tokens configured"""
        return not self._users and not self._tokens

    def login(self, login, password):
        """Authenticate user, return session token or None"""
        user = self._users.get(login)
        if not user:
            return None
        if not verify_password(password, user['password']):
            return None
        return self.create_session(login)

    def create_session(self, login):
        """Create session for user without password check, return token"""
        user = self._users.get(login)
        if not user:
            return None
        token = _secrets.token_hex(32)
        self._sessions[token] = {
            'login': login,
            'admin': user.get('admin', False),
            'timeout': user.get('session_timeout', self._default_timeout),
            'expires': _time.time() + user.get(
                'session_timeout', self._default_timeout),
        }
        return token

    def logout(self, token):
        """Remove session"""
        self._sessions.pop(token, None)

    def authenticate(self, token):
        """Validate token (session or API), return user info or None"""
        # Check API tokens first
        token_cfg = self._tokens.get(token)
        if token_cfg:
            return {
                'login': token_cfg.get('name', 'token'),
                'admin': token_cfg.get('admin', False),
            }
        # Check sessions
        session = self._sessions.get(token)
        if not session:
            return None
        if _time.time() > session['expires']:
            del self._sessions[token]
            return None
        # Renew session
        session['expires'] = _time.time() + session['timeout']
        return {
            'login': session['login'],
            'admin': session['admin'],
        }

    def list_users(self):
        """Return list of users (without passwords)"""
        return [
            {k: v for k, v in user.items() if k != 'password'}
            for user in self._users.values()]

    def add_user(self, login, password, **kwargs):
        """Add user, return True on success, False if exists.
        First user is always admin."""
        if login in self._users:
            return False
        user = {'login': login, 'password': ensure_hashed(password)}
        if not self._users:
            user['admin'] = True
        else:
            if 'admin' in kwargs:
                user['admin'] = kwargs['admin']
        if 'session_timeout' in kwargs:
            user['session_timeout'] = kwargs['session_timeout']
        self._users[login] = user
        return True

    def update_user(self, login, **kwargs):
        """Update user, return True on success, False/string on error"""
        user = self._users.get(login)
        if not user:
            return False
        if 'admin' in kwargs and not kwargs['admin']:
            if user.get('admin') and self._admin_count() <= 1:
                return 'Cannot remove last admin'
        if 'password' in kwargs:
            user['password'] = ensure_hashed(kwargs['password'])
        if 'admin' in kwargs:
            user['admin'] = kwargs['admin']
        if 'session_timeout' in kwargs:
            user['session_timeout'] = kwargs['session_timeout']
        return True

    def _admin_count(self):
        """Count admin users"""
        return sum(1 for u in self._users.values() if u.get('admin'))

    def delete_user(self, login):
        """Delete user, return True on success, False if not found.
        Deleting last admin disables authentication."""
        if login not in self._users:
            return False
        del self._users[login]
        # Invalidate all sessions for this user
        to_remove = [
            t for t, s in self._sessions.items()
            if s['login'] == login]
        for token in to_remove:
            del self._sessions[token]
        return True

    def get_auth_config(self):
        """Return auth config for persistence"""
        config = {'session_timeout': self._default_timeout}
        if self._users:
            config['users'] = list(self._users.values())
        if self._tokens:
            config['tokens'] = list(self._tokens.values())
        return config

    def cleanup(self):
        """Remove expired sessions"""
        now = _time.time()
        expired = [
            t for t, s in self._sessions.items()
            if now > s['expires']]
        for token in expired:
            del self._sessions[token]
