"""
This module contains the URL patterns for the accounts app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (UsersListAPI, UserDetailAPI, CompleteProfileAPI,
                    StructureViewSet, RoomViewSet, ReservationViewSet,
                    DiscountViewSet, GoogleCalendarInitAPI, GoogleCalendarRedirectAPI,
                    RentRoomAPI, StripeWebhook, SendElencoSchedineAPI,
                    CreateCheckoutSessionLinkAPI, AddAdminTypeUserAPI, CreateStructureAPI,
                    AddStructureImageAPI, GetStructureImagesAPI, AvailableRoomsForDatesAPI,
                    DeleteStructureImageAPI, CancelReservationAPI, CheckinCategoryChoicesAPI,
                    RemoveAdminTypeUserAPI, CreateRoomAPI, CalculateDiscountAPI,
                    GetRoomImagesAPI, AddRoomImageAPI, DeleteRoomImageAPI,
                    UploadDataDmsPugliaXmlAPI, ListDmsPugliaXmlFilesAPI, DownloadDmsPugliaXmlFileAPI,
                    SendWhatsAppToAllUsersAPI)

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
    path("users/remove-admin/", RemoveAdminTypeUserAPI.as_view(), name="remove-admin"),
    path('google-calendar/init/', GoogleCalendarInitAPI.as_view(), name='google-calendar-init'),
    path('google-calendar/redirect/', GoogleCalendarRedirectAPI.as_view(), name='google-calendar-redirect'),
    path('structure/create-structure/', CreateStructureAPI.as_view(), name='create-structure'),
    path('structures/<int:pk>/images/', GetStructureImagesAPI.as_view(), name='structure-images-list'),  # GET
    path('structures/<int:pk>/images/add/', AddStructureImageAPI.as_view(), name='add-structure-image'),  # POST
    path('structures/images/<int:pk>/delete/', DeleteStructureImageAPI.as_view(), name='delete-structure-image'),
    path('rooms/<int:pk>/images/', GetRoomImagesAPI.as_view(), name='get-room-images'),
    path('rooms/<int:pk>/images/add/', AddRoomImageAPI.as_view(), name='add-room-image'),
    path('rooms/images/<int:pk>/delete/', DeleteRoomImageAPI.as_view(), name='delete-room-image'),
    path('room/create-room/', CreateRoomAPI.as_view(), name='create-room'),
    path('room/rent-room/', RentRoomAPI.as_view(), name='rent-room'),
    path('room/available-rooms-for-dates/', AvailableRoomsForDatesAPI.as_view(), name='available-rooms-for-dates'),
    path('discount/calculate-discount/', CalculateDiscountAPI.as_view(), name='calculate-discount'),
    path('stripe/create-checkout-session/', CreateCheckoutSessionLinkAPI.as_view(), name='create-checkout-session'),
    path('send-whatsapp-to-all-users/', SendWhatsAppToAllUsersAPI.as_view(), name='send-whatsapp-to-all-users'),
    path('cancel-reservation/', CancelReservationAPI.as_view(), name='cancel-reservation'),
    path('checkin-category-choices/', CheckinCategoryChoicesAPI.as_view(), name='checkin-category-choices'),
    path('send-elenco-schedine/', SendElencoSchedineAPI.as_view(), name='send-elenco-schedine'),
    path('upload-data-dms-puglia-xml/', UploadDataDmsPugliaXmlAPI.as_view(), name='upload-data-dms-puglia-xml'),
    path('list-dms-puglia-xml-files/', ListDmsPugliaXmlFilesAPI.as_view(), name='list-dms-puglia-xml-files'),
    path('download-dms-puglia-xml-file/<int:pk>/', DownloadDmsPugliaXmlFileAPI.as_view(), name='download-dms-puglia-xml-file'),
    path('stripe-webhook/', StripeWebhook.as_view(), name='stripe-webhook'),
    path('', include(router.urls)),
]
