"""
Write your celery tasks here...
"""
from celery import shared_task
from django.utils import timezone

from accounts.models import Reservation
from accounts.functions import send_self_checkin_mail, send_self_checkin_whatsapp_message


@shared_task
def send_self_checkin_reminders():
    """
    Send reminders to users that have not checked in yet.
    """
    today = timezone.now().date()
    reservations = Reservation.objects.filter(check_in=today)

    for reservation in reservations:
        try:

            send_self_checkin_mail(reservation)

            send_self_checkin_whatsapp_message(reservation)

        except Exception as e:
            print(f'Error sending self checkin reminder to {reservation.user.email}: {e}')
