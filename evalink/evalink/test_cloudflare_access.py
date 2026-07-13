from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
import jwt

from evalink.cloudflare_access import (
    JWT_HEADER,
    authenticate_request,
    clear_cert_cache,
    get_or_create_user_from_claims,
    username_for_email,
)


@override_settings(
    CLOUDFLARE_ACCESS_ENABLED=True,
    CLOUDFLARE_ACCESS_TEAM_DOMAIN='myteam',
    CLOUDFLARE_ACCESS_AUD='test-aud',
)
class CloudflareAccessAuthTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        clear_cert_cache()

    def tearDown(self):
        clear_cert_cache()

    def test_username_for_email_uses_at_suffix(self):
        self.assertEqual(username_for_email('alice@example.com'), 'alice_at_example.com')

    def test_username_for_email_avoids_collision(self):
        User.objects.create_user(username='alice_at_example.com', email='other@example.com')
        self.assertEqual(username_for_email('alice@example.com'), 'alice_at_example.com_2')

    def test_get_or_create_user_is_non_admin_without_password(self):
        user = get_or_create_user_from_claims({'email': 'newuser@example.com'})
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.email, 'newuser@example.com')

    def test_get_or_create_user_reuses_existing_email(self):
        existing = User.objects.create_user(
            username='legacy',
            email='crew@example.com',
            password='local-only',
        )
        user = get_or_create_user_from_claims({'email': 'crew@example.com'})
        self.assertEqual(user.pk, existing.pk)

    @override_settings(CLOUDFLARE_ACCESS_ENABLED=False)
    def test_disabled_middleware_does_not_auto_login(self):
        request = self.client.request().wsgi_request
        request.META[JWT_HEADER] = 'fake-token'
        self.assertIsNone(authenticate_request(request))
        self.assertFalse(request.user.is_authenticated)

    @patch('evalink.cloudflare_access.decode_access_token', return_value={'email': 'sso@example.com'})
    def test_valid_jwt_auto_logs_in_and_grants_access(self, _decode):
        response = self.client.get(
            '/features.json',
            HTTP_CF_ACCESS_JWT_ASSERTION='signed-jwt',
        )

        self.assertEqual(response.status_code, 200)
        user = User.objects.get(email='sso@example.com')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.has_usable_password())

    @patch(
        'evalink.cloudflare_access.decode_access_token',
        side_effect=jwt.InvalidTokenError('bad token'),
    )
    def test_invalid_jwt_still_requires_login(self, _decode):
        response = self.client.get(
            '/features.json',
            HTTP_CF_ACCESS_JWT_ASSERTION='bad-jwt',
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    @patch(
        'evalink.cloudflare_access.decode_access_token',
        return_value={'email': 'sso@example.com'},
    )
    def test_existing_session_matching_email_is_reused(self, _decode):
        user = User.objects.create_user(
            username='sso_user',
            email='sso@example.com',
            password='unused',
        )
        user.set_unusable_password()
        user.save()

        self.client.force_login(user)
        before_id = self.client.session.session_key
        response = self.client.get(
            '/features.json',
            HTTP_CF_ACCESS_JWT_ASSERTION='signed-jwt',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session.session_key, before_id)
