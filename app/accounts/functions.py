"""
This file contains all the functions and decorators used in the accounts app.
"""
import django.contrib.auth
from functools import wraps
from rest_framework import status
from rest_framework.response import Response

from allauth.account.models import EmailAddress

from accounts.constants import COMPLETE, ADMIN

User = django.contrib.auth.get_user_model()


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
    # Implement your logic to handle successful payment here

    print("*" * 50)
    print("PaymentIntent was successful!")
    print(payment_intent)
    print("*" * 50)

    return Response(status=status.HTTP_200_OK)
