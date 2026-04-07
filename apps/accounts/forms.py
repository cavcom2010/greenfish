"""
Forms for the accounts app.
"""
from allauth.account.forms import SignupForm
from django import forms

from .models import User


class CustomSignupForm(SignupForm):
    """Custom signup form with phone number."""
    
    first_name = forms.CharField(max_length=150, label="First Name")
    last_name = forms.CharField(max_length=150, label="Last Name")
    phone_number = forms.CharField(max_length=30, required=False, label="Phone Number")
    
    def save(self, request):
        user = super().save(request)
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.phone_number = self.cleaned_data["phone_number"]
        user.save()
        return user


class UserProfileForm(forms.ModelForm):
    """Form for updating user profile."""
    
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone_number"]
