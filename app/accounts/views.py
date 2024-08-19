"""
This module contains the views of the accounts app.
"""
import os

import pytz
import stripe
import xml.etree.ElementTree as ET
import requests
from .constants import PENDING_COMPLETE_DATA, COMPLETE, ADMIN, CANCELED, CUSTOMER, PAID
from .functions import is_active, handle_payment_intent_succeeded, is_admin, calculate_total_cost, calculate_discount, \
    handle_refund_succeeded, get_google_calendar_service, get_busy_dates_from_reservations, \
    get_busy_dates_from_calendar, process_stripe_refund, cancel_reservation_and_remove_event, is_room_available
from .models import User, Structure, Room, Reservation, Discount, GoogleOAuthCredentials, StructureImage
from .serializers import (UserSerializer, CompleteProfileSerializer, StructureSerializer,
                          RoomSerializer, ReservationSerializer, DiscountSerializer,
                          CreateCheckoutSessionSerializer, EmailSerializer, StructureRoomSerializer,
                          StructureImageSerializer, AvailableRoomsForDatesSerializer, GenerateXmlAndSendToDmsSerializer,
                          CancelReservationSerializer, CalculateDiscountSerializer)
from datetime import datetime, timedelta
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Case, When, Value, IntegerField, Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django_filters.rest_framework import DjangoFilterBackend
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from rest_framework import status, filters, viewsets
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from lxml import etree

stripe.api_key = settings.STRIPE_SECRET_KEY


class UsersListAPI(APIView):
    """
    List all users or create a new user
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    @method_decorator(is_active)
    def get(self, request):
        """
        Get all users if the user is a superuser
        """
        user = request.user
        if user.is_superuser or user.type == ADMIN:
            type_param = request.query_params.get('type', None)
            if type_param:
                obj = User.objects.filter(type=type_param)
            else:
                obj = User.objects.all()

            obj = obj.annotate(
                is_logged_in_user=Case(
                    When(id=user.id, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField()
                )
            ).order_by('-is_logged_in_user')

        else:
            obj = User.objects.filter(id=user.id)

        serializer = self.serializer_class(obj, many=True)
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
        It is not a physical delete, but a logical delete (change of status).
        """
        obj = self.get_object(pk)
        if obj is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        # if obj.id == request.user.id or request.user.is_superuser:
        if request.user.is_superuser:
            obj.is_active = False
            obj.save()
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
                user.first_name = serializer.validated_data['first_name']
                user.last_name = serializer.validated_data['last_name']
                user.telephone = serializer.validated_data['telephone']
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
    queryset = Structure.objects.all()
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
    filterset_fields = ['user', 'room', 'check_in', 'check_out']
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

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @method_decorator(is_active)
    @method_decorator(is_admin)
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
        if event['type'] == 'payment_intent.succeeded':
            payment_intent = event['data']['object']
            handle_payment_intent_succeeded(payment_intent)

        if event['type'] == 'refund.succeeded':
            refund = event['data']['object']
            handle_refund_succeeded(refund)

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
            (Q(reservations__status='PAID') |
             Q(reservations__status='UNPAID', reservations__created_at__gte=current_time - timedelta(minutes=15)))
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


class AvailableRoomAPI(APIView):
    serializer_class = AvailableRoomsForDatesSerializer

    def get(self, request):
        room_id = request.query_params.get('room_id')
        check_in_date = request.query_params.get('check_in')
        check_out_date = request.query_params.get('check_out')

        if not room_id or not check_in_date or not check_out_date:
            return Response({'error': 'room_id, check_in and check_out dates are required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            check_in = datetime.strptime(check_in_date, '%Y-%m-%d').replace(tzinfo=pytz.UTC)
            check_out = datetime.strptime(check_out_date, '%Y-%m-%d').replace(tzinfo=pytz.UTC)
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

        room = Room.objects.select_related('structure').filter(id=room_id).first()
        if not room:
            return Response({'error': 'Room does not exist.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            service = get_google_calendar_service()
            if not service:
                return Response({'error': 'Google Calendar service unavailable for this room.'},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            busy_dates = get_busy_dates_from_reservations(room, check_in, check_out)
            busy_dates.update(get_busy_dates_from_calendar(service, room, check_in, check_out))

            available_dates = []
            unavailable_dates = []
            current_date = check_in.date()
            while current_date <= check_out.date():
                if current_date.strftime('%Y-%m-%d') not in busy_dates:
                    available_dates.append(current_date.strftime('%Y-%m-%d'))
                else:
                    unavailable_dates.append(current_date.strftime('%Y-%m-%d'))
                current_date += timedelta(days=1)

            room_data = self.serializer_class({
                'structure': room.structure,
                'room': room,
                'available_dates': available_dates,
                'unavailable_dates': unavailable_dates
            }).data

            return Response(room_data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
            check_in = serializer.validated_data['check_in']
            check_out = serializer.validated_data['check_out']

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
                    timeMin=check_in.isoformat() + 'Z',
                    timeMax=check_out.isoformat() + 'Z',
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

            return Response(serializer.data, status=status.HTTP_201_CREATED)
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
                reservation = Reservation.objects.get(id=reservation_id)
                reservation.coupon_used = discount_code
                calculate_total_cost(reservation)
                discount_amount = calculate_discount(reservation)
                reservation.save()

                return Response({
                    'total_cost': reservation.total_cost,
                    'discount_amount': discount_amount
                },
                    status=status.HTTP_200_OK)
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

                # Retrieve room, structure, and number of people from the reservation
                room = reservation.room
                structure = room.structure
                cost_per_night = room.cost_per_night
                number_of_people = reservation.number_of_people

                line_items = [
                    {
                        'price_data': {
                            'currency': 'eur',
                            'product_data': {
                                'name': f'{room.name} at {structure.name}',
                                'images': [f'https://example.com/{room.name}.jpg'],
                            },
                            'unit_amount': int(cost_per_night * 100),
                        },
                        'quantity': number_of_people,
                    },
                ]

                # Lock the reservation for payment processing
                reservation = Reservation.objects.select_for_update().get(id=reservation.id)

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
                    success_url='https://example.com/success',
                    cancel_url='https://example.com/cancel',
                )

                # Add the payment intent id to the reservation
                reservation.payment_intent_id = session.payment_intent
                reservation.save()

                return Response({'id': session.id}, status=status.HTTP_200_OK)

            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CancelReservationAPI(APIView):
    """
    API to cancel a reservation and process a refund using Stripe
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CancelReservationSerializer

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def post(self, request):
        """
        Cancel a reservation and process a refund
        """
        serializer = self.serializer_class(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        reservation_id = serializer.validated_data['reservation_id']

        try:
            reservation = Reservation.objects.get(reservation_id__exact=reservation_id)

            if not reservation.payment_intent_id:
                return Response({'error': 'No payment intent found for this reservation.'},
                                status=status.HTTP_400_BAD_REQUEST)

            # If the difference between the check-in date and the current date
            # is less than 4 days, a refund is not possible
            if (reservation.check_in - datetime.now()).days < 4:
                # Update reservation status and remove event from Google Calendar
                cancel_reservation_and_remove_event(reservation)

                return Response({'error': 'A refund is not possible for this reservation,'
                                          'however the reservation has been canceled successfully.'},
                                status=status.HTTP_200_OK)

            # Process the refund using Stripe
            refund = process_stripe_refund(reservation)

            cancel_reservation_and_remove_event(reservation)

            return Response({
                'message': 'Reservation canceled and refund processed successfully.',
                'refund_id': refund.id
            }, status=status.HTTP_200_OK)

        except Reservation.DoesNotExist:
            return Response({'error': 'Reservation not found.'}, status=status.HTTP_404_NOT_FOUND)
        except stripe.error.StripeError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GenerateXmlAndSendToDmsAPI(APIView):
    """
    API to generate an XML file and send it to a Document Management System
    """
    permission_classes = [IsAuthenticated]
    serializer_class = GenerateXmlAndSendToDmsSerializer

    @method_decorator(is_active)
    @method_decorator(is_admin)
    def post(self, request):
        """
        Generate an XML file and send it to a DMS
        """
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        utente = serializer.validated_data['utente']
        token = serializer.validated_data['token']
        elenco_schedine = serializer.validated_data['elenco_schedine']
        id_appartamento = serializer.validated_data['id_appartamento']

        try:
            # Create XML
            root = ET.Element("soap:Envelope", attrib={
                "xmlns:soap": "http://www.w3.org/2003/05/soap-envelope",
                "xmlns:all": "AlloggiatiService"
            })
            body = ET.SubElement(root, "soap:Body")
            gestione = ET.SubElement(body, "all:GestioneAppartamenti_Send")

            ET.SubElement(gestione, "all:Utente").text = utente
            ET.SubElement(gestione, "all:token").text = token

            elenco = ET.SubElement(gestione, "all:ElencoSchedine")
            for schedina in elenco_schedine:
                ET.SubElement(elenco, "all:string").text = schedina

            ET.SubElement(gestione, "all:IdAppartamento").text = str(id_appartamento)

            xml_data = ET.tostring(root, encoding='utf-8', xml_declaration=True)

            # XML Validation
            xsd_file_path = os.path.join(settings.TEMPLATES[0]['DIRS'][0], 'xsdValidationScheme', 'scheme.xsd')
            with open(xsd_file_path, 'r') as xsd_file:
                schema_root = etree.XML(xsd_file.read())
                schema = etree.XMLSchema(schema_root)
                xml_doc = etree.fromstring(xml_data)
                schema.assertValid(xml_doc)

            # Send XML
            url = "DMS_URL"
            headers = {'Content-Type': 'application/xml'}
            response = requests.post(url, data=xml_data, headers=headers)

            response.raise_for_status()
            return Response({"message": "Data sent successfully"}, status=status.HTTP_200_OK)

        except etree.DocumentInvalid as e:
            return Response({"error": f"Invalid XML: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        except requests.exceptions.RequestException as e:
            return Response({"error": f"Error while sending data: {str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({"error": f"Unexpected error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
