"""
This file contains the constants used in the accounts app.
"""

# URL of the SOAP service for Alloggiati Web
ALLOGGIATI_WEB_URL = 'https://alloggiatiweb.poliziadistato.it/service/service.asmx'

# STATUS_CHOICES VALUES
COMPLETE = 'COMPLETE'
PENDING_COMPLETE_DATA = 'PENDING_EXTRA_DATA'

# TYPE VALUES
CUSTOMER = 'CUSTOMER'
ADMIN = 'ADMIN'

# ROOM_STATUS VALUES
AVAILABLE = 'AVAILABLE'
UNAVAILABLE = 'UNAVAILABLE'

# STATUS_RESERVATION VALUES
UNPAID = 'UNPAID'
PAID = 'PAID'
CANCELED = 'CANCELED'

STATUS_CHOICES = (
    (COMPLETE, 'Complete'),
    (PENDING_COMPLETE_DATA, 'Pending Complete Data'),
)


TYPE_VALUES = (
    (CUSTOMER, 'Customer'),
    (ADMIN, 'Admin'),
)

ROOM_STATUS = (
    (AVAILABLE, 'Available'),
    (UNAVAILABLE, 'Unavailable'),
)

STATUS_RESERVATION = (
    (UNPAID, 'Unpaid'),
    (PAID, 'Paid'),
    (CANCELED, 'Canceled'),
)
