"""Tests for auth module"""

import time
import unittest

from ser2tcp.http_auth import (
    hash_password, verify_password, ensure_hashed, SessionManager)


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

    def test_ensure_hashed_plain(self):
        result = ensure_hashed('mypass')
        self.assertTrue(result.startswith('sha256:'))
        self.assertTrue(verify_password('mypass', result))

    def test_ensure_hashed_already_hashed(self):
        h = hash_password('mypass')
        self.assertEqual(ensure_hashed(h), h)


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

    # User management tests

    def test_add_first_user_is_admin(self):
        mgr = self._make_manager()
        mgr.add_user('new', 'pass123')
        token = mgr.login('new', 'pass123')
        user = mgr.authenticate(token)
        self.assertTrue(user['admin'])

    def test_add_first_user_admin_forced(self):
        mgr = self._make_manager()
        mgr.add_user('new', 'pass123', admin=False)
        token = mgr.login('new', 'pass123')
        user = mgr.authenticate(token)
        self.assertTrue(user['admin'])

    def test_add_second_user_not_admin(self):
        mgr = self._make_manager(users=[self._make_user()])
        mgr.add_user('new', 'pass123')
        token = mgr.login('new', 'pass123')
        user = mgr.authenticate(token)
        self.assertFalse(user['admin'])

    def test_add_user(self):
        mgr = self._make_manager()
        self.assertTrue(mgr.add_user('new', 'pass123'))
        token = mgr.login('new', 'pass123')
        self.assertIsNotNone(token)

    def test_add_user_with_hash(self):
        mgr = self._make_manager()
        h = hash_password('secret')
        self.assertTrue(mgr.add_user('new', h))
        token = mgr.login('new', 'secret')
        self.assertIsNotNone(token)

    def test_add_user_duplicate(self):
        mgr = self._make_manager(users=[self._make_user()])
        self.assertFalse(mgr.add_user('admin', 'other'))

    def test_add_user_with_admin(self):
        mgr = self._make_manager()
        mgr.add_user('new', 'pass', admin=True)
        token = mgr.login('new', 'pass')
        user = mgr.authenticate(token)
        self.assertTrue(user['admin'])

    def test_add_user_with_timeout(self):
        mgr = self._make_manager()
        mgr.add_user('new', 'pass', session_timeout=120)
        token = mgr.login('new', 'pass')
        self.assertEqual(mgr._sessions[token]['timeout'], 120)

    def test_update_user_password(self):
        mgr = self._make_manager(users=[self._make_user()])
        self.assertTrue(mgr.update_user('admin', password='newpass'))
        self.assertIsNone(mgr.login('admin', 'pass'))
        self.assertIsNotNone(mgr.login('admin', 'newpass'))

    def test_update_user_password_hash(self):
        mgr = self._make_manager(users=[self._make_user()])
        h = hash_password('hashed')
        mgr.update_user('admin', password=h)
        self.assertIsNotNone(mgr.login('admin', 'hashed'))

    def test_update_user_admin(self):
        mgr = self._make_manager(users=[self._make_user()])
        mgr.update_user('admin', admin=True)
        token = mgr.login('admin', 'pass')
        self.assertTrue(mgr.authenticate(token)['admin'])

    def test_update_user_not_found(self):
        mgr = self._make_manager()
        self.assertFalse(mgr.update_user('nobody', password='x'))

    def test_delete_user(self):
        mgr = self._make_manager(users=[
            self._make_user(login='admin', admin=True),
            self._make_user(login='viewer')])
        self.assertTrue(mgr.delete_user('viewer'))
        self.assertIsNone(mgr.login('viewer', 'pass'))

    def test_delete_user_not_found(self):
        mgr = self._make_manager()
        self.assertFalse(mgr.delete_user('nobody'))

    def test_delete_user_invalidates_sessions(self):
        mgr = self._make_manager(users=[
            self._make_user(login='admin', admin=True),
            self._make_user(login='viewer')])
        token = mgr.login('viewer', 'pass')
        mgr.delete_user('viewer')
        self.assertIsNone(mgr.authenticate(token))

    def test_delete_last_admin_refused(self):
        mgr = self._make_manager(users=[
            self._make_user(login='admin', admin=True)])
        result = mgr.delete_user('admin')
        self.assertIsInstance(result, str)
        self.assertIn('admin', result.lower())

    def test_delete_last_admin_allowed_with_admin_token(self):
        mgr = self._make_manager(
            users=[self._make_user(login='admin', admin=True)],
            tokens=[{'token': 'tok', 'name': 'api', 'admin': True}])
        self.assertTrue(mgr.delete_user('admin'))
        self.assertFalse(mgr.is_empty)

    def test_delete_admin_when_another_exists(self):
        mgr = self._make_manager(users=[
            self._make_user(login='admin1', admin=True),
            self._make_user(login='admin2', admin=True)])
        self.assertTrue(mgr.delete_user('admin1'))

    def test_update_remove_last_admin_refused(self):
        mgr = self._make_manager(users=[
            self._make_user(login='admin', admin=True)])
        result = mgr.update_user('admin', admin=False)
        self.assertIsInstance(result, str)
        token = mgr.login('admin', 'pass')
        self.assertTrue(mgr.authenticate(token)['admin'])

    def test_list_users(self):
        mgr = self._make_manager(users=[
            self._make_user(login='a'),
            self._make_user(login='b', admin=True)])
        users = mgr.list_users()
        self.assertEqual(len(users), 2)
        logins = {u['login'] for u in users}
        self.assertEqual(logins, {'a', 'b'})
        for u in users:
            self.assertNotIn('password', u)

    def test_get_auth_config(self):
        mgr = self._make_manager(
            users=[self._make_user()],
            tokens=[{'token': 'key', 'name': 'bot'}])
        config = mgr.get_auth_config()
        self.assertIn('users', config)
        self.assertIn('tokens', config)
        self.assertEqual(len(config['users']), 1)
        self.assertEqual(config['users'][0]['login'], 'admin')
