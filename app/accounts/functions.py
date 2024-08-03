"""
This file contains all the functions and decorators used in the accounts app.
"""
import django.contrib.auth
from functools import wraps
from decouple import config
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from rest_framework import status
from rest_framework.response import Response

from allauth.account.models import EmailAddress

from accounts.constants import COMPLETE, ADMIN
from accounts.models import Reservation, Discount

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
                return Response({"Error": "You have to complete the data completion process"},
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
            html_message = render_to_string('account/email/payment_confirmation_email.html', {'reservation': reservation})
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
