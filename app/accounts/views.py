"""
This module contains the views of the accounts app.
"""
from django.core.exceptions import ObjectDoesNotExist
from django.utils.decorators import method_decorator
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, filters, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .constants import PENDING_COMPLETE_DATA, COMPLETE
from .functions import is_active
from .models import User, Structure, Room, Reservation, Discount
from .serializers import UserSerializer, CompleteProfileSerializer, StructureSerializer, RoomSerializer, \
    ReservationSerializer, DiscountSerializer


class UsersListAPI(APIView):
    """
    List all users or create a new user
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'type']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering_fields = ['username', 'email', 'first_name', 'last_name']

    @method_decorator(is_active)
    def get(self, request):
        """
        Get all users if the user is a superuser
        """
        user = request.user
        obj = User.objects.all()
        serializer = self.serializer_class(obj, many=True)
        if user.is_superuser:
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(status=status.HTTP_403_FORBIDDEN)


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
        if obj.id == request.user.id or request.user.is_superuser:
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
        if obj.id == request.user.id or request.user.is_superuser:
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


class StructureViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing structure instances.
    """
    serializer_class = StructureSerializer
    queryset = Structure.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['name', 'address']
    search_fields = ['name', 'address', 'description']
    ordering_fields = ['name', 'address']


class RoomViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing room instances.
    """
    serializer_class = RoomSerializer
    queryset = Room.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['structure', 'cost_per_night', 'max_people']
    search_fields = ['name', 'services']
    ordering_fields = ['name', 'cost_per_night', 'max_people']


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


class DiscountViewSet(viewsets.ModelViewSet):
    """
    A viewset for viewing and editing discount instances.
    """
    serializer_class = DiscountSerializer
    queryset = Discount.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['code', 'start_date', 'end_date']
    search_fields = ['code', 'description']
    ordering_fields = ['code', 'discount', 'start_date', 'end_date']