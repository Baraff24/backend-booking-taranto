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

# CATEGORY_CHOICES VALUES
TIPO_ALLOGGIATO = 'tipo_alloggiato'
COMUNE_DI_NASCITA = 'comune_di_nascita'
STATO_NASCITA = 'stato_di_nascita'
CITTADINANZA = 'cittadinanza'
TIPO_DOCUMENTO = 'tipo_documento'
LUOGO_RILASCIO_DOCUMENTO = 'luogo_rilascio_documento'

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

CATEGORY_CHOICES = (
    (TIPO_ALLOGGIATO, 'Tipo Alloggiato'),
    (COMUNE_DI_NASCITA, 'Comune di Nascita'),
    (STATO_NASCITA, 'Stato di Nascita'),
    (CITTADINANZA, 'Cittadinanza'),
    (TIPO_DOCUMENTO, 'Tipo Documento'),
    (LUOGO_RILASCIO_DOCUMENTO, 'Luogo Rilascio Documento'),
)
