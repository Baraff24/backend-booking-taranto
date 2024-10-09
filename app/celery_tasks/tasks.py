"""
Write your celery tasks here...
"""
import logging

from celery import shared_task
from django.utils import timezone

from accounts.models import Reservation
from accounts.functions import send_self_checkin_mail, send_self_checkin_whatsapp_message

logger = logging.getLogger(__name__)


@shared_task
def send_self_checkin_reminders():
    logger.info("Task send_self_checkin_reminders started")

    today = timezone.now().date()
    logger.info(f"Checking for reservations with check-in date: {today}")

    # Verify how many reservations are scheduled for today
    reservations = Reservation.objects.filter(check_in=today)
    reservation_count = reservations.count()
    logger.info(f"Found {reservation_count} reservations for today")

    if reservation_count == 0:
        logger.warning("No reservations found for today's date.")

    for reservation in reservations:
        logger.info(f"Processing reservation for user: {reservation.user.email}")

        try:
            # Log before sending email
            logger.info(f"Sending self check-in email to {reservation.email_on_reservation}")
            send_self_checkin_mail(reservation)

            # Log before sending WhatsApp message
            logger.info(f"Sending WhatsApp self check-in message to {reservation.phone_on_reservation}")
            send_self_checkin_whatsapp_message(reservation)

            logger.info(f"Successfully sent check-in reminders to {reservation.user.email}")

        except Exception as e:
            # Error log if any exception occurs
            logger.error(f"Error sending self check-in reminder to {reservation.user.email}: {e}")

    logger.info("Task send_self_checkin_reminders completed")
