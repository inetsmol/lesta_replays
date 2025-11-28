import json
import os
import requests
from django.core.files.base import ContentFile
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from news.models import News

class Command(BaseCommand):
    help = 'Load news from a JSON file'

    def add_arguments(self, parser):
        parser.add_argument('file_path', nargs='?', default='news.json', type=str)

    def handle(self, *args, **options):
        file_path = options['file_path']

        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'File "{file_path}" does not exist.'))
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                self.stdout.write(self.style.ERROR(f'Error decoding JSON: {e}'))
                return

        count_created = 0
        count_updated = 0

        for item in data:
            link = item.get('url')
            if not link:
                self.stdout.write(self.style.WARNING(f'Skipping item without URL: {item}'))
                continue

            # Parse date
            pub_date_str = item.get('pubDate')
            published_at = None
            if pub_date_str:
                try:
                    # Assuming format YYYY-MM-DD
                    dt = datetime.strptime(pub_date_str, '%Y-%m-%d')
                    published_at = timezone.make_aware(dt)
                except ValueError:
                    self.stdout.write(self.style.WARNING(f'Could not parse date "{pub_date_str}" for news "{item.get("title")}"'))

            news_data = {
                'title': item.get('title'),
                'text': item.get('summary', ''), # Map summary to text
                'category': item.get('category'),
                'published_at': published_at,
                'is_active': True,
            }

            news, created = News.objects.update_or_create(
                link=link,
                defaults=news_data
            )
            
            # Download image
            image_url = item.get('imageUrl')
            if image_url:
                try:
                    response = requests.get(image_url, timeout=10)
                    if response.status_code == 200:
                        file_name = image_url.split('/')[-1]
                        news.image.save(file_name, ContentFile(response.content), save=True)
                    else:
                        self.stdout.write(self.style.WARNING(f'Failed to download image from {image_url}'))
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Error downloading image from {image_url}: {e}'))

            if created:
                count_created += 1
                self.stdout.write(self.style.SUCCESS(f'Created news: {news.title}'))
            else:
                count_updated += 1
                self.stdout.write(f'Updated news: {news.title}')

        self.stdout.write(self.style.SUCCESS(f'Done. Created: {count_created}, Updated: {count_updated}'))
