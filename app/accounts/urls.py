"""
This module contains the URL patterns for the accounts app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (UsersListAPI, UserDetailAPI, CompleteProfileAPI,
                    StructureViewSet, RoomViewSet, ReservationViewSet,
                    DiscountViewSet, GoogleCalendarInitAPI, GoogleCalendarRedirectAPI,
                    RentRoomAPI, AvailableRoomAPI, StripeWebhook,
                    CreateCheckoutSessionLinkAPI, AddAdminTypeUserAPI, CreateStructureAPI,
                    AddStructureImageAPI, GetStructureImagesAPI, AvailableRoomsForDatesAPI,
                    DeleteStructureImageAPI, CancelReservationAPI, GenerateXmlAndSendToDmsAPI)

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
    path("users/add-admin/", AddAdminTypeUserAPI.as_view(), name="add-admin"),
    path('google-calendar/init/', GoogleCalendarInitAPI.as_view(), name='google-calendar-init'),
    path('google-calendar/redirect/', GoogleCalendarRedirectAPI.as_view(), name='google-calendar-redirect'),
    path('structure/create-structure/', CreateStructureAPI.as_view(), name='create-structure'),
    path('structures/<int:pk>/images/add-structure-images/', AddStructureImageAPI.as_view(), name='add-structure-image'),
    path('structures/images/<int:pk>/delete-structure-images/', DeleteStructureImageAPI.as_view(), name='delete-structure-image'),
    path('structures/<int:pk>/images/get-structure-images/', GetStructureImagesAPI.as_view(), name='get-structure-images'),
    path('room/rent-room/', RentRoomAPI.as_view(), name='rent-room'),
    path('room/available-rooms-for-dates/', AvailableRoomsForDatesAPI.as_view(), name='available-rooms-for-dates'),
    path('room/available-room/', AvailableRoomAPI.as_view(), name='available-rooms'),
    path('stripe/create-checkout-session/', CreateCheckoutSessionLinkAPI.as_view(), name='create-checkout-session'),
    path('cancel-reservation/', CancelReservationAPI.as_view(), name='cancel-reservation'),
    path('generate-xml-and-send-to-dms/', GenerateXmlAndSendToDmsAPI.as_view(), name='generate-xml-and-send-to-dms'),
    path('stripe-webhook/', StripeWebhook.as_view(), name='stripe-webhook'),
    path('', include(router.urls)),
]
