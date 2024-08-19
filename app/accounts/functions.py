"""
This file contains all the functions and decorators used in the accounts app.
"""
import json
from datetime import timedelta, datetime
import django.contrib.auth
from functools import wraps
import stripe
from decouple import config
from django.core.mail import send_mail
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.html import strip_tags
from rest_framework import status
from rest_framework.response import Response
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from allauth.account.models import EmailAddress

from accounts.constants import COMPLETE, ADMIN, PAID, UNPAID
from accounts.models import Reservation, Discount, GoogleOAuthCredentials

User = django.contrib.auth.get_user_model()
EMAIL = config('EMAIL_HOST_USER', '')


#####################################################################################
# DECORATORS #
#####################################################################################

def is_active(view_func):
    """
    Decorator to check if user is active
    """

    @wraps(view_func)
    def decorator(request, *args, **kwargs):
        user = request.user
        if user.is_active and user.is_authenticated:
            if EmailAddress.objects.filter(user=user, verified=True):
                obj = User.objects.filter(email=user.email)
                if obj[0].status == COMPLETE:
                    return view_func(request, *args, **kwargs)
                return Response({
                    "Error": "You have to complete the data completion process",
                    "userStatus": obj[0].status
                },
                    status=status.HTTP_403_FORBIDDEN)
            return Response({"Error": "Your email is not verified"},
                            status=status.HTTP_403_FORBIDDEN)
        return Response({"Error": "Your account is not active"},
                        status=status.HTTP_403_FORBIDDEN)

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
def handle_checkout_session_completed(session):
    """
    Function to handle checkout session completed event from Stripe
    """
    try:
        # Retrieve the payment intent ID from the session
        session_id = session['id']

        # Find the corresponding reservation
        reservation = get_object_or_404(Reservation, payment_intent_id=session_id)

        print("Reservation found")

        # Update the payment intent ID in the reservation
        reservation.payment_intent_id = session['payment_intent']

        # Update the reservation status to PAID
        reservation.status = PAID
        reservation.save()

        # Optionally, send a confirmation email or update Google Calendar, etc.
        send_payment_confirmation_email(reservation)

        print("Payment completed successfully")
        return Response({'status': 'success'}, status=status.HTTP_200_OK)

    except Reservation.DoesNotExist:
        print("Reservation not found")
        return Response({"error": "Reservation not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(f"Error in handle_checkout_session_completed: {e}")
        return Response({'status': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# def handle_payment_intent_succeeded(payment_intent):
#     """
#     Function to handle the payment intent succeeded
#     """
#     try:
#         reservation = get_object_or_404(Reservation, payment_intent_id=payment_intent['id'])
#
#         reservation.payment_intent_id = payment_intent['payment_intent']
#
#         # Add the reservation to Google Calendar
#         service = get_google_calendar_service()
#         add_reservation_to_google_calendar(service, reservation)
#
#         # Update reservation status to PAID
#         reservation.status = PAID
#         reservation.save()
#
#         # Send payment confirmation email
#         send_payment_confirmation_email(reservation)
#
#         return Response({'status': 'success'}, status=status.HTTP_200_OK)
#
#     except Exception as e:
#         print(f"Error in handle_payment_intent_succeeded: {e}")
#         return Response({'status': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def send_payment_confirmation_email(reservation):
    """
    Send a payment confirmation email to the user
    """
    try:
        subject = 'Conferma di pagamento per la tua prenotazione'
        html_message = render_to_string('account/stripe/payment_confirmation_email.html',
                                        {'reservation': reservation})
        plain_message = strip_tags(html_message)
        from_email = EMAIL
        to_email = reservation.user.email

        send_mail(subject, plain_message, from_email, [to_email], html_message=html_message)
    except Exception as e:
        print(f"Failed to send payment confirmation email: {str(e)}")


def handle_refund_succeeded(refund):
    """
    Function to handle the refund succeeded
    """
    try:
        reservation = Reservation.objects.get(payment_intent=refund)

        # Update reservation status to reflect refund
        reservation.status = 'refunded'
        reservation.save()

        # Send a confirmation email to the user
        send_refund_confirmation_email(reservation)

        return Response({'status': 'success'}, status=status.HTTP_200_OK)
    except Reservation.DoesNotExist:
        return Response({"error": "Reservation not found"}, status=status.HTTP_404_NOT_FOUND)


def send_refund_confirmation_email(reservation):
    """
    Send a refund confirmation email to the user
    """
    subject = 'Conferma di rimborso per la tua prenotazione'
    html_message = render_to_string('account/stripe/refund_confirmation_email.html', {'reservation': reservation})
    plain_message = strip_tags(html_message)
    from_email = EMAIL
    to_email = reservation.user.email

    send_mail(subject, plain_message, from_email, [to_email], html_message=html_message)


def process_stripe_refund(reservation):
    """
    Process a refund using Stripe
    """
    return stripe.Refund.create(payment_intent=reservation.payment_intent_id)


def cancel_reservation_and_remove_event(reservation):
    """
    Cancel the reservation and remove the corresponding event from Google Calendar
    """
    reservation.status = 'canceled'
    reservation.save()

    try:
        creds = GoogleOAuthCredentials.objects.get(id=1)
        credentials = Credentials(
            token=creds.token,
            refresh_token=creds.refresh_token,
            token_uri=creds.token_uri,
            client_id=creds.client_id,
            client_secret=creds.client_secret,
            scopes=creds.scopes.split()
        )
        service = build('calendar', 'v3', credentials=credentials)
        service.events().delete(calendarId='primary', eventId=reservation.google_calendar_event_id).execute()
    except GoogleOAuthCredentials.DoesNotExist:
        raise Exception('Google Calendar credentials not found.')
    except Exception as e:
        raise Exception(f"Failed to remove event from Google Calendar: {str(e)}")


def calculate_total_cost(reservation):
    """
    Calculate the total cost of the reservation.
    """
    # Calculate the number of nights
    number_of_nights = (reservation.check_out - reservation.check_in).days

    # Calculate the total cost
    total_cost = number_of_nights * reservation.room.cost_per_night

    # Update the total cost field
    reservation.total_cost = total_cost
    reservation.save()

    return total_cost


def calculate_discount(reservation):
    """
    Calculate the discount of the reservation.
    """

    try:
        # Get the discount
        discount = Discount.objects.get(code=reservation.coupon_used)

        # Check if the discount is valid for the reservation dates
        if reservation.check_in >= discount.start_date and reservation.check_out <= discount.end_date:
            # Calculate the number of nights
            number_of_nights = (reservation.check_out - reservation.check_in).days

            # Check if the number of nights is greater than or equal to the required number of nights
            if number_of_nights >= discount.numbers_of_nights:
                # Calculate the discount amount
                discount_amount = reservation.total_cost * (discount.discount / 100)
                # Apply the discount
                reservation.total_cost -= discount_amount
                reservation.save()
                return discount_amount

        return None
    except Discount.DoesNotExist:
        return None


def get_google_calendar_service():
    cached_credentials = cache.get('google_calendar_credentials')

    if cached_credentials:
        # If the credentials are cached, we can use them directly
        credentials_data = json.loads(cached_credentials)
        credentials = Credentials(
            token=credentials_data['token'],
            refresh_token=credentials_data.get('refresh_token'),
            token_uri=credentials_data['token_uri'],
            client_id=credentials_data['client_id'],
            client_secret=credentials_data['client_secret'],
            scopes=credentials_data['scopes']
        )
    else:
        try:
            creds = GoogleOAuthCredentials.objects.get(id=1)
            credentials = Credentials(
                token=creds.token,
                refresh_token=creds.refresh_token,
                token_uri=creds.token_uri,
                client_id=creds.client_id,
                client_secret=creds.client_secret,
                scopes=creds.scopes.split()
            )

            # Refresh the token if it's expired
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())

            # Memorize the credentials in the cache
            credentials_data = {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes
            }
            cache.set('google_calendar_credentials', json.dumps(credentials_data), 3600)
        except GoogleOAuthCredentials.DoesNotExist:
            raise Exception("Google Calendar credentials not found.")
        except Exception as e:
            raise Exception(f"Failed to create Google Calendar service: {str(e)}")

    # Build the service
    service = build('calendar', 'v3', credentials=credentials)
    return service


def add_reservation_to_google_calendar(service, reservation):
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
                'dateTime': reservation.check_in.isoformat() + 'T00:00:00Z',
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': reservation.check_out.isoformat() + 'T00:00:00Z',
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
        service.events().insert(calendarId=reservation.room.calendar_id, body=event).execute()
        return event
    except Exception as e:
        raise Exception(f"Failed to add reservation to Google Calendar: {str(e)}")


def get_busy_dates_from_reservations(room, check_in, check_out):
    busy_dates = set()
    current_time = timezone.now()

    # Filter reservations, excluding unpaid reservations that are older than 15 minutes
    local_reservations = Reservation.objects.filter(
        room=room,
        check_out__gte=check_in,
        check_in__lte=check_out
    ).exclude(
        status=UNPAID,
        created_at__lt=(current_time - timedelta(minutes=15))
    )

    # Collect busy dates from valid reservations
    for reservation in local_reservations:
        current_date = reservation.check_in
        while current_date <= reservation.check_out:
            busy_dates.add(current_date.strftime('%Y-%m-%d'))
            current_date += timedelta(days=1)

    return busy_dates


def get_combined_busy_dates(room, check_in, check_out):
    """
    Get the combined busy dates from reservations and Google Calendar events
    """
    # Obtaining the dates occupied by reservations
    busy_dates = get_busy_dates_from_reservations(room, check_in, check_out)

    # Obtaining the dates occupied by Google Calendar events
    service = get_google_calendar_service()
    if service:
        busy_dates.update(get_busy_dates_from_calendar(service, room, check_in, check_out))

    return busy_dates


def is_room_available(busy_dates, check_in, check_out):
    """
    Check if a room is available given a set of busy dates.
    """
    check_in_date = check_in.date()
    check_out_date = check_out.date()

    return not any(
        check_in_date <= datetime.strptime(busy_date, '%Y-%m-%d').date() <= check_out_date
        for busy_date in busy_dates
    )


def get_busy_dates_from_calendar(service, room, check_in, check_out):
    busy_dates = set()
    events_result = service.events().list(
        calendarId=room.calendar_id,
        timeMin=check_in.isoformat(),
        timeMax=check_out.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])

    for event in events:
        event_summary = event.get('summary', '').lower()
        room_name_in_event = room.name.lower() in event_summary
        if room_name_in_event:
            start_date_str = event['start'].get('dateTime', event['start'].get('date'))
            end_date_str = event['end'].get('dateTime', event['end'].get('date'))
            start_date = parse_datetime(start_date_str)
            end_date = parse_datetime(end_date_str)
            current_date = start_date
            while current_date < end_date:
                busy_dates.add(current_date.strftime('%Y-%m-%d'))
                current_date += timedelta(days=1)
    return busy_dates
