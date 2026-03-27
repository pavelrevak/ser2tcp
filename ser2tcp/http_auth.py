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

    def login(self, login, password):
        """Authenticate user, return session token or None"""
        user = self._users.get(login)
        if not user:
            return None
        if not verify_password(password, user['password']):
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

    def cleanup(self):
        """Remove expired sessions"""
        now = _time.time()
        expired = [
            t for t, s in self._sessions.items()
            if now > s['expires']]
        for token in expired:
            del self._sessions[token]
