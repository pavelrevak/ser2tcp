"""Tests for auth module"""

import time
import unittest

from ser2tcp.http_auth import hash_password, verify_password, SessionManager


class TestHashPassword(unittest.TestCase):
    def test_hash_format(self):
        h = hash_password('secret')
        self.assertTrue(h.startswith('sha256:'))
        parts = h.split(':')
        self.assertEqual(len(parts), 3)
        self.assertEqual(len(parts[1]), 32)  # salt hex
        self.assertEqual(len(parts[2]), 64)  # sha256 hex

    def test_different_salts(self):
        h1 = hash_password('secret')
        h2 = hash_password('secret')
        self.assertNotEqual(h1, h2)

    def test_verify_correct(self):
        h = hash_password('secret')
        self.assertTrue(verify_password('secret', h))

    def test_verify_wrong(self):
        h = hash_password('secret')
        self.assertFalse(verify_password('wrong', h))

    def test_verify_invalid_format(self):
        self.assertFalse(verify_password('x', 'plaintext'))
        self.assertFalse(verify_password('x', 'sha256:'))
        self.assertFalse(verify_password('x', 'sha256:a:b:c'))
        self.assertFalse(verify_password('x', 'md5:salt:hash'))


class TestSessionManager(unittest.TestCase):
    def _make_manager(self, users=None, tokens=None, session_timeout=3600):
        config = {'session_timeout': session_timeout}
        if users:
            config['users'] = users
        if tokens:
            config['tokens'] = tokens
        return SessionManager(config)

    def _make_user(self, login='admin', password='pass', admin=False,
            session_timeout=None):
        user = {
            'login': login,
            'password': hash_password(password),
            'admin': admin,
        }
        if session_timeout is not None:
            user['session_timeout'] = session_timeout
        return user

    def test_login_success(self):
        mgr = self._make_manager(users=[self._make_user()])
        token = mgr.login('admin', 'pass')
        self.assertIsNotNone(token)
        self.assertEqual(len(token), 64)

    def test_login_wrong_password(self):
        mgr = self._make_manager(users=[self._make_user()])
        self.assertIsNone(mgr.login('admin', 'wrong'))

    def test_login_unknown_user(self):
        mgr = self._make_manager(users=[self._make_user()])
        self.assertIsNone(mgr.login('nobody', 'pass'))

    def test_login_no_users(self):
        mgr = self._make_manager()
        self.assertIsNone(mgr.login('admin', 'pass'))

    def test_authenticate_session(self):
        mgr = self._make_manager(users=[
            self._make_user(admin=True)])
        token = mgr.login('admin', 'pass')
        user = mgr.authenticate(token)
        self.assertIsNotNone(user)
        self.assertEqual(user['login'], 'admin')
        self.assertTrue(user['admin'])

    def test_authenticate_non_admin(self):
        mgr = self._make_manager(users=[
            self._make_user(login='viewer', admin=False)])
        token = mgr.login('viewer', 'pass')
        user = mgr.authenticate(token)
        self.assertFalse(user['admin'])

    def test_authenticate_invalid_token(self):
        mgr = self._make_manager(users=[self._make_user()])
        self.assertIsNone(mgr.authenticate('invalid'))

    def test_authenticate_api_token(self):
        mgr = self._make_manager(tokens=[
            {'token': 'my-api-key', 'name': 'bot', 'admin': False}])
        user = mgr.authenticate('my-api-key')
        self.assertIsNotNone(user)
        self.assertEqual(user['login'], 'bot')
        self.assertFalse(user['admin'])

    def test_authenticate_api_token_admin(self):
        mgr = self._make_manager(tokens=[
            {'token': 'key', 'name': 'admin-bot', 'admin': True}])
        user = mgr.authenticate('key')
        self.assertTrue(user['admin'])

    def test_authenticate_api_token_default_name(self):
        mgr = self._make_manager(tokens=[{'token': 'key'}])
        user = mgr.authenticate('key')
        self.assertEqual(user['login'], 'token')

    def test_logout(self):
        mgr = self._make_manager(users=[self._make_user()])
        token = mgr.login('admin', 'pass')
        mgr.logout(token)
        self.assertIsNone(mgr.authenticate(token))

    def test_logout_unknown_token(self):
        mgr = self._make_manager()
        mgr.logout('nonexistent')  # should not raise

    def test_session_expiration(self):
        mgr = self._make_manager(
            users=[self._make_user()], session_timeout=0.1)
        token = mgr.login('admin', 'pass')
        self.assertIsNotNone(mgr.authenticate(token))
        time.sleep(0.2)
        self.assertIsNone(mgr.authenticate(token))

    def test_session_renewal(self):
        mgr = self._make_manager(
            users=[self._make_user()], session_timeout=0.5)
        token = mgr.login('admin', 'pass')
        time.sleep(0.3)
        # Access renews expiration
        self.assertIsNotNone(mgr.authenticate(token))
        time.sleep(0.3)
        # Still valid because renewed
        self.assertIsNotNone(mgr.authenticate(token))

    def test_per_user_timeout(self):
        mgr = self._make_manager(
            users=[self._make_user(session_timeout=0.1)],
            session_timeout=3600)
        token = mgr.login('admin', 'pass')
        time.sleep(0.2)
        self.assertIsNone(mgr.authenticate(token))

    def test_cleanup(self):
        mgr = self._make_manager(
            users=[self._make_user()], session_timeout=0.1)
        t1 = mgr.login('admin', 'pass')
        time.sleep(0.2)
        mgr.cleanup()
        self.assertEqual(len(mgr._sessions), 0)

    def test_cleanup_keeps_valid(self):
        mgr = self._make_manager(
            users=[self._make_user()], session_timeout=3600)
        t1 = mgr.login('admin', 'pass')
        mgr.cleanup()
        self.assertEqual(len(mgr._sessions), 1)

    def test_multiple_sessions(self):
        mgr = self._make_manager(users=[self._make_user()])
        t1 = mgr.login('admin', 'pass')
        t2 = mgr.login('admin', 'pass')
        self.assertNotEqual(t1, t2)
        self.assertIsNotNone(mgr.authenticate(t1))
        self.assertIsNotNone(mgr.authenticate(t2))
        mgr.logout(t1)
        self.assertIsNone(mgr.authenticate(t1))
        self.assertIsNotNone(mgr.authenticate(t2))
