# news/views.py
from django.contrib.auth.mixins import UserPassesTestMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView

from .models import News
from .forms import NewsForm


class NewsListView(ListView):
    """
    Страница со списком всех новостей.
    """
    model = News
    template_name = 'news/news_list.html'
    context_object_name = 'news_list'
    paginate_by = 10

    def get_queryset(self):
        return News.objects.filter(is_active=True).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "Новости"
        return context


class NewsDetailView(DetailView):
    """
    Детальная страница новости.
    """
    model = News
    template_name = 'news/news_detail.html'
    context_object_name = 'news'

    def get_queryset(self):
        return News.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = self.object.title
        return context


class NewsCreateView(UserPassesTestMixin, CreateView):
    """
    Страница создания новости (только для staff).
    """
    model = News
    form_class = NewsForm
    template_name = 'news/news_form.html'
    success_url = reverse_lazy('news:news_list')

    def test_func(self):
        return self.request.user.is_staff

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "Добавить новость"
        return context
