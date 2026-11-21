"""Forms for Sanjeevani."""
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.core.validators import RegexValidator
from .models import DonorProfile, ContactMessage, HospitalLocationDetails, KERALA_DISTRICTS, BLOOD_GROUPS

phone_validator = RegexValidator(
    regex=r'^[6-9]\d{9}$',
    message='Enter a valid 10-digit Indian mobile number.'
)

MAPS_PREFIXES = (
    'https://maps.google.com',
    'https://www.google.com/maps',
    'https://goo.gl/maps',
    'https://maps.app.goo.gl',
)


class DonorRegistrationForm(forms.Form):
    full_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your full name'}))
    mobile = forms.CharField(max_length=10, validators=[phone_validator], widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '10-digit mobile number'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address (optional)'}))
    password = forms.CharField(min_length=6, widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Create password (min 6 characters)'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm password'}))
    blood_group = forms.ChoiceField(choices=[('', '-- Select Blood Group --')] + BLOOD_GROUPS, widget=forms.Select(attrs={'class': 'form-select'}))
    district = forms.ChoiceField(choices=[('', '-- Select District --')] + list(KERALA_DISTRICTS), widget=forms.Select(attrs={'class': 'form-select'}))
    locality = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your locality / area'}))
    last_donation_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    is_available = forms.BooleanField(required=False, initial=True, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    show_in_directory = forms.BooleanField(required=False, initial=True, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    share_contact = forms.BooleanField(required=False, initial=True, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    show_last_donation_date = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))

    def clean_mobile(self):
        mobile = self.cleaned_data['mobile']
        if DonorProfile.objects.filter(mobile=mobile).exists():
            raise forms.ValidationError('This mobile number is already registered.')
        if User.objects.filter(username=mobile).exists():
            raise forms.ValidationError('This mobile number is already registered.')
        return mobile

    def clean_blood_group(self):
        bg = self.cleaned_data.get('blood_group')
        if not bg:
            raise forms.ValidationError('Please select a blood group.')
        return bg

    def clean_district(self):
        d = self.cleaned_data.get('district')
        if not d:
            raise forms.ValidationError('Please select a district.')
        return d

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password')
        p2 = cleaned.get('confirm_password')
        if p1 and p2 and p1 != p2:
            self.add_error('confirm_password', 'Passwords do not match.')
        return cleaned


class DonorProfileEditForm(forms.ModelForm):
    class Meta:
        model = DonorProfile
        fields = ['blood_group', 'district', 'locality', 'last_donation_date', 'is_available',
                  'show_in_directory', 'share_contact', 'show_last_donation_date']
        widgets = {
            'blood_group': forms.Select(attrs={'class': 'form-select'}),
            'district': forms.Select(attrs={'class': 'form-select'}),
            'locality': forms.TextInput(attrs={'class': 'form-control'}),
            'last_donation_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_in_directory': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'share_contact': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_last_donation_date': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    full_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user:
            self.fields['full_name'].initial = self.instance.user.get_full_name()


class MobileLoginForm(forms.Form):
    mobile = forms.CharField(max_length=10, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Mobile number'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}))


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'mobile', 'subject', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'}),
            'mobile': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Mobile number (optional)'}),
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Subject'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Your message'}),
        }


class HospitalLocationForm(forms.ModelForm):
    class Meta:
        model = HospitalLocationDetails
        fields = ['hospital_name', 'district', 'full_address', 'google_maps_link']
        widgets = {
            'hospital_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Hospital name'}),
            'district': forms.Select(attrs={'class': 'form-select'}),
            'full_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Full hospital address'}),
            'google_maps_link': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'Paste Google Maps link here'}),
        }

    def clean_google_maps_link(self):
        link = self.cleaned_data.get('google_maps_link', '')
        if not any(link.startswith(p) for p in MAPS_PREFIXES):
            raise forms.ValidationError('Please enter a valid Google Maps link.')
        return link


class DonorSearchForm(forms.Form):
    blood_group = forms.ChoiceField(
        choices=[('', 'All Blood Groups')] + BLOOD_GROUPS,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    district = forms.ChoiceField(
        choices=[('', 'All Districts')] + list(KERALA_DISTRICTS),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    locality = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search by locality'})
    )
    available_only = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
