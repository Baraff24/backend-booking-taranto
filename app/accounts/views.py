"""
This module contains the views of the accounts app.
"""
import stripe
from datetime import datetime, timedelta, timezone
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Case, When, Value, IntegerField
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django_filters.rest_framework import DjangoFilterBackend
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from rest_framework import status, filters, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.settings.base import BASE_DIR
from .constants import PENDING_COMPLETE_DATA, COMPLETE, ADMIN
from .functions import is_active, handle_payment_intent_succeeded, is_admin, calculate_total_cost, calculate_discount
from .models import User, Structure, Room, Reservation, Discount, GoogleOAuthCredentials
from .serializers import (UserSerializer, CompleteProfileSerializer, StructureSerializer,
                          RoomSerializer, ReservationSerializer, DiscountSerializer,
                          CreateCheckoutSessionSerializer, EmailSerializer, StructureRoomSerializer,
                          StructureImageSerializer)

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
        if not user.is_superuser or not user.type == ADMIN:
            return Response(status=status.HTTP_403_FORBIDDEN)

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
        if request.user.is_superuser:
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
    def post(self, request):
        """
        Add an admin type user
        With a post request and his verified email,
        an existing user can be made an admin type user
        """
        user = request.user
        if user.is_superuser:
            serializer = self.serializer_class(data=request.data)
            if serializer.is_valid():
                user = User.objects.get(email=serializer.validated_data['email'])
                user.type = ADMIN
                user.save()
                return Response({'message': f'{user} is now an admin type user'}, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({'error': 'You are not authorized to perform this action'}, status=status.HTTP_403_FORBIDDEN)


class CreateStructureAPI(APIView):
    """
    API to create a structure
    """
    permission_classes = [IsAuthenticated]
    serializer_class = StructureSerializer

    @method_decorator(is_active)
    def post(self, request):
        """
        Create a structure
        """
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
            return User.objects.get(pk=pk)
        except ObjectDoesNotExist:
            return None

    @method_decorator(is_active)
    def post(self, request, pk):
        """
        Add an image to a structure
        """
        obj = self.get_object(pk)
        if obj is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
            return User.objects.get(pk=pk)
        except ObjectDoesNotExist:
            return None

    @method_decorator(is_active)
    def delete(self, request, pk):
        """
        Delete an image from a structure
        """
        obj = self.get_object(pk)
        if obj is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        obj.delete(structure=obj)
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

    @method_decorator(is_active)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @method_decorator(is_active)
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

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
    @method_decorator(is_active)
    @method_decorator(is_admin)
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

        return Response({'status': 'success'}, status=status.HTTP_200_OK)


class AvailableRoomsAPI(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = RoomSerializer

    def get(self, request):
        room_ids = request.query_params.getlist('rooms')
        try:
            rooms = Room.objects.filter(id__in=room_ids)
        except Room.DoesNotExist:
            return Response({'error': 'One or more rooms do not exist.'}, status=status.HTTP_404_NOT_FOUND)

        available_dates = {}
        try:
            creds = GoogleOAuthCredentials.objects.get(id=1)
            credentials = Credentials(
                token=creds.token,
                refresh_token=creds.refresh_token,
                token_uri=creds.token_uri,
                client_id=creds.client_id,
                client_secret=creds.client_secret,
                scopes=creds.scopes.split()
            )
            service = build('calendar', 'v3', credentials=credentials)

            for room in rooms:
                room_availability = []
                today = datetime.now(timezone.utc).isoformat()
                next_year = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()

                # Get local reservations
                local_reservations = Reservation.objects.filter(room=room, check_out__gte=today)

                # Get Google Calendar events
                events_result = service.events().list(
                    calendarId='primary',
                    timeMin=today,
                    timeMax=next_year,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                events = events_result.get('items', [])

                # Combine local reservations and Google Calendar events
                busy_dates = []
                for reservation in local_reservations:
                    current_date = reservation.check_in
                    while current_date <= reservation.check_out:
                        busy_dates.append(current_date.strftime('%Y-%m-%d'))
                        current_date += timedelta(days=1)

                for event in events:
                    start_date = datetime.fromisoformat(event['start'].get('dateTime', event['start'].get('date'))[:-1])
                    end_date = datetime.fromisoformat(event['end'].get('dateTime', event['end'].get('date'))[:-1])
                    current_date = start_date
                    while current_date < end_date:
                        busy_dates.append(current_date.strftime('%Y-%m-%d'))
                        current_date += timedelta(days=1)

                # Determine available dates
                current_date = datetime.now(timezone.utc).date()
                one_year_from_now = current_date + timedelta(days=365)
                while current_date <= one_year_from_now:
                    if current_date.strftime('%Y-%m-%d') not in busy_dates:
                        room_availability.append(current_date.strftime('%Y-%m-%d'))
                    current_date += timedelta(days=1)

                available_dates[room.name] = room_availability

                rooms_data = self.serializer_class(rooms, many=True).data
                response_data = {
                    'rooms': rooms_data,
                    'available_dates': available_dates
                }

            return Response(response_data, status=status.HTTP_200_OK)

        except GoogleOAuthCredentials.DoesNotExist:
            return Response({'error': 'Google Calendar credentials not found.'}, status=status.HTTP_404_NOT_FOUND)


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
            room = serializer.validated_data['room']
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
                creds = GoogleOAuthCredentials.objects.get(id=1)
                credentials = Credentials(
                    token=creds.token,
                    refresh_token=creds.refresh_token,
                    token_uri=creds.token_uri,
                    client_id=creds.client_id,
                    client_secret=creds.client_secret,
                    scopes=creds.scopes.split()
                )
                service = build('calendar', 'v3', credentials=credentials)
                events_result = service.events().list(
                    calendarId='primary',
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
            except GoogleOAuthCredentials.DoesNotExist:
                return Response({'error': 'Google Calendar credentials not found.'}, status=status.HTTP_404_NOT_FOUND)

            # If the room is available, create the reservation
            reservation = Reservation(**serializer.validated_data)
            reservation.user = user

            # Calculate the total cost of the reservation
            calculate_total_cost(reservation)
            reservation.save()

            # Create the event on Google Calendar
            # Move this code to function after the payment is successful
            event = {
                'summary': f"Reservation for {reservation.first_name_on_reservation} {reservation.last_name_on_reservation}",
                'description': (
                    f"Email: {reservation.email_on_reservation}\n"
                    f"Phone: {reservation.phone_on_reservation}\n"
                    f"Total Cost: {reservation.total_cost}\n"
                    f"Number of People: {reservation.number_of_people}\n"
                    f"Room: {reservation.room.name}, {reservation.room.structure}"
                ),
                'start': {
                    'dateTime': reservation.check_in.isoformat() + 'T00:00:00Z',
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': reservation.check_out.isoformat() + 'T00:00:00Z',
                    'timeZone': 'UTC',
                },
                'location': reservation.room.structure.address,
                'attendees': [
                    {'email': reservation.email_on_reservation},
                    # You can add more attendees if needed
                ],
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                        {'method': 'popup', 'minutes': 10},
                    ],
                },
            }
            service.events().insert(calendarId='primary', body=event).execute()

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CalculateDiscountAPI(APIView):
    """
    API to calculate the discount for a reservation
    """
    permission_classes = [IsAuthenticated]

    @method_decorator(is_active)
    def post(self, request):
        """
        Calculate the discount for a reservation
        """
        data = request.data
        discount_code = data.get('discount_code')
        reservation_id = data.get('reservation')

        try:
            reservation = Reservation.objects.get(id=reservation_id)
            reservation.coupon_used = discount_code
            calculate_total_cost(reservation)
            discount_amount = calculate_discount(reservation)
            reservation.save()
            return Response({'total_cost': reservation.total_cost, 'discount_amount': discount_amount},
                            status=status.HTTP_200_OK)
        except Reservation.DoesNotExist:
            return Response({'error': 'Reservation not found'}, status=status.HTTP_400_BAD_REQUEST)
        except Discount.DoesNotExist:
            return Response({'error': 'Discount code not found'}, status=status.HTTP_400_BAD_REQUEST)


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
            data = serializer.validated_data
            room = Room.objects.get(id=data['room'])
            structure = room.structure
            cost_per_night = room.cost_per_night
            number_of_people = data['number_of_people']

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

            try:
                # Create a new Checkout Session for the order
                session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    line_items=line_items,
                    mode='payment',
                    success_url='https://example.com/success',
                    cancel_url='https://example.com/cancel',
                )

                # Add the payment intent id to the reservation
                reservation = Reservation.objects.get(id=data['reservation'])
                reservation.payment_intent_id = session.payment_intent

                return Response({'id': session.id}, status=status.HTTP_200_OK)

            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
