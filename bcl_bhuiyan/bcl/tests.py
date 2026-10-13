
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class CandidateAuthenticationTests(TestCase):

    def test_registration_page(self):
        response = self.client.get(
            reverse("bcl:register")
        )
        self.assertEqual(response.status_code, 200)

    def test_candidate_registration(self):
        response = self.client.post(
            reverse("bcl:register"),
            {
                "first_name": "Test",
                "last_name": "Candidate",
                "username": "testcandidate",
                "email": "candidate@example.com",
                "password1": "TestPass@2026abc",
                "password2": "TestPass@2026abc",
            },
        )

        self.assertRedirects(
            response,
            reverse("bcl:dashboard"),
        )

        self.assertTrue(
            User.objects.filter(
                username="testcandidate"
            ).exists()
        )

    def test_duplicate_email_rejected(self):
        User.objects.create_user(
            username="candidate1",
            email="candidate@example.com",
            password="TestPass@2026abc",
        )

        response = self.client.post(
            reverse("bcl:register"),
            {
                "first_name": "Second",
                "last_name": "Candidate",
                "username": "candidate2",
                "email": "CANDIDATE@example.com",
                "password1": "TestPass@2026abc",
                "password2": "TestPass@2026abc",
            },
        )

        self.assertEqual(response.status_code, 200)

        self.assertFalse(
            User.objects.filter(
                username="candidate2"
            ).exists()
        )

    def test_dashboard_requires_login(self):
        response = self.client.get(
            reverse("bcl:dashboard")
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("bcl:login"),
            response.url,
        )

    def test_login(self):
        User.objects.create_user(
            username="candidate",
            password="TestPass@2026abc",
        )

        response = self.client.post(
            reverse("bcl:login"),
            {
                "username": "candidate",
                "password": "TestPass@2026abc",
            },
        )

        self.assertRedirects(
            response,
            reverse("bcl:dashboard"),
        )

    def test_logout(self):
        user = User.objects.create_user(
            username="candidate",
            password="TestPass@2026abc",
        )

        self.client.force_login(user)

        response = self.client.post(
            reverse("bcl:logout")
        )

        self.assertRedirects(
            response,
            reverse("bcl:login"),
        )

        dashboard = self.client.get(
            reverse("bcl:dashboard")
        )

        self.assertEqual(dashboard.status_code, 302)

    def test_logout_requires_post(self):
        user = User.objects.create_user(
            username="candidate",
            password="TestPass@2026abc",
        )

        self.client.force_login(user)

        response = self.client.get(
            reverse("bcl:logout")
        )

        self.assertEqual(response.status_code, 405)
