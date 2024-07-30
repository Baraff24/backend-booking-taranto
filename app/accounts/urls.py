"""
This module contains the URL patterns for the accounts app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (UsersListAPI, UserDetailAPI, CompleteProfileAPI,
                    StructureViewSet, RoomViewSet, ReservationViewSet,
                    DiscountViewSet, GoogleCalendarInitAPI, GoogleCalendarRedirectAPI,
                    RentRoomAPI, AvailableRoomsAPI, StripeWebhook)

# Create the router and register the viewsets with it.
router = DefaultRouter()
router.register(r'structures', StructureViewSet)
router.register(r'rooms', RoomViewSet)
router.register(r'reservations', ReservationViewSet)
router.register(r'discounts', DiscountViewSet)

urlpatterns = [
    path("users/", UsersListAPI.as_view(), name="users"),
    path("users/<int:pk>/", UserDetailAPI.as_view(), name="user-detail"),
    path("users/complete-profile/", CompleteProfileAPI.as_view(),
         name="complete-profile"),
    path('google-calendar/init/', GoogleCalendarInitAPI.as_view(), name='google-calendar-init'),
    path('google-calendar/redirect/', GoogleCalendarRedirectAPI.as_view(), name='google-calendar-redirect'),
    path('room/rent-room/', RentRoomAPI.as_view(), name='rent-room'),
    path('room/available-rooms/', AvailableRoomsAPI.as_view(), name='available-rooms'),
    path('stripe-webhook/', StripeWebhook.as_view(), name='stripe-webhook'),
    path('', include(router.urls)),
]
