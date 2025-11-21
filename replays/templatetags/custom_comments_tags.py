# replays/templatetags/custom_comments_tags.py
from django import template
from django_comments_xtd import get_form

register = template.Library()


@register.inclusion_tag('comments/form.html', takes_context=True)
def custom_render_comment_form(context, obj):
    """
    Renders the comment form, passing the user from the context to the form's __init__.
    """
    if obj:
        user = context.get('user')
        form_class = get_form()
        # This will fail if __init__ doesn't accept `user`
        form = form_class(obj, user=user)
        context.update({
            'form': form,
            'next': obj.get_absolute_url(),
        })
    return context


@register.simple_tag
def get_page_range(page_obj):
    """
    Генерирует умный список страниц для пагинации.

    Логика:
    - Всегда показываем первую и последнюю страницы
    - Показываем текущую страницу и по 2 страницы с каждой стороны (5 страниц всего)
    - Если между группами страниц расстояние > 1, добавляем многоточие (None)

    Примеры (для 20 страниц):
        Страница 1:   [1] 2 3 4 5 ... 20
        Страница 3:   1 2 [3] 4 5 ... 20
        Страница 6:   1 ... 4 5 [6] 7 8 ... 20
        Страница 8:   1 ... 6 7 [8] 9 10 ... 20
        Страница 10:  1 ... 8 9 [10] 11 12 ... 20
        Страница 15:  1 ... 13 14 [15] 16 17 ... 20
        Страница 18:  1 ... 16 17 [18] 19 20
        Страница 20:  1 ... 16 17 18 19 [20]

    Args:
        page_obj: Django Paginator Page object

    Returns:
        list: Список номеров страниц (int) или None (для многоточия)
    """
    current = page_obj.number
    total = page_obj.paginator.num_pages

    # Если страниц <= 7, показываем все
    if total <= 7:
        return list(range(1, total + 1))

    pages = set()

    # Всегда показываем первую и последнюю
    pages.add(1)
    pages.add(total)

    # Всегда показываем текущую страницу и по 2 с каждой стороны
    for i in range(max(1, current - 2), min(total + 1, current + 3)):
        pages.add(i)

    # Преобразуем в отсортированный список
    pages_list = sorted(pages)

    # Добавляем многоточия между группами
    result = []
    prev = 0
    for page in pages_list:
        if page - prev > 1:
            result.append(None)  # None обозначает многоточие
        result.append(page)
        prev = page

    return result
