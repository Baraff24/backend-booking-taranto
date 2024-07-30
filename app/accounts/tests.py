# """
# This module contains the tests for the accounts app.
# """
# import json
# from unittest.mock import patch
#
# import django.contrib.auth
# import stripe
# from django.urls import reverse
# from rest_framework import status
# from rest_framework.test import APITestCase, APIClient
#
# User = django.contrib.auth.get_user_model()
#
#
# class UserTests(APITestCase):
#     """ Test suite for the user-related API views. """
#
#     def setUp(self):
#         """ Set up initial data for the tests. """
#         self.superuser = User.objects.create_superuser(
#             username='superuser',
#             email='superuser@example.com',
#             password='password123',
#             telephone='1234567890'
#         )
#         self.user = User.objects.create_user(
#             username='regularuser',
#             email='user@example.com',
#             password='password123',
#             telephone='0987654321'
#         )
#         self.client.login(username='superuser', password='password123')
#
#     def test_get_all_users_as_superuser(self):
#         """ Test retrieving all users as a superuser. """
#         url = reverse('users-list')
#         response = self.client.get(url)
#         self.assertEqual(response.status_code, status.HTTP_200_OK)
#         self.assertEqual(len(response.data), 2)
#
#     def test_get_all_users_as_regular_user(self):
#         """ Test retrieving all users as a regular user, expecting forbidden access. """
#         self.client.logout()
#         self.client.login(username='regularuser', password='password123')
#         url = reverse('users-list')
#         response = self.client.get(url)
#         self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
#
#     def test_get_user_detail_as_superuser(self):
#         """ Test retrieving a user's details as a superuser. """
#         url = reverse('user-detail', args=[self.user.id])
#         response = self.client.get(url)
#         self.assertEqual(response.status_code, status.HTTP_200_OK)
#         self.assertEqual(response.data['username'], self.user.username)
#
#     def test_get_user_detail_as_regular_user(self):
#         """ Test retrieving another user's details as a regular user, expecting forbidden access. """
#         self.client.logout()
#         self.client.login(username='regularuser', password='password123')
#         url = reverse('user-detail', args=[self.superuser.id])
#         response = self.client.get(url)
#         self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
#
#     def test_update_user_as_superuser(self):
#         """ Test updating a user's details as a superuser. """
#         url = reverse('user-detail', args=[self.user.id])
#         data = {'username': 'updateduser'}
#         response = self.client.put(url, data)
#         self.assertEqual(response.status_code, status.HTTP_200_OK)
#         self.user.refresh_from_db()
#         self.assertEqual(self.user.username, 'updateduser')
#
#     def test_delete_user_as_superuser(self):
#         """ Test logically deleting a user as a superuser. """
#         url = reverse('user-detail', args=[self.user.id])
#         response = self.client.delete(url)
#         self.assertEqual(response.status_code, status.HTTP_200_OK)
#         self.user.refresh_from_db()
#         self.assertFalse(self.user.is_active)
#
#     def test_complete_profile(self):
#         """ Test completing a user's profile. """
#         self.client.logout()
#         self.client.login(username='regularuser', password='password123')
#         url = reverse('complete-profile')
#         data = {
#             'first_name': 'John',
#             'last_name': 'Doe',
#             'telephone': '1122334455'
#         }
#         response = self.client.put(url, data)
#         self.assertEqual(response.status_code, status.HTTP_200_OK)
#         self.user.refresh_from_db()
#         self.assertEqual(self.user.first_name, 'John')
#         self.assertEqual(self.user.last_name, 'Doe')
#         self.assertEqual(self.user.telephone, '1122334455')
#         self.assertEqual(self.user.status, 'complete')
#
#
# class CreatePaymentIntentViewTests(APITestCase):
#     def setUp(self):
#         self.client = APIClient()
#         self.url = reverse('create-payment-intent')
#         self.user = self.setup_user()
#         self.client.force_authenticate(user=self.user)
#
#     @staticmethod
#     def setup_user():
#         from accounts.models import User
#         return User.objects.create_user(
#             username='testuser',
#             email='testuser@example.com',
#             password='testpass'
#         )
#
#     @patch('stripe.PaymentIntent.create')
#     def test_create_payment_intent_success(self, mock_create):
#         mock_create.return_value = {
#             'client_secret': 'test_client_secret'
#         }
#         data = {
#             'amount': 1000,
#             'currency': 'eur'
#         }
#         response = self.client.post(self.url, data, format='json')
#         self.assertEqual(response.status_code, status.HTTP_200_OK)
#         self.assertIn('clientSecret', response.data)
#         self.assertEqual(response.data['clientSecret'], 'test_client_secret')
#
#     def test_create_payment_intent_missing_amount(self):
#         data = {
#             'currency': 'eur'
#         }
#         response = self.client.post(self.url, data, format='json')
#         self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
#         self.assertIn('amount', response.data)
#
#
# class StripeWebhookViewTests(APITestCase):
#     def setUp(self):
#         self.client = APIClient()
#         self.url = reverse('stripe-webhook')
#
#     @patch('stripe.Webhook.construct_event')
#     def test_webhook_payment_intent_succeeded(self, mock_construct_event):
#         event_data = {
#             'id': 'evt_test',
#             'type': 'payment_intent.succeeded',
#             'data': {
#                 'object': {
#                     'id': 'pi_test'
#                 }
#             }
#         }
#         mock_construct_event.return_value = event_data
#
#         payload = json.dumps(event_data)
#         sig_header = 't=1492774577,v1=signature'
#
#         response = self.client.post(self.url, payload, format='json', HTTP_STRIPE_SIGNATURE=sig_header)
#         self.assertEqual(response.status_code, status.HTTP_200_OK)
#         self.assertEqual(response.data['status'], 'success')
#
#     @patch('stripe.Webhook.construct_event')
#     def test_webhook_invalid_signature(self, mock_construct_event):
#         mock_construct_event.side_effect = stripe.error.SignatureVerificationError(
#             'Invalid signature', 'sig_test'
#         )
#
#         payload = json.dumps({
#             'id': 'evt_test',
#             'type': 'payment_intent.succeeded',
#         })
#         sig_header = 't=1492774577,v1=invalid_signature'
#
#         response = self.client.post(self.url, payload, format='json', HTTP_STRIPE_SIGNATURE=sig_header)
#         self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
#         self.assertIn('error', response.data)
#
#     @patch('stripe.Webhook.construct_event')
#     def test_webhook_invalid_payload(self, mock_construct_event):
#         mock_construct_event.side_effect = ValueError('Invalid payload')
#
#         payload = 'invalid_payload'
#         sig_header = 't=1492774577,v1=signature'
#
#         response = self.client.post(self.url, payload, format='json', HTTP_STRIPE_SIGNATURE=sig_header)
#         self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
#         self.assertIn('error', response.data)
