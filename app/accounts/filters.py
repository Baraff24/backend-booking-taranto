from django_filters import rest_framework as filters
from .models import Reservation


class ReservationFilter(filters.FilterSet):
    created_at_gte = filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_at_lte = filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = Reservation
        fields = ['user', 'room', 'check_in', 'check_out', 'created_at_gte', 'created_at_lte']
