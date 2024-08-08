"""
Serializers for the accounts app.
"""
from django.utils import timezone
from rest_framework import serializers
from .models import User, Structure, Room, Reservation, Discount, StructureImage


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


class StructureImageSerializer(serializers.ModelSerializer):
    """
    Serializer for the StructureImage model
    """

    class Meta:
        model = StructureImage
        fields = ['id', 'image', 'alt', 'structure']


class StructureSerializer(serializers.ModelSerializer):
    """
    Serializer for the Structure model
    """
    images = StructureImageSerializer(many=True, required=False)

    class Meta:
        model = Structure
        fields = ['id', 'name', 'description', 'address', 'cis', 'images']

    def create(self, validated_data):
        images_data = validated_data.pop('images', [])
        structure = Structure.objects.create(**validated_data)
        for image_data in images_data:
            StructureImage.objects.create(structure=structure, **image_data)
        return structure

    def update(self, instance, validated_data):
        images_data = validated_data.pop('images', [])
        instance.name = validated_data.get('name', instance.name)
        instance.description = validated_data.get('description', instance.description)
        instance.address = validated_data.get('address', instance.address)
        instance.cis = validated_data.get('cis', instance.cis)
        instance.save()

        for image_data in images_data:
            StructureImage.objects.update_or_create(structure=instance, **image_data)

        return instance


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
    structure_images = StructureImageSerializer(many=True, read_only=True)

    class Meta:
        model = Structure
        fields = ['id', 'name', 'description', 'address', 'cis', 'rooms', 'structure_images']


class AvailableRoomsForDatesSerializer(serializers.ModelSerializer):
    """
    Serializer for the AvailableRoomForDates API
    """
    structure = StructureSerializer(read_only=True)

    class Meta:
        model = Room
        fields = ['id', 'name', 'room_status', 'services', 'cost_per_night', 'max_people', 'structure']


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
        read_only_fields = ['user', 'room', 'total_cost', 'reservation_id', 'payment_intent_id', 'status', 'created_at']

    def validate(self, data):
        """
        Validate that check-in date is before check-out date
        """
        if data['check_in'] >= data['check_out']:
            raise serializers.ValidationError("Check-in date must be before check-out date.")
        if data['number_of_people'] > data['room'].max_people:
            raise serializers.ValidationError(
                "Number of people must be less than or equal to the maximum number of people allowed in the room.")
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
                  'email_on_reservation', 'phone_on_reservation', 'status', 'room']


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


class SchedinaSerializer(serializers.Serializer):
    tipo_alloggiati = serializers.CharField(max_length=2)
    data_arrivo = serializers.DateField(input_formats=['%d/%m/%Y'])
    numero_giorni_permanenza = serializers.IntegerField(min_value=1, max_value=30)
    cognome = serializers.CharField(max_length=50)
    nome = serializers.CharField(max_length=30)
    sesso = serializers.ChoiceField(choices=[('1', 'M'), ('2', 'F')])
    data_nascita = serializers.DateField(input_formats=['%d/%m/%Y'])
    comune_nascita = serializers.CharField(max_length=9)
    provincia_nascita = serializers.CharField(max_length=2)
    stato_nascita = serializers.CharField(max_length=9)
    cittadinanza = serializers.CharField(max_length=9)
    tipo_documento = serializers.CharField(max_length=5)
    numero_documento = serializers.CharField(max_length=20)
    luogo_rilascio_documento = serializers.CharField(max_length=9)
    id_appartamento = serializers.CharField(max_length=6)


class GenerateXmlAndSendToDmsSerializer(serializers.Serializer):
    utente = serializers.CharField(max_length=100)
    token = serializers.CharField(max_length=255)
    elenco_schedine = SchedinaSerializer(many=True)
    id_appartamento = serializers.IntegerField()

    @staticmethod
    def validate_elenco_schedine(value):
        if not value:
            raise serializers.ValidationError("Elenco delle Schedine non può essere vuoto.")
        return value

    def validate(self, data):
        # Custom validations if needed
        return data
