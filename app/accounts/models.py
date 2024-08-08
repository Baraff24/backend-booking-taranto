"""
This module contains the models for the accounts app.
"""
import uuid

from django.db import models
from django.contrib.auth.models import AbstractUser

from .constants import (STATUS_CHOICES, PENDING_COMPLETE_DATA, TYPE_VALUES,
                        CUSTOMER, ROOM_STATUS, AVAILABLE, STATUS_RESERVATION, UNPAID)


class User(AbstractUser):
    """
    Custom user model that extends the default Django user model.
    The default Django user model has the following fields:
    - username
    - password
    - email
    """
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    telephone = models.CharField(max_length=20, unique=True, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                              default=PENDING_COMPLETE_DATA)
    type = models.CharField(max_length=10, choices=TYPE_VALUES, default=CUSTOMER)

    def __str__(self):
        return str({f"{self.first_name} {self.last_name} - {self.email}"})


class Structure(models.Model):
    """
    Model that represents the structure, that is the building where the rooms are located.
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    address = models.CharField(max_length=200)
    cis = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return str(self.name)


class StructureImage(models.Model):
    """
    Model that represents the image of the structure.
    """
    structure = models.ForeignKey(Structure, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='structure_images/')
    alt = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return str(self.structure)


class Room(models.Model):
    """
    Model that represents the room.
    """
    structure = models.ForeignKey(Structure, on_delete=models.CASCADE, related_name='rooms')
    room_status = models.CharField(max_length=20, choices=ROOM_STATUS, default=AVAILABLE)
    name = models.CharField(max_length=100)
    services = models.TextField(blank=True)
    cost_per_night = models.DecimalField(max_digits=10, decimal_places=2)
    max_people = models.IntegerField()

    def __str__(self):
        return str(self.name)


class Reservation(models.Model):
    """
    Model that represents the reservation.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reservations')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='reservations')
    reservation_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    check_in = models.DateField()
    check_out = models.DateField()
    number_of_people = models.IntegerField()
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    payment_intent_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_RESERVATION, default=UNPAID)
    first_name_on_reservation = models.CharField(max_length=100)
    last_name_on_reservation = models.CharField(max_length=100)
    phone_on_reservation = models.CharField(max_length=20)
    email_on_reservation = models.EmailField()
    coupon_used = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str({f"{self.user} - {self.room}"})


class Discount(models.Model):
    """
    Model that represents the discount.
    """
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    discount = models.DecimalField(max_digits=5, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    numbers_of_nights = models.IntegerField()
    rooms = models.ManyToManyField(Room, related_name='discounts')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.code)


class GoogleOAuthCredentials(models.Model):
    """
    Model that represents the Google OAuth credential.
    """
    token = models.TextField()
    refresh_token = models.TextField()
    token_uri = models.TextField()
    client_id = models.TextField()
    client_secret = models.TextField()
    scopes = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.token)
