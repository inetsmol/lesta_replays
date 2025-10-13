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
