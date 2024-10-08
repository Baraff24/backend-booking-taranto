"""
This module contains the models for the accounts app.
"""
from datetime import date
import uuid

from django.db import models
from django.contrib.auth.models import AbstractUser

from .constants import (STATUS_CHOICES, PENDING_COMPLETE_DATA, TYPE_VALUES,
                        CUSTOMER, ROOM_STATUS, AVAILABLE, STATUS_RESERVATION, UNPAID, CATEGORY_CHOICES)


class User(AbstractUser):
    """
    Custom user model that extends the default Django user model.
    Fields:
    - username, password, email (inherited)
    - first_name: User's first name
    - last_name: User's last name
    - telephone: Unique phone number for the user
    - status: Indicates the status of the user's profile completion
    - type: Defines the type of the user (e.g., CUSTOMER, ADMIN)
    """
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    telephone = models.CharField(max_length=20, unique=True, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                              default=PENDING_COMPLETE_DATA)
    type = models.CharField(max_length=10, choices=TYPE_VALUES, default=CUSTOMER)
    has_accepted_terms = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.email}"


class Structure(models.Model):
    """
    Model representing a building or structure that contains rooms.
    Fields:
    - name: Name of the structure
    - description: A textual description of the structure
    - address: Physical address of the structure
    - cis: Unique identifier for the structure
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    address = models.CharField(max_length=200)
    cis = models.CharField(max_length=60, unique=True)

    def __str__(self):
        return str(self.name)


class StructureImage(models.Model):
    """
    Model representing an image of a structure.
    Fields:
    - structure: Foreign key to the Structure model
    - image: Image file for the structure
    - alt: Alternative text for the image (useful for SEO and accessibility)
    """
    structure = models.ForeignKey(Structure, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='structure_images/')
    alt = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"Image of {self.structure.name}"


class Room(models.Model):
    """
    Model representing a room within a structure.
    Fields:
    - structure: Foreign key to the Structure model
    - room_status: Status of the room (e.g., available, occupied)
    - name: Name or identifier for the room
    - services: Textual description of services provided in the room
    - cost_per_night: Cost per night to rent the room
    - max_people: Maximum occupancy of the room
    - calendar_id: Associated Google Calendar ID for the room
    - calendar_id_booking: Associated Google Calendar ID for the room of Booking.com
    """
    structure = models.ForeignKey(Structure, on_delete=models.CASCADE, related_name='rooms')
    room_status = models.CharField(max_length=20, choices=ROOM_STATUS, default=AVAILABLE)
    name = models.CharField(max_length=100)
    services = models.TextField(blank=True)
    cost_per_night = models.DecimalField(max_digits=10, decimal_places=2)
    max_people = models.PositiveIntegerField()
    calendar_id = models.CharField(max_length=255, blank=True, null=True)
    calendar_id_booking = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.name} in {self.structure.name}"


class RoomImage(models.Model):
    """
    Model representing an image of a room.
    Fields:
    - room: Foreign key to the Room model
    - image: Image file for the room
    - alt: Alternative text for the image
    """
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='room_images/')
    alt = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"Image of {self.room.name}"


class Reservation(models.Model):
    """
    Model representing a reservation for a room.
    Fields:
    - user: Foreign key to the User model
    - room: Foreign key to the Room model
    - reservation_id: Unique identifier for the reservation
    - event_id: Google Calendar event ID associated with the reservation
    - check_in: Check-in date
    - check_out: Check-out date
    - number_of_people: Number of people staying in the room
    - total_cost: Total cost of the reservation
    - payment_intent_id: Stripe payment intent ID associated with the reservation
    - status: Status of the reservation (e.g., unpaid, paid, canceled)
    - first_name_on_reservation: First name of the person on the reservation
    - last_name_on_reservation: Last name of the person on the reservation
    - phone_on_reservation: Phone number of the person on the reservation
    - email_on_reservation: Email of the person on the reservation
    - coupon_used: Coupon code used for the reservation, if any
    - created_at: Timestamp of when the reservation was created
    """
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='reservations'
    )
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='reservations')
    reservation_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    event_id = models.CharField(max_length=500, blank=True, null=True)
    check_in = models.DateField()
    check_out = models.DateField()
    number_of_people = models.PositiveIntegerField()
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
        return f"Reservation {self.reservation_id} by {self.user}"


class Discount(models.Model):
    """
    Model representing a discount code.
    Fields:
    - code: Unique discount code
    - description: Description of the discount
    - discount: Percentage or flat discount value
    - start_date: Start date of the discount's validity
    - end_date: End date of the discount's validity
    - numbers_of_nights: Minimum number of nights required to apply the discount
    - rooms: Many-to-many relationship with Room to specify which rooms the discount applies to
    - created_at: Timestamp of when the discount was created
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
    Model representing Google OAuth credentials.
    Fields:
    - token: Access token
    - refresh_token: Refresh token
    - token_uri: URI to refresh the token
    - client_id: Google API client ID
    - client_secret: Google API client secret
    - scopes: Space-separated list of OAuth scopes
    - created_at: Timestamp of when the credentials were created
    - updated_at: Timestamp of when the credentials were last updated
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
        return f"Google OAuth Credentials (Client ID: {self.client_id})"


class UserAlloggiatiWeb(models.Model):
    """
    Model representing the user for the Alloggiati Web app.
    Fields:
    - structure: Foreign key to the User model
    - alloggiati_web_user: Alloggiati web user assigned to the structure
    - alloggiati_web_password: Password for the Alloggiati Web app
    - wskey: Web service key for the Alloggiati Web app
    - created_at: Timestamp of when the user was created
    """
    structure = models.ForeignKey(Structure, on_delete=models.CASCADE, related_name='structure_alloggiati_web')
    alloggiati_web_user = models.CharField(max_length=100)
    alloggiati_web_password = models.CharField(max_length=100)
    wskey = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"User for Alloggiati Web: {self.structure}"


class TokenInfoAlloggiatiWeb(models.Model):
    """
    Model representing the token info for the Alloggiati Web app.
    Fields:
    - issued: Timestamp of when the token was issued
    - expires: Timestamp of when the token expires
    - token: Access token for the Alloggiati Web app
    - created_at: Timestamp of when the token was created
    """
    issued = models.DateTimeField()
    expires = models.DateTimeField()
    token = models.CharField(max_length=500)

    def __str__(self):
        return "Token Info for Alloggiati Web"


class CheckinCategoryChoices(models.Model):
    """
    Model representing the checkin category choices.
    Fields:
    - category: Category of the checkin
    - codice: Code for the checkin category choice
    - descrizione: Description of the checkin category choice
    """
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    codice = models.CharField(max_length=10, blank=True, null=True)
    descrizione = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.descrizione} ({self.codice}) - {self.category}"


class DmsPugliaXml(models.Model):
    """
    Model representing the DMS Puglia XML.
    Fields:
    - xml: XML file for the DMS Puglia
    - created_at: Timestamp of when the XML was created
    """
    structure = models.ForeignKey(Structure, on_delete=models.CASCADE, related_name='dms_puglia_xml')
    date = models.DateField(default=date.today, null=True, blank=True)
    xml = models.FileField(upload_to='dms_puglia_xml/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"DMS Puglia XML ({self.created_at})"
