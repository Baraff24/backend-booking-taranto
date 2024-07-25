"""
This module contains the URL patterns for the accounts app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (UsersListAPI, UserDetailAPI, CompleteProfileAPI,
                    StructureViewSet, RoomViewSet, ReservationViewSet,
                    DiscountViewSet)

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
    path('', include(router.urls)),
]
