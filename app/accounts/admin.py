"""
This file is used to customize the User model in the Django admin panel.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Structure, Room, Reservation, Discount, GoogleOAuthCredentials


class CustomUserAdmin(UserAdmin):
    """
    Custom User model for the Django admin panel.
    """
    fieldsets = (
        *UserAdmin.fieldsets,  # original form fieldsets, expanded
        (  # new fieldset added on to the bottom

            # group heading of your choice;
            # set to None for a blank space instead of a header
            'Other information of the User',
            {
                'fields': (
                    'telephone',
                    'status',
                    'type',
                ),
            },
        ),
    )


admin.site.register(User, CustomUserAdmin)
admin.site.register(Structure)
admin.site.register(Room)
admin.site.register(Reservation)
admin.site.register(Discount)
admin.site.register(GoogleOAuthCredentials)
