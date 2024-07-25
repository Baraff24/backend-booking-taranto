"""
Serializers for the accounts app.
"""
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for the User model
    """
    class Meta:
        """
        Meta class for the UserSerializer
        """
        model = User
        fields = '__all__'


class CompleteProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for the User model
    """
    class Meta:
        """
        Meta class for the CompleteProfileSerializer
        """
        model = User
        fields = ['first_name', 'last_name', 'telephone']
