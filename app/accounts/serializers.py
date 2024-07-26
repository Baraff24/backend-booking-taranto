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


class StructureSerializer(serializers.ModelSerializer):
    """
    Serializer for the Structure model
    """

    class Meta:
        model = Structure
        fields = '__all__'


class RoomSerializer(serializers.ModelSerializer):
    """
    Serializer for the Room model
    """

    class Meta:
        model = Room
        fields = '__all__'


class ReservationSerializer(serializers.ModelSerializer):
    """
    Serializer for the Reservation model
    """

    class Meta:
        model = Reservation
        fields = '__all__'

    def validate(self, data):
        """
        Validate that check-in date is before check-out date
        """
        if data['check_in'] >= data['check_out']:
            raise serializers.ValidationError("Check-in date must be before check-out date.")
        return data


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


class PaymentIntentSerializer(serializers.Serializer):
    """
    Serializer for the payment intent information
    """
    amount = serializers.FloatField(
        min_value=0,
        help_text="The amount to pay in the selected currency",
        required=True
    )
    currency = serializers.CharField(max_length=3, default='eur')
