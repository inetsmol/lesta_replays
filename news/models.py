# news/models.py
from django.db import models
from django.urls import reverse


class News(models.Model):
    """
    Модель для новостей на главной странице.
    """
    title = models.CharField(
        "Заголовок",
        max_length=200,
        help_text="Заголовок новости"
    )
    text = models.TextField(
        "Текст",
        help_text="Текст новости"
    )
    image = models.ImageField(
        "Изображение",
        upload_to='news/',
        null=True,
        blank=True,
        help_text="Изображение для слайдера"
    )
    created_at = models.DateTimeField(
        "Дата создания",
        auto_now_add=True
    )
    is_active = models.BooleanField(
        "Активна",
        default=True,
        help_text="Отображать ли новость на сайте"
    )

    class Meta:
        verbose_name = "Новость"
        verbose_name_plural = "Новости"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("news_detail", kwargs={"pk": self.pk})
