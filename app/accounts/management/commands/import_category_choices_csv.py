import csv
from django.core.management.base import BaseCommand

from accounts.constants import CATEGORY_CHOICES
from accounts.models import CheckinCategoryChoices


class Command(BaseCommand):
    help = 'Import choices from CSV files'

    def add_arguments(self, parser):
        parser.add_argument('category', type=str,
                            help="The category of the data being imported (e.g., tipo_alloggiato, comune_nascita, etc.)")
        parser.add_argument('file_path', type=str, help="The path to the CSV file.")

    def handle(self, *args, **options):
        category = options['category']
        file_path = options['file_path']

        if category not in dict(CATEGORY_CHOICES):
            self.stdout.write(self.style.ERROR('Invalid category provided.'))
            return

        # Check if the data for this category already exists
        if CheckinCategoryChoices.objects.filter(category=category).exists():
            self.stdout.write(self.style.WARNING(f'Data for category "{category}" already exists. Skipping import.'))
            return

        new_entries = []
        with open(file_path, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:

                # Combine 'Descrizione' and 'Provincia' with a hyphen, handling missing values gracefully
                descrizione = row['Descrizione']
                provincia = row.get('Provincia', '').strip()
                if provincia:
                    descrizione = f"{descrizione} - {provincia}"

                new_entries.append(CheckinCategoryChoices(
                    category=category,
                    descrizione=descrizione,
                    codice=row.get('Codice', '')
                ))

        if new_entries:
            CheckinCategoryChoices.objects.bulk_create(new_entries)
            self.stdout.write(
                self.style.SUCCESS(f'Choices for category "{category}" imported successfully from {file_path}'))
        else:
            self.stdout.write(self.style.WARNING(f'No new entries found in the file {file_path}.'))
