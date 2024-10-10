"""
This file contains all the functions and decorators used in the accounts app.
"""
import logging
import xml.etree.ElementTree as ET
import json
from datetime import timedelta, datetime
from urllib.parse import urlparse

import django.contrib.auth
from functools import wraps
import requests
from decouple import config
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.mail import send_mail
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.template.loader import get_template
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.html import strip_tags
from redis import Redis
from requests import RequestException
from rest_framework import status
from rest_framework.response import Response
from rq import Queue
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from allauth.account.models import EmailAddress
from twilio.rest import Client

from accounts.constants import COMPLETE, ADMIN, PAID, UNPAID, CANCELED
from accounts.models import (Reservation, Discount, GoogleOAuthCredentials,
                             UserAlloggiatiWeb, TokenInfoAlloggiatiWeb,
                             DmsPugliaXml, Structure)
from accounts.serializers import ReservationSerializer
from config.settings.base import (TWILIO_AUTH_TOKEN, TWILIO_ACCOUNT_SID,
                                  ALLOGGIATI_WEB_URL, TWILIO_NUMBER, REDIS_BACKEND, OWNER_PHONE_NUMBER)

User = django.contrib.auth.get_user_model()
EMAIL = config('EMAIL_HOST_USER', '')
CACHE_KEY = 'google_calendar_credentials'
CACHE_TIMEOUT = 3600  # 1 hour cache timeout
logger = logging.getLogger(__name__)


#####################################################################################
# DECORATORS #
#####################################################################################

def is_active(view_func):
    """
    Decorator to check if the user is active, authenticated, and has a verified email.
    """

    @wraps(view_func)
    def decorator(request, *args, **kwargs):
        user = request.user

        # Check if the user is authenticated and active
        if not user.is_authenticated or not user.is_active:
            return Response({"Error": "Your account is not active or authenticated."},
                            status=status.HTTP_403_FORBIDDEN)

        # Check if the email is verified
        if not EmailAddress.objects.filter(user=user, verified=True).exists():
            return Response({"Error": "Your email is not verified."},
                            status=status.HTTP_403_FORBIDDEN)

        # Check if the user's data completion status is COMPLETE
        if user.status != COMPLETE:
            return Response({
                "Error": "You have to complete the data completion process",
                "userStatus": user.status
            }, status=status.HTTP_403_FORBIDDEN)

        # If all checks pass, proceed to the view
        return view_func(request, *args, **kwargs)

    return decorator


def is_admin(view_func):
    """
    Decorator to check if user has the status type of ADMIN
    """

    @wraps(view_func)
    def decorator(request, *args, **kwargs):
        user = request.user
        if user.type == ADMIN:
            return view_func(request, *args, **kwargs)
        return Response({"Error": "Your account is not an admin account"},
                        status=status.HTTP_403_FORBIDDEN)

    return decorator


#####################################################################################
# FUNCTIONS #
#####################################################################################


def send_account_deletion_email(user):
    """
    Send an account deletion confirmation email to the user.
    """
    try:
        context = {
            'user': user,
            'current_year': timezone.now().year,
        }
        subject = 'Conferma di cancellazione del tuo account'
        html_message = get_template('account/email/confirm_account_delete.html').render(context)
        plain_message = strip_tags(html_message)
        from_email = EMAIL  # Replace with your actual 'from' email address or settings.EMAIL_HOST_USER
        to_email = user.email

        send_mail(subject, plain_message, from_email, [to_email], html_message=html_message)
    except Exception as e:
        print(f"Failed to send account deletion email: {str(e)}")


def get_redis_connection_and_queue():
    """
    Parses the REDIS_BACKEND URL and returns a Redis connection and RQ queue.
    """
    redis_url = urlparse(REDIS_BACKEND)

    redis_conn = Redis(
        host=redis_url.hostname,
        port=redis_url.port,
        db=int(redis_url.path.lstrip('/')),
        password=redis_url.password
    )
    queue = Queue(connection=redis_conn)
    return redis_conn, queue


class WhatsAppService:
    def __init__(self):
        self.client = Client(
            TWILIO_ACCOUNT_SID,
            TWILIO_AUTH_TOKEN
        )
        self.from_whatsapp_number = TWILIO_NUMBER
        self.messaging_service_sid = 'MG7bc471ed29f87a3fce5bc75c0da53aab'

    def send_template_message(self, to_number, template_sid, template_parameters):
        """
        Send a WhatsApp message using a Twilio-approved template.

        Args:
            to_number (str): The recipient's phone number in E.164 format.
            template_sid (str): The SID of the Twilio-approved template.
            template_parameters (list): Parameters to replace in the template.

        Returns:
            str: The SID of the sent message or None if failed.
        """
        try:
            # Send the WhatsApp message using the Messaging Service SID
            msg = self.client.messages.create(
                messaging_service_sid=self.messaging_service_sid,
                to=f'whatsapp:{to_number}',
                content_sid=template_sid,
                content_variables=json.dumps(template_parameters)
            )
            return msg.sid
        except Exception as e:
            print(f"Failed to send WhatsApp template message: {str(e)}")
            return None

    def queue_message(self, to_number, messaging_service_sid, template_parameters):
        """
        Queue a WhatsApp message to be sent later via Redis.

        Args:
            to_number (str): The recipient's phone number in E.164 format.
            messaging_service_sid (str): The Messaging Service SID for the message.
            template_parameters (list): Parameters to replace in the template.

        Returns:
            str: The job ID of the queued task.
        """
        try:
            # Get the Redis connection and queue
            _, queue = get_redis_connection_and_queue()

            # Enqueue the send_message function with its arguments
            job = queue.enqueue(self.send_template_message, to_number, messaging_service_sid, template_parameters)
            return job.id
        except Exception as e:
            print(f"Failed to queue WhatsApp message: {str(e)}")
            return None


def send_confirmation_checkout_session_completed(reservation):
    try:
        whatsapp_service = WhatsAppService()

        guest_template_parameters = {
            "1": reservation.user.first_name,
            "2": str(reservation.id),
            "3": reservation.first_name_on_reservation,
            "4": reservation.last_name_on_reservation,
            "5": reservation.email_on_reservation,
            "6": reservation.phone_on_reservation,
            "7": reservation.room.structure.name,
            "8": reservation.room.name,
            "9": reservation.check_in.strftime('%d-%m-%Y'),
            "10": reservation.check_out.strftime('%d-%m-%Y')
        }

        owner_template_parameters = {
            "1": reservation.first_name_on_reservation,
            "2": reservation.last_name_on_reservation,
            "3": reservation.email_on_reservation,
            "4": reservation.phone_on_reservation,
            "5": reservation.room.structure.name,
            "6": reservation.room.name,
            "7": reservation.check_in.strftime('%d-%m-%Y'),
            "8": reservation.check_out.strftime('%d-%m-%Y')
        }

        guest_template_sid = "HX658f51746eeb9ef8f4ca40c9c5c92b4c"
        owner_template_sid = "HX9da8137893a6ff24066314f6be63317b"

        # Queue the message for the guest
        guest_job_id = whatsapp_service.queue_message(
            reservation.phone_on_reservation,
            guest_template_sid,
            guest_template_parameters
        )

        # Queue the message for the owner
        owner_job_id = whatsapp_service.queue_message(
            OWNER_PHONE_NUMBER,
            owner_template_sid,
            owner_template_parameters
        )

        if guest_job_id and owner_job_id:
            logger.info(f"WhatsApp messages queued successfully with job IDs: {guest_job_id}, {owner_job_id}")
            return guest_job_id, owner_job_id
        else:
            logger.error("Failed to queue WhatsApp messages.")
            return None

    except Exception as e:
        logger.error(f"Failed to send WhatsApp confirmation message: {str(e)}")
        return None


def send_cancel_reservation_whatsapp_message(reservation):
    try:
        whatsapp_service = WhatsAppService()

        template_parameters = {
            "1": reservation.user.first_name,
            "2": str(reservation.id),
            "3": reservation.first_name_on_reservation,
            "4": reservation.last_name_on_reservation,
            "5": reservation.email_on_reservation,
            "6": reservation.phone_on_reservation,
            "7": reservation.room.structure.name,
            "8": reservation.room.name,
            "9": reservation.check_in.strftime('%d-%m-%Y'),
            "10": reservation.check_out.strftime('%d-%m-%Y')
        }

        guest_template_sid = "HXde2f58fdc731d09fe91bc84ddfb3560b"
        owner_template_sid = "HX7da22de22b2f46c8b94a552eaefa0cd5"

        guest_job_id = whatsapp_service.queue_message(
            reservation.phone_on_reservation,
            guest_template_sid,
            template_parameters
        )

        owner_job_id = whatsapp_service.queue_message(
            OWNER_PHONE_NUMBER,
            owner_template_sid,
            template_parameters
        )

        if guest_job_id and owner_job_id:
            logger.info(
                f"WhatsApp cancellation messages queued successfully with job IDs: {guest_job_id}, {owner_job_id}")
            return guest_job_id, owner_job_id
        else:
            logger.error("Failed to queue WhatsApp cancellation messages.")
            return None

    except Exception as e:
        logger.error(f"Failed to send WhatsApp cancellation message: {str(e)}")
        return None


def handle_checkout_session_completed(session):
    """
    Manage the checkout session completed event.
    """
    try:
        # Retrieve the session ID
        session_id = session['id']

        # Find the reservation by payment intent ID
        reservation = get_object_or_404(Reservation, payment_intent_id=session_id)

        # Update the payment intent ID
        reservation.payment_intent_id = session['payment_intent']

        # Add the reservation to Google Calendar
        service = get_google_calendar_service()
        add_reservation_to_google_calendars(service, reservation)

        # Update the reservation status to PAID
        reservation.status = PAID
        reservation.save()

        # Send a payment confirmation email
        send_payment_confirmation_email(reservation)

        # Send a self-checkin email
        send_confirmation_checkout_session_completed(reservation)

        return Response({'status': 'success'}, status=status.HTTP_200_OK)

    except Reservation.DoesNotExist:
        logger.error("Reservation not found")
        return Response({"error": "Reservation not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error in handle_checkout_session_completed: {str(e)}")
        return Response({'status': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def send_payment_confirmation_email(reservation):
    """
    Send a payment confirmation email to the user.
    """
    try:
        serializer = ReservationSerializer(reservation)
        reservation_data = serializer.data

        context = {
            'reservation': reservation_data,
            'current_year': timezone.now().year,
        }

        subject = 'Conferma di pagamento per la tua prenotazione'
        html_message = get_template('account/stripe/payment_confirmation_email.html').render(context)
        plain_message = strip_tags(html_message)
        from_email = EMAIL
        to_email = reservation.email_on_reservation

        send_mail(subject, plain_message, from_email, [to_email], html_message=html_message)
        logger.info(f"Payment confirmation email sent to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send payment confirmation email: {str(e)}")


def send_self_checkin_mail(reservation):
    """
    Send a self-checkin reminder email to the user.
    """
    try:
        serializer = ReservationSerializer(reservation)
        reservation_data = serializer.data

        context = {
            'reservation': reservation_data,
            'current_year': timezone.now().year,
        }

        subject = 'Ricorda di fare il check-in!'
        html_message = get_template('account/email/email_self_checkin.html').render(context)
        plain_message = strip_tags(html_message)
        from_email = EMAIL
        to_email = reservation.email_on_reservation

        send_mail(subject, plain_message, from_email, [to_email], html_message=html_message)
        logger.info(f"Self check-in email sent to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send self check-in email: {str(e)}")


def send_cancel_reservation_email(reservation):
    """
    Send a cancellation confirmation email to the user.
    """
    try:
        serializer = ReservationSerializer(reservation)
        reservation_data = serializer.data

        context = {
            'reservation': reservation_data,
            'current_year': timezone.now().year,
        }
        subject = 'Conferma di cancellazione della tua prenotazione'
        html_message = get_template('account/stripe/cancel_reservation_email.html').render(context)
        plain_message = strip_tags(html_message)
        from_email = EMAIL
        to_email = reservation.email_on_reservation

        send_mail(subject, plain_message, from_email, [to_email], html_message=html_message)
        logger.info(f"Cancellation email sent to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send cancellation email: {str(e)}")


def send_self_checkin_whatsapp_message(reservation):
    try:
        whatsapp_service = WhatsAppService()

        # Prepare template parameters for guest
        guest_template_parameters = {
            "1": reservation.user.first_name,
            "2": str(reservation.id),
            "3": reservation.first_name_on_reservation,
            "4": reservation.last_name_on_reservation,
            "5": reservation.email_on_reservation,
            "6": reservation.phone_on_reservation,
            "7": reservation.room.structure.name,
            "8": reservation.room.name,
            "9": reservation.check_in.strftime('%d-%m-%Y'),
            "10": reservation.check_out.strftime('%d-%m-%Y')
        }

        # Prepare template parameters for the owner
        owner_template_parameters = {
            "1": reservation.first_name_on_reservation,
            "2": reservation.last_name_on_reservation,
            "3": reservation.email_on_reservation,
            "4": reservation.phone_on_reservation,
            "5": reservation.room.structure.name,
            "6": reservation.room.name,
            "7": reservation.check_in.strftime('%d-%m-%Y'),
            "8": reservation.check_out.strftime('%d-%m-%Y')
        }

        # Define the Messaging Service SIDs
        # guest_template_sid = "send_self_checkin_guest"
        # owner_template_sid = "send_self_checkin_owner"

        guest_template_sid = "HX454bd1992ce34b4075823847b865075d"
        owner_template_sid = "HX454bd1992ce34b4075823847b865075d"

        # Queue the message for the guest
        guest_job_id = whatsapp_service.queue_message(
            reservation.phone_on_reservation,
            guest_template_sid,
            guest_template_parameters
        )

        # Queue the message for the owner
        owner_job_id = whatsapp_service.queue_message(
            OWNER_PHONE_NUMBER,
            owner_template_sid,
            owner_template_parameters
        )

        if guest_job_id and owner_job_id:
            print(f"WhatsApp message queued successfully with job ID: {guest_job_id}")
            return guest_job_id, owner_job_id
        else:
            print("Failed to queue the WhatsApp message.")
            return None

    except Exception as e:
        print(f"Failed to send WhatsApp confirmation message: {str(e)}")
        return None


def cancel_reservation_and_remove_event(reservation):
    """
    Cancel a reservation and remove the event from Google Calendar.
    """
    try:
        service = get_google_calendar_service()

        if reservation.event_id:
            # Try to delete the event from the calendar associated with the reservation of django db
            service.events().delete(calendarId=reservation.room.calendar_id, eventId=reservation.event_id).execute()
            logger.info(f"Event {reservation.event_id} deleted from calendar {reservation.room.calendar_id}")

            # Update the reservation status to CANCELED
            reservation.status = CANCELED
            reservation.save()

            # Send a cancellation confirmation email
            send_cancel_reservation_email(reservation)
            send_cancel_reservation_whatsapp_message(reservation)
        else:
            logger.error("No event_id found for this reservation.")
            raise Exception("No event_id found for this reservation.")
    except GoogleOAuthCredentials.DoesNotExist:
        logger.error('Google Calendar credentials not found.')
        raise Exception('Google Calendar credentials not found.')
    except Exception as e:
        logger.error(f"Failed to remove event from Google Calendar: {str(e)}")
        raise Exception(f"Failed to remove event from Google Calendar: {str(e)}")


def calculate_total_cost(reservation):
    """
    Calculate the total cost for a reservation
    """
    # Calculate the number of nights
    number_of_nights = (reservation.check_out - reservation.check_in).days

    # Calculate the total cost
    total_cost = number_of_nights * reservation.room.cost_per_night

    # Update the total cost in the reservation
    reservation.total_cost = total_cost
    reservation.save()

    logger.debug(f"Total cost calculated for reservation {reservation.id}: {total_cost}")
    return total_cost


def calculate_discount(reservation):
    """
    Calculate the discount for a reservation
    """
    try:
        # Retrieve the discount object
        discount = Discount.objects.get(code=reservation.coupon_used)

        # Verify if the reservation dates are within the discount period
        if reservation.check_in >= discount.start_date and reservation.check_out <= discount.end_date:
            # Calculate the number of nights
            number_of_nights = (reservation.check_out - reservation.check_in).days

            # Verify if the reservation meets the minimum number of nights for the discount
            if number_of_nights >= discount.numbers_of_nights:
                # Calculate the total discount amount
                discount_amount = reservation.total_cost * (discount.discount / 100)
                # Apply the discount to the reservation
                reservation.total_cost -= discount_amount
                reservation.save()
                logger.info(f"Discount applied to reservation {reservation.id}: {discount_amount}")
                return discount_amount

        return None
    except Discount.DoesNotExist:
        logger.warning(f"No discount found for code {reservation.coupon_used}")
        return None


#####################################################################################
## GETTING GOOGLE CALENDAR SERVICE ## START
#####################################################################################

def get_cached_credentials():
    """
    Retrieve the cached Google Calendar credentials.
    """
    cached_credentials = cache.get(CACHE_KEY)
    if cached_credentials:
        logger.debug("Using cached credentials.")
        credentials_data = json.loads(cached_credentials)
        return Credentials(
            token=credentials_data['token'],
            refresh_token=credentials_data.get('refresh_token'),
            token_uri=credentials_data['token_uri'],
            client_id=credentials_data['client_id'],
            client_secret=credentials_data['client_secret'],
            scopes=credentials_data['scopes']
        )
    logger.debug("No cached credentials found.")
    return None


def get_credentials_from_db():
    """
    Retrieve the Google Calendar credentials from the database.
    """
    try:
        creds = GoogleOAuthCredentials.objects.get(id=1)
        logger.debug("Credentials retrieved from database.")
        return Credentials(
            token=creds.token,
            refresh_token=creds.refresh_token,
            token_uri=creds.token_uri,
            client_id=creds.client_id,
            client_secret=creds.client_secret,
            scopes=creds.scopes.split()
        )
    except GoogleOAuthCredentials.DoesNotExist:
        logger.error("Google Calendar credentials not found in the database.")
        raise Exception("Google Calendar credentials not found in the database.")


def cache_credentials(credentials):
    """
    Cache the Google Calendar credentials.
    """
    credentials_data = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    cache.set(CACHE_KEY, json.dumps(credentials_data), CACHE_TIMEOUT)
    logger.debug("Credentials cached successfully.")


def update_db_token(token):
    """
    Update the token in the database.
    """
    GoogleOAuthCredentials.objects.filter(id=1).update(token=token)
    logger.debug("Database updated with new token.")


def refresh_credentials(credentials):
    """
    Run the refresh token flow to obtain a new access token.
    """
    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            logger.info("Access token refreshed successfully.")
            # Cache and update the new token
            cache_credentials(credentials)
            update_db_token(credentials.token)
        except Exception as e:
            logger.error(f"Error while refreshing token: {e}")
            if "invalid_grant" in str(e):
                raise Exception("Refresh token expired or revoked. Reauthentication required.")
            raise Exception(f"Error during token refresh: {str(e)}")


def get_google_calendar_service():
    """
    Build and return the Google Calendar service.
    """
    try:
        # Retrieve the cached or database credentials
        credentials = get_cached_credentials() or get_credentials_from_db()

        # Run the refresh token flow if the credentials are expired
        if credentials.expired:
            logger.debug("Credentials expired. Attempting refresh.")
            refresh_credentials(credentials)

        # Build and return the Google Calendar service
        logger.debug("Building Google Calendar service...")
        service = build('calendar', 'v3', credentials=credentials)
        logger.info("Google Calendar service built successfully.")
        return service

    except Exception as e:
        logger.error(f"Error while setting up Google Calendar service: {e}")
        raise Exception(f"Error setting up Google Calendar service: {str(e)}")


#####################################################################################
## GETTING GOOGLE CALENDAR SERVICE ## END
#####################################################################################

def add_reservation_to_google_calendars(service, reservation):
    try:
        event = {
            'summary': f"Reservation for {reservation.first_name_on_reservation} {reservation.last_name_on_reservation}",
            'description': (
                f"Email: {reservation.email_on_reservation}\n"
                f"Phone: {reservation.phone_on_reservation}\n"
                f"Total Cost: {reservation.total_cost}\n"
                f"Number of People: {reservation.number_of_people}\n"
                f"Room: {reservation.room.name}, {reservation.room.structure}"
            ),
            'start': {
                'date': reservation.check_in.strftime('%Y-%m-%d'),
                'timeZone': 'UTC',
            },
            'end': {
                'date': reservation.check_out.strftime('%Y-%m-%d'),
                'timeZone': 'UTC',
            },
            'location': reservation.room.structure.address,
            'attendees': [
                {'email': reservation.email_on_reservation},
            ],
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 10},
                ],
            },
        }

        # Add the event to the calendar associated with django
        created_event = service.events().insert(calendarId=reservation.room.calendar_id, body=event).execute()
        logger.info(f"Event created in calendar {reservation.room.calendar_id} with ID {created_event.get('id')}")

        # Memorize the event ID in the reservation
        reservation.event_id = created_event.get('id')
        reservation.save()

        return created_event
    except Exception as e:
        logger.error(f"Failed to add reservation to Google Calendars: {str(e)}")
        raise Exception(f"Failed to add reservation to Google Calendars: {str(e)}")


def get_busy_dates_from_reservations(room, check_in, check_out):
    busy_dates = set()
    current_time = timezone.now()

    # Filter reservations that overlap with the selected dates and are not UNPAID and older than 10 minutes
    local_reservations = Reservation.objects.filter(
        room=room,
        check_out__gte=check_in,
        check_in__lte=check_out
    ).exclude(
        Q(status=UNPAID) & Q(created_at__lt=(current_time - timedelta(minutes=10)))
    )

    # Collect the busy dates from the reservations
    for reservation in local_reservations:
        current_date = reservation.check_in
        while current_date < reservation.check_out:
            busy_dates.add(current_date.strftime('%Y-%m-%d'))
            current_date += timedelta(days=1)

    logger.debug(f"Busy dates from reservations for room {room.name}: {busy_dates}")
    return busy_dates


def get_busy_dates_from_calendars(service, room, check_in, check_out):
    """
    Get busy dates from both Google Calendars associated with the room.
    """
    busy_dates = set()
    calendar_ids = [room.calendar_id, room.calendar_id_booking]

    for calendar_id in filter(None, calendar_ids):
        try:
            logger.debug(f"Fetching events from calendar {calendar_id}")
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=check_in.isoformat() + 'Z',
                timeMax=check_out.isoformat() + 'Z',
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
            logger.debug(f"Number of events fetched from calendar {calendar_id}: {len(events)}")

            for event in events:
                logger.debug(f"Processing event ID: {event.get('id')}, Summary: {event.get('summary')}")

                # Handle events with 'date' (all-day events) and 'dateTime' (events with specific times)
                start = event['start'].get('date') or event['start'].get('dateTime')
                end = event['end'].get('date') or event['end'].get('dateTime')

                if not start or not end:
                    logger.warning(f"Event {event.get('id')} has missing start or end time.")
                    continue

                # Parse the start and end dates
                start_date = parse_event_date(start)
                end_date = parse_event_date(end)

                if not start_date or not end_date:
                    logger.warning(f"Skipping event {event.get('id')} due to date parsing error.")
                    continue

                # For all-day events, the end date is exclusive
                if 'date' in event['start']:
                    # Adjust end_date to include the last day
                    end_date -= timedelta(days=1)

                current_date = start_date
                while current_date <= end_date:
                    busy_dates.add(current_date.strftime('%Y-%m-%d'))
                    current_date += timedelta(days=1)

            logger.debug(f"Busy dates from calendar {calendar_id} for room {room.name}: {busy_dates}")
        except Exception as e:
            logger.error(f"Error fetching events from calendar {calendar_id}: {str(e)}")
            raise Exception(f"Error fetching events from calendar {calendar_id}: {str(e)}")

    return busy_dates


def parse_event_date(date_str):
    """
    Parse event date string to datetime.date object.
    """
    try:
        if 'T' in date_str:
            # DateTime format
            return datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
        else:
            # Date format (all-day events)
            return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError as e:
        logger.error(f"Error parsing date string '{date_str}': {str(e)}")
        return None


def get_combined_busy_dates(room, check_in, check_out):
    """
    Obtain the combined busy dates from the reservations and Google Calendar.
    """
    try:
        # Obtain the busy dates from the reservations
        busy_dates = get_busy_dates_from_reservations(room, check_in, check_out)

        # Obtain the busy dates from the Google Calendar
        service = get_google_calendar_service()
        if service:
            busy_dates_calendar = get_busy_dates_from_calendars(service, room, check_in, check_out)
            busy_dates.update(busy_dates_calendar)

        logger.debug(f"Combined busy dates for room {room.name}: {busy_dates}")
        return busy_dates
    except Exception as e:
        logger.error(f"Error in get_combined_busy_dates: {str(e)}")
        raise Exception(f"Error in get_combined_busy_dates: {str(e)}")


def is_room_available(busy_dates, check_in, check_out):
    """
    Check if a room is available given a set of busy dates.
    """
    check_in_date = check_in.date()
    check_out_date = check_out.date() - timedelta(days=1)  # Exclude the check-out date
    current_date = check_in_date
    while current_date <= check_out_date:
        date_str = current_date.strftime('%Y-%m-%d')
        if date_str in busy_dates:
            logger.debug(f"Room not available on {date_str}")
            return False
        current_date += timedelta(days=1)
    logger.debug("Room is available for the selected dates.")
    return True


### Utility Functions ###

def build_soap_envelope(action, body_content):
    """
    Make a SOAP request to the Alloggiati Web service.
    """
    envelope = ET.Element('{http://www.w3.org/2003/05/soap-envelope}Envelope', attrib={
        'xmlns:soap': 'http://www.w3.org/2003/05/soap-envelope',
        'xmlns:all': 'AlloggiatiService'
    })
    ET.SubElement(envelope, '{http://www.w3.org/2003/05/soap-envelope}Header')
    body = ET.SubElement(envelope, '{http://www.w3.org/2003/05/soap-envelope}Body')
    action_element = ET.SubElement(body, f'{action}')

    for key, value in body_content.items():
        if isinstance(value, tuple):
            sub_element = ET.SubElement(action_element, value[0])
            sub_element.text = value[1]
        else:
            # Add the value directly to the action element
            action_element.append(value)

    return ET.tostring(envelope, encoding='utf-8', method='xml')


def send_soap_request(xml_request):
    """
    Send a SOAP request to the Alloggiati Web service.
    """
    headers = {'Content-Type': 'text/xml; charset=utf-8'}
    try:
        response = requests.post(ALLOGGIATI_WEB_URL, data=xml_request, headers=headers, timeout=10)
        response.raise_for_status()
        logger.debug("SOAP request sent successfully.")
        return response.content
    except RequestException as e:
        logger.error(f"Failed to connect to SOAP service: {str(e)}")
        raise ConnectionError(f"Failed to connect to SOAP service: {str(e)}")


def parse_soap_response(xml_response, action_namespace, expected_fields):
    """
    Analize the SOAP response from the Alloggiati Web service.
    """
    namespaces = {
        'soap': 'http://www.w3.org/2003/05/soap-envelope',
        'all': 'AlloggiatiService'
    }

    root = ET.fromstring(xml_response)

    # Find the esito element
    esito_element = root.find(f'.//{action_namespace}:esito', namespaces)

    # If esito is not True, raise a ValidationError
    if esito_element is None or esito_element.text.strip().lower() != 'true':
        error_details = {}
        for field in expected_fields:
            element = root.find(f'.//{action_namespace}:{field}', namespaces)
            if element is not None and element.text:
                error_details[field] = element.text.strip()
            else:
                error_details[field] = "Missing or empty field"

        logger.error(f"SOAP Error: {error_details}")
        raise ValidationError("SOAP Error", error_details)

    # Collect the expected fields from the response
    result = {}
    for field in expected_fields:
        element = root.find(f'.//{action_namespace}:{field}', namespaces)
        result[field] = element.text.strip() if element is not None and element.text else None

    logger.debug(f"SOAP response parsed successfully: {result}")
    return result


def get_or_create_token(structure_id):
    """
    Retrieve a valid token from the database or generate a new one.
    """
    token_info = TokenInfoAlloggiatiWeb.objects.filter(expires__gt=timezone.now()).first()

    if token_info:
        logger.debug("Valid token found.")
        return token_info

    logger.debug("No valid token found. Generating a new one.")
    return generate_and_send_token_alloggiati_web_request(structure_id)


def generate_and_send_token_alloggiati_web_request(structure_id):
    """
    Make and send a request to the Alloggiati Web service to generate a new token.
    """
    try:
        user_info = UserAlloggiatiWeb.objects.get(structure__id=structure_id)
        body_content = {
            'Utente': ('{AlloggiatiService}Utente', user_info.alloggiati_web_user),
            'Password': ('{AlloggiatiService}Password', user_info.alloggiati_web_password),
            'WsKey': ('{AlloggiatiService}WsKey', user_info.wskey),
        }

        xml_request = build_soap_envelope('{AlloggiatiService}GenerateToken', body_content)
        response_content = send_soap_request(xml_request)

        # Analize the SOAP response and extract the token data
        token_data = parse_soap_response(
            response_content,
            'all',
            ['issued', 'expires', 'token']
        )

        # Build and return the TokenInfoAlloggiatiWeb object
        token_info = TokenInfoAlloggiatiWeb.objects.create(
            issued=datetime.fromisoformat(token_data['issued']),
            expires=datetime.fromisoformat(token_data['expires']),
            token=token_data['token'],
        )
        logger.info("New token generated and saved.")
        return token_info

    except UserAlloggiatiWeb.DoesNotExist:
        logger.error(f"User information for structure_id {structure_id} not found.")
        raise ValidationError(f"User information for structure_id {structure_id} not found.")
    except Exception as e:
        logger.error(f"An error occurred while generating the token: {str(e)}")
        raise Exception(f"An error occurred while generating the token: {str(e)}")


def validate_elenco_schedine(structure_id, elenco_schedine):
    """
    Validate the list of schedine for a structure.
    """
    try:
        user_info = UserAlloggiatiWeb.objects.get(structure__id=structure_id)
        token_info = get_or_create_token(structure_id)

        elenco_subelement = ET.Element('{AlloggiatiService}ElencoSchedine')
        for schedina in elenco_schedine:
            schedina_element = ET.SubElement(elenco_subelement, '{AlloggiatiService}string')
            schedina_element.text = schedina

        body_content = {
            'Utente': ('{AlloggiatiService}Utente', user_info.alloggiati_web_user),
            'token': ('{AlloggiatiService}token', token_info.token),
            'ElencoSchedine': elenco_subelement,
        }

        xml_request = build_soap_envelope('{AlloggiatiService}Send', body_content)
        response_content = send_soap_request(xml_request)

        result = parse_soap_response(
            response_content,
            'all',
            ['Esito', 'ErroreCod', 'ErroreDes', 'ErroreDettaglio']
        )
        logger.info(f"Elenco Schedine validation result: {result}")
        return result

    except (ObjectDoesNotExist, ValidationError, ConnectionError) as e:
        logger.error(f"Error in validate_elenco_schedine: {str(e)}")
        return {"error": str(e), "status": "failed"}
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        return {"error": f"An unexpected error occurred: {str(e)}", "status": "failed"}


#####################################################################################
# DMS Puglia XML Generation START #
#####################################################################################


def generate_dms_puglia_xml(data, vendor):
    """
    Generate or update a DMS Puglia XML file.
    """
    try:
        movimento_data = data['data'].strftime('%Y-%m-%d')
        structure_id = data.get('structure_id')

        if not structure_id:
            raise ValueError("Missing 'structure_id' in the data.")

        logger.debug(f"Structure ID: {structure_id}, Movimento Data: {movimento_data}")

        # Check for existing XML file for the same date and structure
        existing_dms_instance = DmsPugliaXml.objects.filter(
            structure_id=structure_id,
            xml__contains=f'data="{movimento_data}"'
        ).first()

        if existing_dms_instance:
            return update_existing_xml(existing_dms_instance, data, movimento_data)

        return create_new_xml(data, movimento_data, vendor)

    except Exception as e:
        logger.error(f"Error generating XML: {e}")
        raise


def append_element_with_text(parent_el, tag, text):
    """
    Helper function to create a new XML element with text.
    """
    el = ET.SubElement(parent_el, tag)
    el.text = str(text) if text else ""
    return el


def append_componenti_to_arrivo(arrivo_el, componenti):
    """
    Append componenti to the <arrivo> element.
    """
    componenti_el = ET.SubElement(arrivo_el, "componenti")
    for componente in componenti:
        componente_el = ET.SubElement(componenti_el, "componente")
        for key in ['codice_cliente_sr', 'sesso', 'cittadinanza', 'paese_residenza', 'comune_residenza',
                    'occupazione_posto_letto', 'eta']:
            append_element_with_text(componente_el, key, componente.get(key, " "))


def append_arrivi_to_movimento(movimento_el, arrivi):
    arrivi_el = ET.SubElement(movimento_el, "arrivi")
    for arrivo in arrivi:
        arrivo_el = ET.SubElement(arrivi_el, "arrivo")
        for key in ['codice_cliente_sr', 'sesso', 'cittadinanza', 'paese_residenza',
                    'comune_residenza', 'occupazione_postoletto', 'dayuse', 'tipologia_alloggiato', 'eta',
                    'durata_soggiorno']:
            append_element_with_text(arrivo_el, key, arrivo.get(key, " "))

        # Handle capo gruppo or capo famiglia (tipologia_alloggiato = 17 or 18)
        if arrivo.get('tipologia_alloggiato') in ['17', '18']:
            componenti = arrivo.get('componenti', [])
            append_componenti_to_arrivo(arrivo_el, componenti)


def update_existing_xml(existing_dms_instance, data, movimento_data):
    """
    Update an existing XML file in the DB for the given structure and date.
    """
    try:
        logger.debug("Updating existing XML")
        # Read and parse the existing XML content
        existing_xml_content = existing_dms_instance.xml.read().decode('utf-8')

        tree = ET.ElementTree(ET.fromstring(existing_xml_content))
        root = tree.getroot()

        # Find or create the movimento element
        movimento_el = find_or_create_movimento(root, data, movimento_data)

        # Add arrivi data
        append_arrivi_to_movimento(movimento_el, data['arrivi'])

        # Save updated XML content back to the database
        updated_xml_content = ET.tostring(root, encoding="utf-8", method="xml").decode("utf-8")
        save_xml_to_db(existing_dms_instance, updated_xml_content, movimento_data)

        return updated_xml_content

    except Exception as e:
        logger.error(f"Error processing or saving existing XML: {e}")
        raise


def create_new_xml(data, movimento_data, vendor):
    """
    Create a new XML file in the DB for the given structure and date.
    """
    try:
        logger.debug("Creating new XML")
        # Create the root element for the new XML
        root = ET.Element("movimenti", attrib={
            'xmlns:xsi': "http://www.w3.org/2001/XMLSchema-instance",
            'xsi:noNamespaceSchemaLocation': "movimentogiornaliero-0.6.xsd",
            'vendor': vendor
        })

        # Create a new movimento element and add arrivi
        movimento_el = ET.SubElement(root, "movimento", attrib={
            'type': data['type'],
            'data': movimento_data
        })
        append_arrivi_to_movimento(movimento_el, data['arrivi'])

        # Save new XML content to the database
        new_xml_content = ET.tostring(root, encoding="utf-8", method="xml")

        if new_xml_content is None:
            raise ValueError("Failed to generate XML content")

        new_xml_content = new_xml_content.decode("utf-8")
        logger.debug(f"New XML Content (decoded): {new_xml_content}")

        structure_id = data.get('structure_id')
        if not structure_id:
            raise ValueError("Missing 'structure_id' in the data.")

        # Retrieve the structure object
        structure = Structure.objects.get(id=structure_id)

        # Create the DmsPugliaXml instance with the structure
        dms_instance = DmsPugliaXml(structure=structure)
        save_xml_to_db(dms_instance, new_xml_content, movimento_data)

        return new_xml_content

    except Structure.DoesNotExist:
        logger.error(f"Structure with this id does not exist.")
        raise ValueError(f"Structure with this id does not exist.")
    except Exception as e:
        logger.error(f"Error creating new XML: {e}")
        raise


def find_or_create_movimento(root, data, movimento_data):
    """
    Find or create the 'movimento' element in the XML.
    """
    movimento_el = root.find(f"./movimento[@data='{movimento_data}']")
    if movimento_el is not None:
        return movimento_el

    # if movimento element does not exist, create a new one
    return ET.SubElement(root, 'movimento', attrib={
        'type': data['type'],
        'data': movimento_data
    })


@transaction.atomic
def save_xml_to_db(dms_instance, xml_content, movimento_data):
    """
    Save the XML content to the database inside a transaction using default_storage.
    """
    if not dms_instance.structure_id:
        raise ValueError("Missing structure_id in DmsPugliaXml instance.")

    try:
        structure = dms_instance.structure
        relative_filename = f'dms_puglia_xml/{structure.name}_{movimento_data}.xml'
        logger.debug(f"Saving file: {relative_filename}")

        content_file = ContentFile(xml_content.encode('utf-8'))
        saved_path = default_storage.save(relative_filename, content_file)
        dms_instance.xml.name = saved_path

        dms_instance.save()
        logger.info(f"File saved successfully at: {saved_path}")

    except Exception as e:
        logger.error(f"Error saving XML to database: {e}")
        raise

#####################################################################################
# DMS Puglia XML Generation END #
#####################################################################################
