"""
Template tags для работы с WebP изображениями.

Автоматически использует WebP версию изображения если она существует,
с fallback на оригинальный формат (PNG/JPG).

Usage:
    {% load webp_tags %}

    {# Простой вариант #}
    {% webp_image 'path/to/image.png' 'Alt text' %}

    {# С дополнительными атрибутами #}
    {% webp_image 'path/to/image.jpg' 'Alt text' class='img-fluid' loading='lazy' %}

    {# Только URL (без тега <picture>) #}
    {% webp_url 'path/to/image.png' %}
"""

from django import template
from django.contrib.staticfiles.storage import staticfiles_storage
from django.utils.safestring import mark_safe
from pathlib import Path

register = template.Library()


@register.simple_tag
def webp_url(image_path):
    """
    Вернуть URL WebP версии изображения если она существует.

    Args:
        image_path: Путь к изображению относительно STATIC_ROOT

    Returns:
        str: URL WebP версии или оригинального изображения
    """
    # Получаем путь к WebP версии
    webp_path = str(Path(image_path).with_suffix('.webp'))

    # Проверяем существует ли WebP файл
    try:
        webp_url = staticfiles_storage.url(webp_path)
        # Проверяем существование файла
        if staticfiles_storage.exists(webp_path):
            return webp_url
    except Exception:
        pass

    # Fallback на оригинальный файл
    return staticfiles_storage.url(image_path)


@register.simple_tag
def webp_image(image_path, alt_text='', **kwargs):
    """
    Создать <picture> тег с WebP и fallback на оригинальный формат.

    Args:
        image_path: Путь к изображению относительно STATIC_ROOT
        alt_text: Alt текст для изображения
        **kwargs: Дополнительные HTML атрибуты (class, loading, etc.)

    Returns:
        str: HTML тег <picture> с WebP и fallback

    Example:
        {% webp_image 'images/hero.png' 'Hero image' class='img-fluid' loading='lazy' %}

        Результат:
        <picture>
            <source srcset="/static/images/hero.webp" type="image/webp">
            <img src="/static/images/hero.png" alt="Hero image" class="img-fluid" loading="lazy">
        </picture>
    """
    # Получаем URL оригинального изображения
    original_url = staticfiles_storage.url(image_path)

    # Получаем путь к WebP версии
    webp_path = str(Path(image_path).with_suffix('.webp'))

    # Проверяем существует ли WebP файл
    has_webp = False
    webp_url = ''

    try:
        webp_url = staticfiles_storage.url(webp_path)
        if staticfiles_storage.exists(webp_path):
            has_webp = True
    except Exception:
        pass

    # Формируем HTML атрибуты
    attrs = []
    for key, value in kwargs.items():
        # Заменяем подчеркивания на дефисы (для data_src -> data-src)
        key = key.replace('_', '-')
        attrs.append(f'{key}="{value}"')

    attrs_str = ' ' + ' '.join(attrs) if attrs else ''

    # Если WebP существует, используем <picture>
    if has_webp:
        html = f'''<picture>
    <source srcset="{webp_url}" type="image/webp">
    <img src="{original_url}" alt="{alt_text}"{attrs_str}>
</picture>'''
    else:
        # Fallback на обычный <img>
        html = f'<img src="{original_url}" alt="{alt_text}"{attrs_str}>'

    return mark_safe(html)


@register.simple_tag
def webp_background(image_path):
    """
    Создать inline стиль для background-image с WebP и fallback.

    Args:
        image_path: Путь к изображению относительно STATIC_ROOT

    Returns:
        str: CSS стиль для background-image

    Example:
        <div {% webp_background 'images/bg.jpg' %}>...</div>

        Результат (если WebP существует):
        <div style="background-image: url('/static/images/bg.webp')">...</div>

        Результат (если WebP не существует):
        <div style="background-image: url('/static/images/bg.jpg')">...</div>

    Note:
        Для полноценного fallback в CSS используйте:
        .element {
            background-image: url('bg.jpg');
            background-image: url('bg.webp');
        }
    """
    url = webp_url(image_path)
    return mark_safe(f'style="background-image: url(\'{url}\')"')


@register.filter
def has_webp(image_path):
    """
    Проверить существует ли WebP версия изображения.

    Args:
        image_path: Путь к изображению относительно STATIC_ROOT

    Returns:
        bool: True если WebP версия существует

    Example:
        {% if 'images/photo.png'|has_webp %}
            <p>WebP version available</p>
        {% endif %}
    """
    webp_path = str(Path(image_path).with_suffix('.webp'))

    try:
        return staticfiles_storage.exists(webp_path)
    except Exception:
        return False
