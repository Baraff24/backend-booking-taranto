"""
This module contains the views of the accounts app.
"""
import io

import pytz
import stripe
import xml.etree.ElementTree as ET

from django.core.files.base import ContentFile
from django.http import FileResponse

from .constants import PENDING_COMPLETE_DATA, COMPLETE, ADMIN, CANCELED, CUSTOMER, PAID, UNPAID
from .filters import ReservationFilter
from .functions import (is_active, is_admin, calculate_total_cost, calculate_discount,
                        get_google_calendar_service, get_busy_dates_from_reservations,
                        cancel_reservation_and_remove_event,
                        is_room_available, handle_checkout_session_completed, parse_soap_response,
                        build_soap_envelope,
                        send_soap_request, send_account_deletion_email, WhatsAppService, generate_dms_puglia_xml)
from .models import User, Structure, Room, Reservation, Discount, GoogleOAuthCredentials, StructureImage, RoomImage, \
    CheckinCategoryChoices, DmsPugliaXml
from .serializers import (UserSerializer, CompleteProfileSerializer, StructureSerializer,
                          RoomSerializer, ReservationSerializer, DiscountSerializer,
                          CreateCheckoutSessionSerializer, EmailSerializer, StructureRoomSerializer,
                          StructureImageSerializer, AvailableRoomsForDatesSerializer,
                          CancelReservationSerializer, CalculateDiscountSerializer, RoomImageSerializer,
                          SendElencoSchedineSerializer, CheckinCategoryChoicesSerializer,
                          SendWhatsAppToAllUsersSerializer, SchedinaSerializer, MovimentoSerializer,
                          DmsPugliaXmlSerializer)
from datetime import datetime, timedelta
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.db.models import Case, When, Value, IntegerField, Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django_filters.rest_framework import DjangoFilterBackend
from google_auth_oauthlib.flow import Flow
from rest_framework import status, filters, viewsets
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

stripe.api_key = settings.STRIPE_SECRET_KEY


class UsersListAPI(APIView):
    """
    List all users or create a new user
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    @method_decorator(is_active)
    def get(self, request):
        user = request.user
        queryset = User.objects.all()

        if not user.is_superuser and user.type != ADMIN:
            queryset = queryset.filter(id=user.id)
        else:
            type_param = request.query_params.get('type', None)
            if type_param:
                queryset = queryset.filter(type=type_param)

        queryset = queryset.annotate(
            is_logged_in_user=Case(
                When(id=user.id, then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            )
        ).order_by('-is_logged_in_user')

        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserDetailAPI(APIView):
    """
    Retrieve, update or delete a user instance.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    @staticmethod
    def get_object(pk):
        """
        Get the user object by primary
        """
        try:
            return User.objects.get(pk=pk)
        except ObjectDoesNotExist:
            return None

    @method_decorator(is_active)
    def get(self, request, pk):
        """
        Get the user instance by primary key
        """
        obj = self.get_object(pk)
        if obj is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = self.serializer_class(obj)
        if request.user.is_superuser or request.user.type == ADMIN:
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(status=status.HTTP_403_FORBIDDEN)

    @method_decorator(is_active)
    def put(self, request, pk):
        """
        Update the user instance by primary key
        """
        obj = self.get_object(pk)
        if obj is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = self.serializer_class(obj, data=request.data)
        # if obj.id == request.user.id or request.user.is_superuser:
        if request.user.is_superuser:
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_403_FORBIDDEN)

    @method_decorator(is_active)
    def delete(self, request, pk):
        """
        Delete the user instance by primary key.
        It is a physical delete.
        The user can only delete their profile if they have no active reservations.
        """
        obj = self.get_object(pk)
        if obj is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        active_reservations = Reservation.objects.filter(
            user=obj,
            status__in=[PAID],
            check_out__gt=timezone.now()
        ).exists()

        if active_reservations:
            return Response(
                {'error': 'You cannot delete your profile while you have active bookings.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if obj.id == request.user.id or request.user.is_superuser or request.user.type == ADMIN:
            # Send email to the user
            send_account_deletion_email(obj)

            # Send whatsapp message to the user
            whatsapp_service = WhatsAppService()
            whatsapp_service.send_message(
                obj.telephone,
                'Your account has been deleted.'
            )

            obj.delete()
            return Response(status=status.HTTP_200_OK)

        return Response(status=status.HTTP_403_FORBIDDEN)


class CompleteProfileAPI(APIView):
    """
    API to complete the user's profile
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CompleteProfileSerializer

    def put(self, request):
        """
        Complete the user's profile
        """
        user = request.user
        if user.status == PENDING_COMPLETE_DATA:
            serializer = self.serializer_class(data=request.data)
            if serializer.is_valid():
                has_accepted_terms = serializer.validated_data['has_accepted_terms']
                if not has_accepted_terms:
                    return Response({'error': 'You must accept the terms and conditions.'},
                                    status=status.HTTP_400_BAD_REQUEST)

                user.first_name = serializer.validated_data['first_name']
                user.last_name = serializer.validated_data['last_name']
                user.telephone = serializer.validated_data['telephone']
                user.has_accepted_terms = has_accepted_terms
                user.status = COMPLETE
                user.save()
                return Response({'user_status': COMPLETE}, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({f"The User: {user}, has already completed his profile"},
                        status=status.HTTP_400_BAD_REQUEST)


class AddAdminTypeUserAPI(APIView):
    """
    API to add an admin type user
    """
    permission_classes = [IsAuthenticated]
    serializer_class = EmailSerializer

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def post(self, request):
        """
        Add an admin type user
        With a post request and his verified email,
        an existing user can be made an admin type user
        """
        user = request.user
        if user.is_superuser or user.type == ADMIN:
            serializer = self.serializer_class(data=request.data)
            if serializer.is_valid():
                user = User.objects.get(email=serializer.validated_data['email'])
                user.type = ADMIN
                user.save()
                return Response({'message': f'{user} is now an admin type user'}, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({'error': 'You are not authorized to perform this action'}, status=status.HTTP_403_FORBIDDEN)


class RemoveAdminTypeUserAPI(APIView):
    """
    API to add an admin type user
    """
    permission_classes = [IsAuthenticated]
    serializer_class = EmailSerializer

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def post(self, request):
        """
        Remove an admin type user
        With a post request and his verified email,
        an existing admin user can be made a customer type user
        """
        user = request.user
        if user.is_superuser or user.type == ADMIN:
            serializer = self.serializer_class(data=request.data)
            if serializer.is_valid():
                user = User.objects.get(email=serializer.validated_data['email'])
                user.type = CUSTOMER
                user.save()
                return Response({'message': f'{user} is now a customer type user'}, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({'error': 'You are not authorized to perform this action'}, status=status.HTTP_403_FORBIDDEN)


class CreateStructureAPI(APIView):
    """
    API to create a structure
    """
    permission_classes = [IsAuthenticated]
    serializer_class = StructureSerializer

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def post(self, request):
        """
        Create a structure
        """
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GetStructureImagesAPI(APIView):
    """
    API to get all images of a structure
    """
    serializer_class = StructureImageSerializer

    @staticmethod
    def get_object(pk):
        """
        Get the user object by primary
        """
        try:
            return Structure.objects.get(pk=pk)
        except ObjectDoesNotExist:
            return None

    def get(self, request, pk):
        """
        Get all images of a structure
        """
        obj = self.get_object(pk)
        if obj is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        images = obj.images.all()
        serializer = self.serializer_class(images, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class AddStructureImageAPI(APIView):
    """
    API to add an image to a structure
    """
    permission_classes = [IsAuthenticated]
    serializer_class = StructureImageSerializer

    @staticmethod
    def get_object(pk):
        """
        Get the user object by primary
        """
        try:
            return Structure.objects.get(pk=pk)
        except ObjectDoesNotExist:
            return None

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def post(self, request, pk):
        """
        Add an image to a structure
        """
        obj = self.get_object(pk)
        if obj is None:
            return Response({"detail": "Structure not found."}, status=status.HTTP_404_NOT_FOUND)

        images = request.FILES.getlist('images')
        if not images:
            return Response({"detail": "No images provided."}, status=status.HTTP_400_BAD_REQUEST)

        structure_images = [StructureImage(structure=obj, image=image) for image in images]

        try:
            StructureImage.objects.bulk_create(structure_images)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.serializer_class(structure_images, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class DeleteStructureImageAPI(APIView):
    """
    API to delete an image from a structure
    """
    permission_classes = [IsAuthenticated]

    @staticmethod
    def get_object(pk):
        """
        Get the user object by primary
        """
        try:
            return StructureImage.objects.get(pk=pk)
        except ObjectDoesNotExist:
            return None

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def delete(self, request, pk):
        """
        Delete an image from a structure
        """
        obj = self.get_object(pk)
        if obj is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_200_OK)


class StructureViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing structure instances.
    """
    serializer_class = StructureRoomSerializer
    queryset = Structure.objects.prefetch_related('rooms', 'images').all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['name', 'address']
    search_fields = ['name', 'address', 'description']
    ordering_fields = ['name', 'address']

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def create(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


class CreateRoomAPI(APIView):
    """
    API to create a room and associated Google Calendar
    """
    permission_classes = [IsAuthenticated]
    serializer_class = RoomSerializer

    @method_decorator(is_active)
    @method_decorator(is_admin)
    @transaction.atomic
    def post(self, request):
        """
        Create a room and associated Google Calendar
        """
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            try:
                room = serializer.save()
                # Create a Google Calendar for the new room
                calendar_id = self.create_google_calendar(room)
                # Save the calendar ID to the room
                room.calendar_id = calendar_id
                room.save()

                return Response(serializer.data, status=status.HTTP_201_CREATED)
            except Exception as e:
                transaction.set_rollback(True)
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def create_google_calendar(room):
        """
        Create a Google Calendar for a specific room
        """
        try:
            service = get_google_calendar_service()

            calendar = {
                'summary': f'{room.name} Calendar',
                'description': f'Calendar for room {room.name}',
                'timeZone': 'UTC'
            }

            created_calendar = service.calendars().insert(body=calendar).execute()

            # Make the calendar public
            rule = {
                'role': 'reader',  # Public read-only access
                'scope': {
                    'type': 'default',  # Public
                }
            }
            service.acl().insert(calendarId=created_calendar['id'], body=rule).execute()

            return created_calendar['id']

        except GoogleOAuthCredentials.DoesNotExist:
            raise Exception('Google Calendar credentials not found.')
        except Exception as e:
            raise Exception(f'Failed to create Google Calendar: {str(e)}')


class GetRoomImagesAPI(APIView):
    """
    API to get all images of a room
    """
    serializer_class = RoomImageSerializer

    @staticmethod
    def get_object(pk):
        """
        Get the room object by primary key
        """
        try:
            return Room.objects.get(pk=pk)
        except ObjectDoesNotExist:
            return None

    def get(self, request, pk):
        """
        Get all images of a room
        """
        obj = self.get_object(pk)
        if obj is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        images = obj.images.all()
        serializer = self.serializer_class(images, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class AddRoomImageAPI(APIView):
    """
    API to add an image to a room
    """
    permission_classes = [IsAuthenticated]
    serializer_class = RoomImageSerializer

    @staticmethod
    def get_object(pk):
        """
        Get the room object by primary key
        """
        try:
            return Room.objects.get(pk=pk)
        except ObjectDoesNotExist:
            return None

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def post(self, request, pk):
        """
        Add an image to a room
        """
        obj = self.get_object(pk)
        if obj is None:
            return Response({"detail": "Room not found."}, status=status.HTTP_404_NOT_FOUND)

        images = request.FILES.getlist('images')
        if not images:
            return Response({"detail": "No images provided."}, status=status.HTTP_400_BAD_REQUEST)

        room_images = [RoomImage(room=obj, image=image) for image in images]

        try:
            RoomImage.objects.bulk_create(room_images)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.serializer_class(room_images, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class DeleteRoomImageAPI(APIView):
    """
    API to delete an image from a room
    """
    permission_classes = [IsAuthenticated]

    @staticmethod
    def get_object(pk):
        """
        Get the room image object by primary key
        """
        try:
            return RoomImage.objects.get(pk=pk)
        except ObjectDoesNotExist:
            return None

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def delete(self, request, pk):
        """
        Delete an image from a room
        """
        obj = self.get_object(pk)
        if obj is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_200_OK)


class RoomViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing room instances.
    """
    serializer_class = RoomSerializer
    queryset = Room.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['structure', 'cost_per_night', 'max_people']
    search_fields = ['name', 'services']
    ordering_fields = ['name', 'cost_per_night', 'max_people']

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def create(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


class ReservationViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing reservation instances.
    """
    serializer_class = ReservationSerializer
    queryset = Reservation.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ReservationFilter
    search_fields = ['first_name_on_reservation', 'last_name_on_reservation', 'email_on_reservation']
    ordering_fields = ['check_in', 'check_out', 'total_cost']

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.type == ADMIN:
            return Reservation.objects.all()  # Superuser/admin can see all reservations
        return Reservation.objects.filter(user=user)  # Regular user can see only their own reservations

    @method_decorator(is_active)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @method_decorator(is_active)
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def create(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def update(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def partial_update(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def destroy(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


class DiscountViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing discount instances.
    """
    serializer_class = DiscountSerializer
    queryset = Discount.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['code', 'start_date', 'end_date']
    search_fields = ['code', 'description']
    ordering_fields = ['code', 'discount', 'start_date', 'end_date']

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


class GoogleCalendarInitAPI(APIView):
    permission_classes = [IsAdminUser]

    @staticmethod
    def get(request):
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"
                }
            },
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
            scopes=['https://www.googleapis.com/auth/calendar']
        )
        auth_url, _ = flow.authorization_url(prompt='consent')
        return Response({'auth_url': auth_url}, status=status.HTTP_200_OK)


class GoogleCalendarRedirectAPI(APIView):
    @staticmethod
    def get(request):
        code = request.GET.get('code')
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"
                }
            },
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
            scopes=['https://www.googleapis.com/auth/calendar']
        )
        flow.fetch_token(code=code)
        credentials = flow.credentials

        GoogleOAuthCredentials.objects.update_or_create(
            id=1,
            defaults={
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': ' '.join(credentials.scopes)
            }
        )
        return Response({'message': 'Google Calendar credentials have been successfully updated.'},
                        status=status.HTTP_200_OK)


# class CalendarEventsAPI(APIView):
#     @staticmethod
#     def get(request):
#         try:
#             creds = GoogleOAuthCredentials.objects.get(id=1)
#             credentials = Credentials(
#                 token=creds.token,
#                 refresh_token=creds.refresh_token,
#                 token_uri=creds.token_uri,
#                 client_id=creds.client_id,
#                 client_secret=creds.client_secret,
#                 scopes=creds.scopes.split()
#             )
#             service = build('calendar', 'v3', credentials=credentials)
#             events_result = service.events().list(calendarId='primary', maxResults=10, singleEvents=True,
#                                                   orderBy='startTime').execute()
#             events = events_result.get('items', [])
#             return Response(events, status=status.HTTP_200_OK)
#         except GoogleOAuthCredentials.DoesNotExist:
#             return Response({'error': 'Credentials not found'}, status=status.HTTP_404_NOT_FOUND)


# class CreateCalendarEventAPI(APIView):
#     permission_classes = [IsAuthenticated]
#     serializer_class = ReservationCalendarSerializer
#
#     def post(self, request):
#         try:
#             creds = GoogleOAuthCredentials.objects.get(id=1)
#             credentials = Credentials(
#                 token=creds.token,
#                 refresh_token=creds.refresh_token,
#                 token_uri=creds.token_uri,
#                 client_id=creds.client_id,
#                 client_secret=creds.client_secret,
#                 scopes=creds.scopes.split()
#             )
#             service = build('calendar', 'v3', credentials=credentials)
#
#             serializer = self.serializer_class(data=request.data)
#             if serializer.is_valid():
#                 reservation = serializer.validated_data
#                 event = {
#                     'summary': f"Reservation for {reservation['first_name_on_reservation']} {reservation['last_name_on_reservation']}",
#                     'description': f"Email: {reservation['email_on_reservation']}\nPhone: {reservation['phone_on_reservation']}\nTotal Cost: {reservation['total_cost']}\nNumber of People: {reservation['number_of_people']}\nRoom: {reservation['room']['name']}, {reservation['room']['structure']}",
#                     'start': {
#                         'dateTime': reservation['check_in'].isoformat(),
#                         'timeZone': 'UTC',
#                     },
#                     'end': {
#                         'dateTime': reservation['check_out'].isoformat(),
#                         'timeZone': 'UTC',
#                     },
#                 }
#                 event = service.events().insert(calendarId='primary', body=event).execute()
#                 return Response(event, status=status.HTTP_201_CREATED)
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
#         except GoogleOAuthCredentials.DoesNotExist:
#             return Response({'error': 'Credentials not found'}, status=status.HTTP_404_NOT_FOUND)


class StripeWebhook(APIView):
    """
    API to create a payment intent for a reservation payment using Stripe
    """

    @method_decorator(csrf_exempt)
    def post(self, request):
        """
        API to handle Stripe webhooks
        """
        payload = request.body
        sig_header = request.META['HTTP_STRIPE_SIGNATURE']
        endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, endpoint_secret
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Handle the event
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            handle_checkout_session_completed(session)

        return Response({'status': 'success'}, status=status.HTTP_200_OK)


class AvailableRoomsForDatesAPI(APIView):
    serializer_class = AvailableRoomsForDatesSerializer

    def get(self, request):
        check_in_date = request.query_params.get('check_in')
        check_out_date = request.query_params.get('check_out')
        number_of_people = request.query_params.get('number_of_people')

        if not check_in_date or not check_out_date or not number_of_people:
            return Response({'error': 'Both check_in and check_out dates and number_of_people are required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            check_in = datetime.strptime(check_in_date, '%Y-%m-%d').replace(tzinfo=pytz.UTC)
            check_out = datetime.strptime(check_out_date, '%Y-%m-%d').replace(tzinfo=pytz.UTC)
            max_people = int(number_of_people)
        except ValueError:
            return Response({
                'error': 'Invalid date format or number_of_people. Use YYYY-MM-DD for dates and ensure number_of_people is an integer.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Filter rooms available for the selected dates and number of people from the local database
        current_time = timezone.now()
        available_rooms = Room.objects.filter(
            max_people__gte=max_people
        ).exclude(
            Q(reservations__check_in__lt=check_out, reservations__check_out__gt=check_in) &
            (
                    Q(reservations__status=PAID) |
                    Q(reservations__status=UNPAID, reservations__created_at__gte=current_time - timedelta(minutes=10)) |
                    Q(reservations__status=CANCELED)
            )
        ).select_related('structure').distinct()

        final_available_rooms = []

        # Check availability for each room with Google Calendar and return only the available ones
        for room in available_rooms:
            try:

                busy_dates = get_busy_dates_from_reservations(room, check_in, check_out)

                is_available = is_room_available(busy_dates, check_in, check_out)

                if is_available:
                    final_available_rooms.append(self.serializer_class(room).data)
            except Exception as e:
                print(f'Error checking availability for room {room.name}: {str(e)}')
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(final_available_rooms, status=status.HTTP_200_OK)


class RentRoomAPI(APIView):
    """
    API to rent a room
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ReservationSerializer

    @method_decorator(is_active)
    def post(self, request):
        """
        Rent a room
        """
        user = request.user
        serializer = self.serializer_class(data=request.data)

        if serializer.is_valid():
            room = serializer.validated_data['room']  # Room is already validated and attached in the serializer
            check_in_date = serializer.validated_data['check_in']
            check_out_date = serializer.validated_data['check_out']

            # Convert check_in and check_out to datetime with time 00:00 and then to UTC
            check_in = datetime.combine(check_in_date, datetime.min.time()).replace(tzinfo=pytz.UTC)
            check_out = datetime.combine(check_out_date, datetime.min.time()).replace(tzinfo=pytz.UTC)

            # Check if the room is available in the local database
            conflicting_reservations = Reservation.objects.filter(
                room=room,
                check_in__lt=check_out,
                check_out__gt=check_in
            )

            if conflicting_reservations.exists():
                return Response({'error': 'Room is not available for the selected dates.'},
                                status=status.HTTP_400_BAD_REQUEST)

            # Check if the room is available on Google Calendar
            try:
                service = get_google_calendar_service()
                if not service:
                    return Response({'error': 'Google Calendar service unavailable.'},
                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                events_result = service.events().list(
                    calendarId=room.calendar_id,
                    timeMin=check_in.isoformat(),
                    timeMax=check_out.isoformat(),
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                events = events_result.get('items', [])

                if events:
                    return Response({
                        'error': 'Room is not available for the selected dates due to existing Google Calendar events.'},
                        status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # If the room is available, create the reservation
            reservation = Reservation(**serializer.validated_data)
            reservation.user = user

            # Calculate the total cost of the reservation
            calculate_total_cost(reservation)
            reservation.save()

            # Return the updated serializer to show all the fields
            return Response(self.serializer_class(reservation).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CalculateDiscountAPI(APIView):
    """
    API to calculate the discount for a reservation
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CalculateDiscountSerializer

    @method_decorator(is_active)
    def post(self, request):
        """
        Calculate the discount for a reservation
        """
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            discount_code = serializer.validated_data['discount_code']
            reservation_id = serializer.validated_data['reservation']

            try:
                reservation = Reservation.objects.get(reservation_id__exact=reservation_id)

                if reservation.status == PAID:
                    return Response({'error': 'This reservation has already been paid.'},
                                    status=status.HTTP_400_BAD_REQUEST)

                reservation.coupon_used = discount_code
                reservation.save()
                discount_amount = calculate_discount(reservation)

                if discount_amount is not None:
                    return Response({
                        'total_cost': str(reservation.total_cost),
                        'discount_amount': str(discount_amount)
                    }, status=status.HTTP_200_OK)
                else:
                    return Response({'error': 'Discount not valid or not applicable for the reservation dates'},
                                    status=status.HTTP_400_BAD_REQUEST)

            except Reservation.DoesNotExist:
                return Response({'error': 'Reservation not found'}, status=status.HTTP_400_BAD_REQUEST)
            except Discount.DoesNotExist:
                return Response({'error': 'Discount code not found'}, status=status.HTTP_400_BAD_REQUEST)

        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CreateCheckoutSessionLinkAPI(APIView):
    """
    API to create a checkout session link for a reservation payment using Stripe
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CreateCheckoutSessionSerializer

    @method_decorator(is_active)
    def post(self, request):
        """
        Create a checkout session link
        """
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            try:

                # Get the reservation instance from the validated data
                reservation = serializer.get_reservation()

                with transaction.atomic():
                    # Lock the reservation for payment processing
                    reservation = Reservation.objects.select_for_update().get(id=reservation.id)

                    # Retrieve room, structure, and number of people from the reservation
                    room = reservation.room
                    structure = room.structure
                    total_cost = reservation.total_cost

                    # Check if structure has images and get the first one, otherwise use a placeholder
                    structure_image = structure.images.first()
                    if structure_image:
                        image_url = request.build_absolute_uri(structure_image.image.url)
                    else:
                        image_url = "https://gmapartments-bucket1.s3.eu-south-1.amazonaws.com/logos/gm-logo-cover.png"

                    # Define line_items according to Stripe's best practices
                    line_items = [
                        {
                            'price_data': {
                                'currency': 'eur',
                                'product_data': {
                                    'name': f'{room.name} at {structure.name}',
                                    'images': [image_url],
                                },
                                'unit_amount': int(total_cost * 100),
                            },
                            'quantity': 1,
                        },
                    ]

                    # Check if the reservation is already in a state that disallows payment
                    # (e.g. already paid or canceled or it passed 10 minutes since the reservation was made)
                    time_elapsed = timezone.now() - reservation.created_at
                    if reservation.status in [PAID, CANCELED] or time_elapsed > timedelta(minutes=10):
                        return Response({'error': 'This reservation cannot be processed for payment.'},
                                        status=status.HTTP_400_BAD_REQUEST)

                    # Create a new Checkout Session for the order
                    session = stripe.checkout.Session.create(
                        payment_method_types=['card'],
                        line_items=line_items,
                        mode='payment',
                        success_url='https://gm-apartments.it/booking/payment-success',
                        cancel_url='https://gm-apartments.it/booking/payment-failed',
                    )

                    # Add the session ID to the reservation temporarily
                    reservation.payment_intent_id = session.id
                    reservation.save()

                return Response({'url': session.url}, status=status.HTTP_200_OK)

            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CancelReservationAPI(APIView):
    """
    API to cancel a reservation
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CancelReservationSerializer

    @method_decorator(is_active)
    def post(self, request, *args, **kwargs):
        """
        Cancel a reservation and process a refund
        """
        serializer = self.serializer_class(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        reservation_id = serializer.validated_data['reservation_id']

        try:
            # Admins can cancel any reservation, but normal users can only cancel their own reservations
            if request.user.type == ADMIN or request.user.is_superuser:
                reservation = Reservation.objects.get(reservation_id=reservation_id)
            else:
                reservation = Reservation.objects.get(reservation_id=reservation_id, user=request.user)

            if not reservation.payment_intent_id:
                return Response({'error': 'No payment intent found for this reservation.'},
                                status=status.HTTP_400_BAD_REQUEST)

            cancel_reservation_and_remove_event(reservation)

            return Response({
                'message': 'Reservation canceled and refund processed successfully.',
            }, status=status.HTTP_200_OK)

        except Reservation.DoesNotExist:
            return Response({'error': 'Reservation not found.'}, status=status.HTTP_404_NOT_FOUND)
        except stripe.error.StripeError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SendElencoSchedineAPI(APIView):
    """
    API View to send the Elenco Schedine to the DMS.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = SendElencoSchedineSerializer

    @method_decorator(is_active)
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        try:
            data = serializer.validated_data

            elenco_schedine = data['elenco_schedine']

            utente = data['utente']
            token = data['token']

            # Initial body content without 'ElencoSchedine'
            body_content = {
                'Utente': ('{AlloggiatiService}Utente', utente),
                'token': ('{AlloggiatiService}token', token),
            }

            elenco_subelement = ET.Element('{AlloggiatiService}ElencoSchedine')
            for schedina_data in elenco_schedine:
                schedina_str = SchedinaSerializer().to_representation(schedina_data)
                schedina_element = ET.SubElement(elenco_subelement, '{AlloggiatiService}string')
                schedina_element.text = schedina_str

            # Add the elenco_subelement directly to the body content
            body_content['ElencoSchedine'] = elenco_subelement

            soap_request = build_soap_envelope(
                action='{AlloggiatiService}Test',
                body_content=body_content
            )

            # Send the SOAP request
            response_content = send_soap_request(soap_request)

            # Parse and return the SOAP response
            response_data = parse_soap_response(
                response_content,
                'all',
                ['esito', 'ErroreCod', 'ErroreDes', 'ErroreDettaglio']
            )
            return Response(response_data, status=status.HTTP_200_OK)

        except ObjectDoesNotExist:
            return Response({"error": "Structure or Token not found"}, status=status.HTTP_404_NOT_FOUND)

        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        except ET.ParseError as e:
            return Response({"error": "Invalid SOAP response format"}, status=status.HTTP_502_BAD_GATEWAY)

        except Exception as e:
            return Response({"error": f"An unexpected error occurred: {str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UploadDataDmsPugliaXmlAPI(APIView):
    """
    API to generate and upload the DMS Puglia XML file for the Movimenti.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = MovimentoSerializer

    @method_decorator(is_active)
    def post(self, request, *args, **kwargs):
        try:
            # Validate the incoming data with the serializer
            serializer = MovimentoSerializer(data=request.data)
            if serializer.is_valid():
                try:
                    # Generate XML content
                    xml_content = generate_dms_puglia_xml(serializer.validated_data, vendor="XXXXX")

                    # Convert XML content to bytes for file-like storage
                    xml_file = io.BytesIO(xml_content.encode('utf-8'))
                    xml_file.seek(0)  # Reset the file pointer

                    # Create a DmsPugliaXml model instance and save the file
                    dms_instance = DmsPugliaXml(structure_id=serializer.validated_data['structure_id'])
                    filename = f'dms_puglia_movimenti_{datetime.now().strftime("%Y%m%d%H%M%S")}.xml'

                    # Save the file to the model's FileField
                    dms_instance.xml.save(filename, ContentFile(xml_file.read()), save=True)

                    # Serialize and return the saved instance
                    dms_serializer = DmsPugliaXmlSerializer(dms_instance)
                    return Response(dms_serializer.data, status=status.HTTP_201_CREATED)

                except Exception as e:
                    print(f"Error saving file: {e}")
                    return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            print(f"Unexpected error: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ListDmsPugliaXmlFilesAPI(APIView):
    """
    API to list all the available DMS Puglia XML files.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = DmsPugliaXmlSerializer

    @method_decorator(is_active)
    def get(self, request, *args, **kwargs):
        try:
            # Query all XML files in the DmsPugliaXml model
            xml_files = DmsPugliaXml.objects.all()

            # Serialize the data
            serializer = self.serializer_class(xml_files, many=True)

            # Return the serialized data
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DownloadDmsPugliaXmlFileAPI(APIView):
    """
    API to download the DMS Puglia XML file.
    """
    permission_classes = [IsAuthenticated]

    @staticmethod
    def get_object(pk):
        """
        Get the DmsPugliaXml object by primary
        """
        try:
            return DmsPugliaXml.objects.get(pk=pk)
        except ObjectDoesNotExist:
            return None

    @method_decorator(is_active)
    def get(self, request, pk, *args, **kwargs):
        try:
            # Get the DmsPugliaXml instance by primary key (id)
            dms_puglia_xml = self.get_object(pk=pk)

            # Ensure that the file exists before responding
            if not dms_puglia_xml.xml:
                return Response({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)

            # Create a response with FileResponse for streaming the file
            response = FileResponse(dms_puglia_xml.xml.open(), content_type='application/xml')
            response['Content-Disposition'] = f'attachment; filename="{dms_puglia_xml.xml.name}"'

            return response

        except DmsPugliaXml.DoesNotExist:
            return Response({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"An unexpected error occurred: {str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CheckinCategoryChoicesAPI(APIView):
    """
    API View to return check-in category choices.
    If a 'category' parameter is provided, it returns choices for that specific category.
    If no parameter is provided, it returns all choices across all categories.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CheckinCategoryChoicesSerializer

    @method_decorator(is_active)
    def get(self, request):
        category = request.query_params.get('category', None)

        if category:
            # If category is provided, filter by category
            choices = CheckinCategoryChoices.objects.filter(category=category)
            if not choices.exists():
                return Response({"error": f"No choices found for category '{category}'."},
                                status=status.HTTP_404_NOT_FOUND)
        else:
            # If no category is provided, return all choices
            choices = CheckinCategoryChoices.objects.all()

        # Serialize the results
        serializer = self.serializer_class(choices, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SendWhatsAppToAllUsersAPI(APIView):
    """
    API View to send a WhatsApp message to all users on the site.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = SendWhatsAppToAllUsersSerializer

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def post(self, request):
        """
        Handles POST requests to send a WhatsApp message to all users.
        """
        try:
            # Validate the incoming data
            serializer = self.serializer_class(data=request.data)
            if not serializer.is_valid():
                print("Error in serializer validation")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            message = serializer.validated_data['message']
            template_sid = "HXb660cd668c95559734a235228ed03af4"  # Messaging service SID
            whatsapp_service = WhatsAppService()
            failed_users = []
            successful_jobs = []

            template_parameters = [
                {"type": "text", "text": message}  # This replaces {{1}} in the template
            ]

            # Retrieve all users with a valid phone number
            try:
                users = User.objects.exclude(telephone__isnull=True).exclude(telephone__exact='')
                print(f"Number of users with valid phone numbers: {len(users)}")
            except Exception as e:
                print(f"Error retrieving users: {e}")
                return Response({"message": "Error retrieving users"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Iterate over each user and queue WhatsApp message
            for user in users:
                try:
                    job_id = whatsapp_service.queue_message(
                        user.phone_number,
                        template_sid,
                        template_parameters
                    )
                    if job_id:
                        successful_jobs.append({"user": user.id, "job_id": job_id})
                        print(f"Message queued successfully for user ID: {user.id}")
                    else:
                        failed_users.append({"user": user.id, "phone_number": user.phone_number})
                        print(f"Failed to queue message for user ID: {user.id}")
                except Exception as e:
                    print(f"Error queuing message for user ID {user.id}: {e}")
                    failed_users.append({"user": user.id, "phone_number": user.phone_number})

            # Check if there were any failures
            if failed_users:
                print(f"Some messages could not be queued. Failed users: {failed_users}")
                return Response({
                    "message": "Some messages could not be queued.",
                    "failed_users": failed_users,
                    "successful_jobs": successful_jobs
                }, status=status.HTTP_207_MULTI_STATUS)

            # If all messages were queued successfully
            print(f"Messages queued successfully for all users.")
            return Response({
                "message": "Messages queued successfully.",
                "successful_jobs": successful_jobs
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Unexpected error in SendWhatsAppToAllUsersAPI: {e}")
            return Response({"message": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
