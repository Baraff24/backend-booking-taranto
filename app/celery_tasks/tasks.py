from celery import shared_task
from django.utils import timezone

from accounts.constants import UNPAID
from accounts.models import Reservation


@shared_task
def delete_expired_reservations():
    """
    Delete all the reservations that have expired.
    """
    reservations = Reservation.objects.filter(status=UNPAID, expires_at__lt=timezone.now())
    reservations.delete()
