from django.conf import settings
from django.db import models


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    lesta_nickname = models.CharField("Ник в игре", max_length=64)
    clan = models.CharField("Клан", max_length=64, blank=True)

    def __str__(self):
        return f"{self.user.username} ({self.lesta_nickname})"
