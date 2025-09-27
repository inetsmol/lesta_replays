# core/context_processors.py
def sidebar_widgets(request):
    return {
        # меняйте порядок/состав, чтобы управлять сайдбаром слева/справа
        "left_widgets": [
            "includes/sidebar/_support.html",
            # "includes/sidebar/_friends.html",
        ],
        "right_widgets": [
            "includes/sidebar/_friends.html",
        ],
    }