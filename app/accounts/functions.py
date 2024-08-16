"""
This file contains all the functions and decorators used in the accounts app.
"""
from datetime import timedelta

import django.contrib.auth
from functools import wraps

import stripe
from decouple import config
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.dateparse import parse_datetime
from django.utils.html import strip_tags
from rest_framework import status
from rest_framework.response import Response
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from allauth.account.models import EmailAddress

from accounts.constants import COMPLETE, ADMIN
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
def handle_payment_intent_succeeded(payment_intent):
    """
    Function to handle the payment intent succeeded
    """
    # Get the reservation and set the paid field to True
    try:
        reservation = Reservation.objects.get(payment_intent=payment_intent)
        reservation.payed = True
        reservation.save()

        try:
            # Send an email to the user to confirm the payment
            subject = 'Conferma di pagamento per la tua prenotazione'
            html_message = render_to_string('account/stripe/payment_confirmation_email.html',
                                            {'reservation': reservation})
            plain_message = strip_tags(html_message)
            from_email = EMAIL
            to_email = reservation.user.email

            send_mail(subject, plain_message, from_email, [to_email], html_message=html_message)

            return Response({'status': 'success'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Reservation.DoesNotExist:
        return Response({"Error": "Reservation not found"},
                        status=status.HTTP_404_NOT_FOUND)


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
                return Response({'Discount applied': discount_amount}, status=status.HTTP_200_OK)
        return Response({"Error": "Discount not valid for the reservation dates"},
                        status=status.HTTP_400_BAD_REQUEST)
    except Discount.DoesNotExist:
        return Response({"Error": "Discount not found"},
                        status=status.HTTP_404_NOT_FOUND)


def get_google_calendar_service():
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
        return service
    except GoogleOAuthCredentials.DoesNotExist:
        return None


def get_busy_dates_from_reservations(room, check_in, check_out):
    busy_dates = set()
    local_reservations = Reservation.objects.filter(
        room=room,
        check_out__gte=check_in,
        check_in__lte=check_out
    )
    for reservation in local_reservations:
        current_date = reservation.check_in
        while current_date <= reservation.check_out:
            busy_dates.add(current_date.strftime('%Y-%m-%d'))
            current_date += timedelta(days=1)
    return busy_dates


def get_busy_dates_from_calendar(service, room, check_in, check_out):
    busy_dates = set()
    events_result = service.events().list(
        calendarId='primary',
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
