# accounts/forms.py
from django import forms
from .models import Profile

class SignupForm(forms.Form):
    lesta_nickname = forms.CharField(label="Ник в игре", max_length=64)
    clan = forms.CharField(label="Клан", max_length=64, required=False)

    # allauth вызовет этот метод после создания пользователя
    def signup(self, request, user):
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.lesta_nickname = self.cleaned_data["lesta_nickname"]
        profile.clan = self.cleaned_data.get("clan", "")
        profile.save()
        return user
