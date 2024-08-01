"""
Serializers for the accounts app.
"""

from rest_framework import serializers
from .models import User, Structure, Room, Reservation, Discount


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for the User model
    """

    class Meta:
        model = User
        fields = '__all__'


class CompleteProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for the User model to complete profile
    """

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'telephone']


class EmailSerializer(serializers.Serializer):
    """
    Serializer for the email field
    """
    email = serializers.EmailField()


class StructureSerializer(serializers.ModelSerializer):
    """
    Serializer for the Structure model
    """

    class Meta:
        model = Structure
        fields = ['id', 'name', 'description', 'address', 'cis']


class RoomSerializer(serializers.ModelSerializer):
    """
    Serializer for the Room model
    """

    class Meta:
        model = Room
        fields = ['id', 'name', 'room_status', 'services', 'cost_per_night', 'max_people', 'structure']


class StructureRoomSerializer(serializers.ModelSerializer):
    """
    Serializer for the Structure model
    """
    rooms = RoomSerializer(many=True, read_only=True)

    class Meta:
        model = Structure
        fields = ['id', 'name', 'description', 'address', 'cis', 'rooms']


class DiscountSerializer(serializers.ModelSerializer):
    """
    Serializer for the Discount model
    """

    class Meta:
        model = Discount
        fields = '__all__'

    def validate(self, attrs):
        """
        Validate that the discount start date is before the end date
        """
        if attrs['start_date'] >= attrs['end_date']:
            raise serializers.ValidationError("Start date must be before end date.")
        return attrs


class ReservationSerializer(serializers.ModelSerializer):
    """
    Serializer for the Reservation model
    """
    user = UserSerializer(read_only=True)
    room = RoomSerializer(read_only=True)
    discount = DiscountSerializer(read_only=True)

    class Meta:
        model = Reservation
        fields = ['id', 'check_in', 'check_out', 'number_of_people', 'discount',
                  'first_name_on_reservation', 'last_name_on_reservation',
                  'email_on_reservation', 'phone_on_reservation', 'coupon_used', 'user', 'room']
        read_only_fields = ['user', 'room', 'total_cost', 'reservation_id', 'payment_intent_id', 'paid']

    def validate(self, data):
        """
        Validate that check-in date is before check-out date
        """
        if data['check_in'] >= data['check_out']:
            raise serializers.ValidationError("Check-in date must be before check-out date.")
        if data['number_of_people'] > data['room'].max_people:
            raise serializers.ValidationError("Number of people must be less than or equal to the maximum number of people allowed in the room.")
        return data


class ReservationCalendarSerializer(serializers.ModelSerializer):
    """
    Serializer for the Reservation model for the calendar
    """
    room = RoomSerializer(read_only=True)

    class Meta:
        model = Reservation
        fields = ['id', 'check_in', 'check_out', 'number_of_people', 'total_cost',
                  'first_name_on_reservation', 'last_name_on_reservation',
                  'email_on_reservation', 'phone_on_reservation', 'room']


class CreateCheckoutSessionSerializer(serializers.Serializer):
    room = serializers.IntegerField()
    reservation = serializers.IntegerField()
    number_of_people = serializers.IntegerField()

    @staticmethod
    def validate_room(value):
        try:
            Room.objects.get(id=value)
        except Room.DoesNotExist:
            raise serializers.ValidationError("Room does not exist.")
        return value

    @staticmethod
    def validate_reservation(value):
        try:
            Reservation.objects.get(id=value)
        except Reservation.DoesNotExist:
            raise serializers.ValidationError("Reservation does not exist.")
        return value

    @staticmethod
    def validate_number_of_people(value):
        if value <= 0:
            raise serializers.ValidationError("Number of people must be a positive integer.")
        return value
