# replays/context_processors.py
from replays.services import SubscriptionService, UsageLimitService


def sidebar_widgets(request):
    return {
        # меняйте порядок/состав, чтобы управлять сайдбаром слева/справа
        "left_widgets": [
            "includes/sidebar/_support.html",
            # "includes/sidebar/_friends.html",
        ],
        "right_widgets": [
            "includes/sidebar/_telegram.html",
            "includes/sidebar/_friends.html",
        ],
    }


def subscription_context(request):
    """Контекст подписки для всех шаблонов."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {
            'user_plan': None,
            'is_premium': False,
            'is_pro': False,
            'show_donation_prompts': True,
            'remaining_uploads': None,
            'remaining_downloads': None,
        }

    plan = SubscriptionService.get_user_plan(user)
    remaining = UsageLimitService.get_remaining(user)
    user_subscription = getattr(user, 'subscription', None)

    return {
        'user_plan': plan,
        'user_subscription': user_subscription,
        'user_profile': getattr(user, 'profile', None),
        'is_premium': plan.name in ('premium', 'pro'),
        'is_pro': plan.name == 'pro',
        'show_donation_prompts': plan.show_donation_prompts,
        'remaining_uploads': remaining['uploads_remaining'],
        'remaining_downloads': remaining['downloads_remaining'],
        'uploads_limit': remaining['uploads_limit'],
        'downloads_limit': remaining['downloads_limit'],
    }