"""
This file contains all the functions and decorators used in the accounts app.
"""
import datetime
from functools import wraps
from rest_framework import status, serializers
from rest_framework.response import Response

from allauth.account.models import EmailAddress


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
                return view_func(request, *args, **kwargs)
            return Response({"Error": "Your email is not verified"},
                            status=status.HTTP_403_FORBIDDEN)
        return Response({"Error": "Your account is not active"},
                        status=status.HTTP_403_FORBIDDEN)

    return decorator


#####################################################################################
# FUNCTIONS #
#####################################################################################
def handle_payment_intent_succeeded(payment_intent):
    # Implement your logic to handle successful payment here
    pass
