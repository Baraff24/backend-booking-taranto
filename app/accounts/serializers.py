"""
Serializers for the accounts app.
"""
from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .constants import CANCELED
from .models import (User, Structure, Room, Reservation, Discount,
                     StructureImage, RoomImage, UserAllogiatiWeb,
                     TokenInfoAllogiatiWeb, CheckinCategoryChoices)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom token serializer to use custom claims.
    Use email instead of username for authentication.
    """

    # Specify the field to use for authentication
    username_field = 'email'

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        token['email'] = user.email

        return token

    def validate(self, attrs):
        # Override the default method to use email instead of username
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            user = authenticate(
                request=self.context.get('request'),
                username=email,
                password=password
            )

            if not user:
                raise serializers.ValidationError('Invalid credentials')

            attrs['user'] = user
            return super().validate(attrs)
        else:
            raise serializers.ValidationError('Must include "email" and "password".')


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for the User model.
    """

    class Meta:
        model = User
        fields = '__all__'


class CompleteProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for completing a user's profile.
    """

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'telephone', 'has_accepted_terms']


class EmailSerializer(serializers.Serializer):
    """
    Serializer for the email field.
    """
    email = serializers.EmailField()


class StructureImageSerializer(serializers.ModelSerializer):
    """
    Serializer for the StructureImage model.
    """
    image = serializers.SerializerMethodField()

    class Meta:
        model = StructureImage
        fields = ['id', 'image', 'alt', 'structure']

    def get_image(self, obj):
        request = self.context.get('request', None)
        image_url = obj.image.url
        if request:
            return request.build_absolute_uri(image_url)
        return image_url


class StructureSerializer(serializers.ModelSerializer):
    """
    Serializer for the Structure model.
    """
    images = StructureImageSerializer(many=True, required=False)

    class Meta:
        model = Structure
        fields = ['id', 'name', 'description', 'address', 'cis', 'images']

    def create(self, validated_data):
        images_data = validated_data.pop('images', [])
        structure = Structure.objects.create(**validated_data)
        StructureImage.objects.bulk_create(
            [StructureImage(structure=structure, **image_data) for image_data in images_data]
        )
        return structure

    def update(self, instance, validated_data):
        images_data = validated_data.pop('images', [])
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        StructureImage.objects.filter(structure=instance).delete()
        StructureImage.objects.bulk_create(
            [StructureImage(structure=instance, **image_data) for image_data in images_data]
        )
        return instance


class RoomImageSerializer(serializers.ModelSerializer):
    """
    Serializer for the StructureImage model.
    """
    image = serializers.SerializerMethodField()

    class Meta:
        model = RoomImage
        fields = ['id', 'image', 'alt', 'room']

    def get_image(self, obj):
        request = self.context.get('request', None)
        image_url = obj.image.url
        if request:
            return request.build_absolute_uri(image_url)
        return image_url


class RoomSerializer(serializers.ModelSerializer):
    """
    Serializer for the Room model.
    """
    images = RoomImageSerializer(many=True, required=False)

    class Meta:
        model = Room
        fields = ['id', 'name', 'room_status', 'services',
                  'cost_per_night', 'max_people', 'structure', 'calendar_id', 'images']
        read_only_fields = ['id', 'calendar_id']

    @staticmethod
    def validate_cost_per_night(value):
        """
        Ensure that the cost_per_night is greater than 0.
        """
        if value <= 0:
            raise serializers.ValidationError("Cost per night must be greater than 0.")
        return value


class StructureRoomSerializer(serializers.ModelSerializer):
    """
    Serializer for the Structure model with associated rooms.
    """
    rooms = RoomSerializer(many=True, read_only=True)
    images = StructureImageSerializer(many=True, read_only=True)

    class Meta:
        model = Structure
        fields = ['id', 'name', 'description', 'address', 'cis', 'rooms', 'images']


class AvailableRoomsForDatesSerializer(serializers.ModelSerializer):
    """
    Serializer for rooms available for specific dates.
    """
    structure = StructureSerializer(read_only=True)

    class Meta:
        model = Room
        fields = ['id', 'name', 'room_status', 'services', 'cost_per_night', 'max_people', 'structure']


class DiscountSerializer(serializers.ModelSerializer):
    """
    Serializer for the Discount model.
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
    Serializer for the Reservation model.
    """
    user = UserSerializer(read_only=True)
    room_id = serializers.IntegerField(write_only=True)
    room = RoomSerializer(read_only=True)
    discount = DiscountSerializer(read_only=True)

    class Meta:
        model = Reservation
        fields = [
            'id', 'check_in', 'check_out', 'number_of_people', 'discount',
            'first_name_on_reservation', 'last_name_on_reservation',
            'email_on_reservation', 'phone_on_reservation', 'coupon_used',
            'user', 'room', 'room_id', 'total_cost', 'reservation_id',
            'payment_intent_id', 'status', 'created_at'
        ]
        read_only_fields = ['user', 'room', 'total_cost', 'reservation_id', 'payment_intent_id', 'status', 'created_at']

    def validate(self, data):
        """
        Validate that check-in date is before check-out date
        """
        if data['check_in'] >= data['check_out']:
            raise serializers.ValidationError("Check-in date must be before check-out date.")

        # Validate room existence
        room = get_object_or_404(Room, id=data['room_id'])

        # Validate the number of people
        if data['number_of_people'] > room.max_people:
            raise serializers.ValidationError(
                "Number of people must be less than or equal to the maximum number of people allowed in the room."
            )

        # Validate the maximum length of stay
        max_nights = 30
        num_nights = (data['check_out'] - data['check_in']).days
        if num_nights > max_nights:
            raise serializers.ValidationError(f"The maximum stay is {max_nights} nights.")

        # Attach the room to the data for further use
        data['room'] = room
        return data


class CancelReservationSerializer(serializers.Serializer):
    """
    Serializer for canceling a reservation.
    """
    reservation_id = serializers.UUIDField(required=True)

    @staticmethod
    def validate_reservation_id(value):
        """
        Verify that the reservation exists and has not been canceled
        """

        reservation = get_object_or_404(Reservation, reservation_id__exact=value)

        if reservation.status == CANCELED:
            raise serializers.ValidationError("This reservation has already been canceled.")

        return value


class ReservationCalendarSerializer(serializers.ModelSerializer):
    """
    Serializer for displaying reservation details in a calendar.
    """
    room = RoomSerializer(read_only=True)

    class Meta:
        model = Reservation
        fields = ['id', 'check_in', 'check_out', 'number_of_people', 'total_cost',
                  'first_name_on_reservation', 'last_name_on_reservation',
                  'email_on_reservation', 'phone_on_reservation', 'status', 'room']


class CalculateDiscountSerializer(serializers.Serializer):
    """
    Serializer for calculating the discount for a reservation.
    """
    reservation = serializers.UUIDField(required=True)
    discount_code = serializers.CharField(max_length=50, required=True)


class CreateCheckoutSessionSerializer(serializers.Serializer):
    """
    Serializer for creating a Stripe checkout session.
    """
    reservation_id = serializers.UUIDField(required=True)

    def get_reservation(self):
        """
        Helper method to return the reservation instance after validation.
        """
        return get_object_or_404(Reservation, reservation_id__exact=self.validated_data['reservation_id'])


class UserAllogiatiWebSerializer(serializers.ModelSerializer):
    """
    Serializer for the UserAllogiatiWeb model.
    """

    class Meta:
        model = UserAllogiatiWeb
        fields = '__all__'


class TokenInfoAllogiatiWebSerializer(serializers.ModelSerializer):
    """
    Serializer for the TokenInfoAllogiatiWeb model.
    """

    class Meta:
        model = TokenInfoAllogiatiWeb
        fields = '__all__'


class AuthenticationTestSerializer(serializers.Serializer):
    structure_id = serializers.IntegerField(required=True)


class SchedinaSerializer(serializers.Serializer):
    """
    Serializer for handling individual guest registration forms (Schedina).
    This serializer will create a single string representing the entire schedina.
    """
    tipo_alloggiati = serializers.CharField(max_length=2)
    data_arrivo = serializers.DateField(input_formats=['%d/%m/%Y'])
    numero_giorni_permanenza = serializers.IntegerField(min_value=1, max_value=30)
    cognome = serializers.CharField(max_length=50)
    nome = serializers.CharField(max_length=30)
    sesso = serializers.ChoiceField(choices=[('1', 'M'), ('2', 'F')])
    data_nascita = serializers.DateField(input_formats=['%d/%m/%Y'])
    comune_nascita = serializers.CharField(max_length=9, required=False, allow_blank=True)
    provincia_nascita = serializers.CharField(max_length=2, required=False, allow_blank=True)
    stato_nascita = serializers.CharField(max_length=9)
    cittadinanza = serializers.CharField(max_length=9)
    tipo_documento = serializers.CharField(max_length=5, required=False, allow_blank=True)
    numero_documento = serializers.CharField(max_length=20, required=False, allow_blank=True)
    luogo_rilascio_documento = serializers.CharField(max_length=9, required=False, allow_blank=True)

    def validate(self, data):
        """
        Override the validate method to apply conditional validation.
        """
        # Conditionally set comune_nascita and provincia_nascita to empty if the guest is Italian
        if data.get('cittadinanza') == "100000100":
            data['comune_nascita'] = ''
            data['provincia_nascita'] = ''

        # Conditionally set tipo_documento and numero_documento to empty for specific guest types
        if data.get('tipo_alloggiati') in ['19', '20']:
            data['tipo_documento'] = ''
            data['numero_documento'] = ''
            data['luogo_rilascio_documento'] = ''

        return data

    def to_representation(self, instance):
        """
        Override the to_representation method to concatenate all fields into a single string.
        """
        try:
            # Format dates as gg/MM/AAAA
            data_arrivo_str = instance['data_arrivo'].strftime('%d/%m/%Y')
            data_nascita_str = instance['data_nascita'].strftime('%d/%m/%Y')

            # Comune and provincia are already conditionally validated in 'validate'
            comune_nascita_str = instance.get('comune_nascita', '').ljust(9)
            provincia_nascita_str = instance.get('provincia_nascita', '').ljust(2)

            tipo_documento_str = instance.get('tipo_documento', '').ljust(5)
            numero_documento_str = instance.get('numero_documento', '').ljust(20)
            luogo_rilascio_documento_str = instance.get('luogo_rilascio_documento', '').ljust(9)

            return (
                f"{instance.get('tipo_alloggiati', '').ljust(2)}"
                f"{data_arrivo_str}"
                f"{str(instance.get('numero_giorni_permanenza', '')).zfill(2)}"
                f"{instance.get('cognome', '').ljust(50)}"
                f"{instance.get('nome', '').ljust(30)}"
                f"{instance.get('sesso', '').ljust(1)}"
                f"{data_nascita_str}"
                f"{comune_nascita_str}"
                f"{provincia_nascita_str}"
                f"{instance.get('stato_nascita', '').ljust(9)}"
                f"{instance.get('cittadinanza', '').ljust(9)}"
                f"{tipo_documento_str}"
                f"{numero_documento_str}"
                f"{luogo_rilascio_documento_str}"
            ).upper()
        except Exception as e:
            print(f"Error in to_representation: {str(e)}")
            raise serializers.ValidationError(f"Error serializing schedina: {str(e)}")


class SendElencoSchedineSerializer(serializers.Serializer):
    """
    Serializer for generating XML and sending it to a DMS.
    """
    utente = serializers.CharField(read_only=True)
    token = serializers.CharField(read_only=True)
    elenco_schedine = SchedinaSerializer(many=True)
    structure_id = serializers.IntegerField()

    @staticmethod
    def validate_elenco_schedine(value):
        if not value:
            raise serializers.ValidationError("Elenco delle Schedine non può essere vuoto.")
        return value

    def validate(self, data):
        # Extract structure_id from the validated data
        structure_id = data.get('structure_id')

        try:
            # Get the user information from UserAllogiatiWeb
            user_info = UserAllogiatiWeb.objects.get(structure_id=structure_id)
            data['utente'] = user_info.allogiati_web_user
        except UserAllogiatiWeb.DoesNotExist:
            raise serializers.ValidationError("Utente associated with the structure ID not found.")

        # Retrieve or generate a valid token
        token_info = TokenInfoAllogiatiWeb.objects.filter(expires__gt=timezone.now()).first()
        if not token_info:
            # Lazy import to avoid circular imports
            from .functions import get_or_create_token
            # Generate a new token if none exists or the existing one is expired
            token_info = get_or_create_token(structure_id)

        # Ensure the token is valid before proceeding
        if not token_info or not token_info.token:
            raise serializers.ValidationError("No valid token found. Please generate a new one.")

        data['token'] = token_info.token

        # Additional cross-field validations can go here if needed
        return data


# Serializer for Puglia DMS
class ComponenteSerializer(serializers.Serializer):
    codice_cliente_sr = serializers.CharField(max_length=20)
    sesso = serializers.ChoiceField(choices=[('M', 'Male'), ('F', 'Female')])
    cittadinanza = serializers.CharField(max_length=9)
    paese_residenza = serializers.CharField(max_length=9, required=False)
    comune_residenza = serializers.CharField(max_length=9, required=False)
    occupazione_posto_letto = serializers.ChoiceField(choices=[('si', 'Yes'), ('no', 'No')])
    eta = serializers.IntegerField(min_value=0)

# Serializer for Puglia DMS
class ArrivoSerializer(serializers.Serializer):
    codice_cliente_sr = serializers.CharField(max_length=20)
    sesso = serializers.ChoiceField(choices=[('M', 'Male'), ('F', 'Female')])
    cittadinanza = serializers.CharField(max_length=9)
    comune_residenza = serializers.CharField(max_length=9, required=False)
    occupazione_postoletto = serializers.ChoiceField(choices=[('si', 'Yes'), ('no', 'No')])
    dayuse = serializers.ChoiceField(choices=[('si', 'Yes'), ('no', 'No')])
    tipologia_alloggiato = serializers.CharField(max_length=2)
    eta = serializers.IntegerField(min_value=0)
    durata_soggiorno = serializers.IntegerField(min_value=1, required=False)
    mezzo_trasporto_arrivo = serializers.CharField(max_length=50, required=False)
    mezzo_trasporto_movimento = serializers.CharField(max_length=50, required=False)
    motivazioni_viaggio = serializers.CharField(max_length=50, required=False)
    componenti = ComponenteSerializer(many=True, required=False)

# Serializer for Puglia DMS
class MovimentoSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=[('MP', 'Movement')])
    data = serializers.DateField(format='%Y-%m-%d')
    arrivi = ArrivoSerializer(many=True)
    partenze = serializers.ListField(
        child=serializers.CharField(max_length=20), required=False
    )
    dati_struttura = serializers.DictField(child=serializers.IntegerField(), required=False)



class CheckinCategoryChoicesSerializer(serializers.ModelSerializer):
    """
    Serializer for the CheckinCategoryChoices model.
    """

    class Meta:
        model = CheckinCategoryChoices
        fields = '__all__'


class WhatsAppMessageSerializer(serializers.Serializer):
    user_phone_number = serializers.CharField(max_length=15)
    message = serializers.CharField(max_length=4096)  # WhatsApp messages have a 4096 character limit


class SendWhatsAppToAllUsersSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=4096)  # WhatsApp messages have a 4096 character limit
