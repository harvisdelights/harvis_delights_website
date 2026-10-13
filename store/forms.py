from django import forms
from django.contrib.auth import authenticate, get_user_model


class CustomerSignupForm(forms.Form):
    first_name = forms.CharField(max_length=30, label="First name")
    last_name = forms.CharField(max_length=30, label="Last name", required=False)
    email = forms.EmailField(max_length=150)
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput, min_length=8)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        user_model = get_user_model()
        if user_model.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Please sign in.")
        if user_model.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("Please use a different email address.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("password1") and cleaned_data.get("password2") and cleaned_data["password1"] != cleaned_data["password2"]:
            self.add_error("password2", "Passwords do not match.")
        return cleaned_data

    def save(self):
        user_model = get_user_model()
        return user_model.objects.create_user(
            username=self.cleaned_data["email"],
            email=self.cleaned_data["email"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
            password=self.cleaned_data["password1"],
        )


class CustomerLoginForm(forms.Form):
    email = forms.EmailField(label="Email address")
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user_cache = None

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email", "").lower()
        password = cleaned_data.get("password")
        if email and password:
            user_model = get_user_model()
            user = user_model.objects.filter(email__iexact=email).first()
            self.user_cache = authenticate(self.request, username=user.username if user else email, password=password)
            if self.user_cache is None:
                raise forms.ValidationError("Email or password is incorrect.")
        return cleaned_data

    def get_user(self):
        return self.user_cache


class CheckoutAddressForm(forms.Form):
    full_name = forms.CharField(max_length=120, label="Full name")
    phone = forms.RegexField(regex=r"^[6-9][0-9]{9}$", label="Mobile number", error_messages={"invalid": "Enter a valid 10-digit Indian mobile number."})
    line1 = forms.CharField(max_length=180, label="Address line 1")
    line2 = forms.CharField(max_length=180, label="Address line 2", required=False)
    city = forms.CharField(max_length=80)
    state = forms.CharField(max_length=80)
    pincode = forms.RegexField(regex=r"^[1-9][0-9]{5}$", label="Pincode", error_messages={"invalid": "Enter a valid 6-digit pincode."})
