"""
This module contains the tests for the accounts app.
"""
import django.contrib.auth
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = django.contrib.auth.get_user_model()


class UserTests(APITestCase):
    """ Test suite for the user-related API views. """

    def setUp(self):
        """ Set up initial data for the tests. """
        self.superuser = User.objects.create_superuser(
            username='superuser',
            email='superuser@example.com',
            password='password123',
            telephone='1234567890'
        )
        self.user = User.objects.create_user(
            username='regularuser',
            email='user@example.com',
            password='password123',
            telephone='0987654321'
        )
        self.client.login(username='superuser', password='password123')

    def test_get_all_users_as_superuser(self):
        """ Test retrieving all users as a superuser. """
        url = reverse('users-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_get_all_users_as_regular_user(self):
        """ Test retrieving all users as a regular user, expecting forbidden access. """
        self.client.logout()
        self.client.login(username='regularuser', password='password123')
        url = reverse('users-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_user_detail_as_superuser(self):
        """ Test retrieving a user's details as a superuser. """
        url = reverse('user-detail', args=[self.user.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], self.user.username)

    def test_get_user_detail_as_regular_user(self):
        """ Test retrieving another user's details as a regular user, expecting forbidden access. """
        self.client.logout()
        self.client.login(username='regularuser', password='password123')
        url = reverse('user-detail', args=[self.superuser.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_user_as_superuser(self):
        """ Test updating a user's details as a superuser. """
        url = reverse('user-detail', args=[self.user.id])
        data = {'username': 'updateduser'}
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'updateduser')

    def test_delete_user_as_superuser(self):
        """ Test logically deleting a user as a superuser. """
        url = reverse('user-detail', args=[self.user.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_complete_profile(self):
        """ Test completing a user's profile. """
        self.client.logout()
        self.client.login(username='regularuser', password='password123')
        url = reverse('complete-profile')
        data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'telephone': '1122334455'
        }
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'John')
        self.assertEqual(self.user.last_name, 'Doe')
        self.assertEqual(self.user.telephone, '1122334455')
        self.assertEqual(self.user.status, 'complete')
