#!/usr/bin/env bash

# This script is used to start the docker container
python manage.py makemigrations
echo -e "\e[34m >>> Migrating changes \e[97m"
python manage.py migrate
echo -e "\e[32m >>> migration completed \e[97m"
echo -e "\e[34m >>> Collecting Static files \e[97m"
python manage.py collectstatic --noinput
echo -e "\e[32m >>> Static files collect completed \e[97m"

echo -e "\e[34m >>> Tests for accounts app \e[97m"
python manage.py test accounts
echo -e "\e[32m >>> Tests completed \e[97m"

echo -e "\e[34m >>> Adding category choices for the check-in process \e[97m"
python manage.py import_category_choices_csv comune_di_nascita initial_data/category_choices_csv/comuni.csv
python manage.py import_category_choices_csv tipo_documento initial_data/category_choices_csv/documenti.csv
python manage.py import_category_choices_csv stato_di_nascita initial_data/category_choices_csv/stati.csv
python manage.py import_category_choices_csv tipo_alloggiato initial_data/category_choices_csv/tipo_alloggiato.csv

gunicorn core.asgi --bind 0.0.0.0:8000 -k uvicorn.workers.UvicornWorker --timeout 20 --workers=2
