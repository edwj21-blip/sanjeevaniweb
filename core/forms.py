"""Forms for Sanjeevani."""
from django import forms
from django.contrib.auth.models import User
from django.core.validators import RegexValidator

from . import eligibility
from .models import (
    DONATION_TYPES, BLOOD_GROUPS, KERALA_DISTRICTS, ContactMessage, DonorProfile,
)
from .services import DonationError, today, validate_donation_date
from .translations import tr

phone_validator = RegexValidator(regex=r'^[6-9]\d{9}$', message='Enter a valid 10-digit Indian mobile number.')

UNDER_18_MESSAGE = "You must be at least 18 years old to register as a blood donor."

FC = {'class': 'form-control'}
FS = {'class': 'form-select'}
FCHK = {'class': 'form-check-input'}


def _tr_choices(choices):
    return [(v, tr(l)) for v, l in choices]


class DonorRegistrationForm(forms.Form):
    full_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs=FC))
    mobile = forms.CharField(max_length=10, widget=forms.TextInput(attrs={**FC, 'inputmode': 'numeric'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs=FC))
    password = forms.CharField(min_length=6, widget=forms.PasswordInput(attrs=FC))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs=FC))
    date_of_birth = forms.DateField(input_formats=['%Y-%m-%d'], widget=forms.DateInput(attrs={**FC, 'type': 'date', 'id': 'id_date_of_birth'}, format='%Y-%m-%d'))
    blood_group = forms.ChoiceField(choices=[('', '--')] + BLOOD_GROUPS, widget=forms.Select(attrs=FS))
    district = forms.ChoiceField(choices=[('', '--')] + list(KERALA_DISTRICTS), widget=forms.Select(attrs=FS))
    locality = forms.CharField(max_length=100, widget=forms.TextInput(attrs=FC))
    last_donation_date = forms.DateField(input_formats=['%Y-%m-%d'], required=False, widget=forms.DateInput(attrs={**FC, 'type': 'date'}, format='%Y-%m-%d'))
    last_donation_type = forms.ChoiceField(required=False, choices=DONATION_TYPES, initial='whole_blood',
                                           widget=forms.Select(attrs=FS))
    share_contact = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs=FCHK))  # consent to be contacted (validated below)
    health_declaration = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs=FCHK))
    show_in_directory = forms.BooleanField(required=False, initial=True, widget=forms.CheckboxInput(attrs=FCHK))
    show_last_donation_date = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs=FCHK))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['last_donation_type'].choices = _tr_choices(DONATION_TYPES)

    def clean_mobile(self):
        mobile = self.cleaned_data['mobile'].strip()
        phone_validator(mobile)
        if DonorProfile.objects.filter(mobile=mobile).exists() or User.objects.filter(username=mobile).exists():
            raise forms.ValidationError(tr('This mobile number is already registered.'))
        return mobile

    def clean_date_of_birth(self):
        dob = self.cleaned_data['date_of_birth']
        if dob > today():
            raise forms.ValidationError(tr('Date of birth cannot be in the future.'))
        if not eligibility.is_adult(dob, today()):
            raise forms.ValidationError(tr(UNDER_18_MESSAGE))
        return dob

    def clean_share_contact(self):
        if not self.cleaned_data.get('share_contact'):
            raise forms.ValidationError(tr('You must agree to be contacted to register as a donor.'))
        return True

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password') and cleaned.get('confirm_password') \
                and cleaned['password'] != cleaned['confirm_password']:
            self.add_error('confirm_password', tr('Passwords do not match.'))
        last = cleaned.get('last_donation_date')
        dob = cleaned.get('date_of_birth')
        if last:
            if last > today():
                self.add_error('last_donation_date', tr('Donation date cannot be in the future.'))
            elif dob and last < eligibility.eighteenth_birthday(dob):
                self.add_error('last_donation_date', tr('Donation date cannot be before you turned 18.'))
        return cleaned


class ReceiverSignupForm(forms.Form):
    full_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs=FC))
    mobile = forms.CharField(max_length=10, validators=[phone_validator], widget=forms.TextInput(attrs=FC))
    password = forms.CharField(min_length=6, widget=forms.PasswordInput(attrs=FC))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs=FC))

    def clean_mobile(self):
        mobile = self.cleaned_data['mobile'].strip()
        if User.objects.filter(username=mobile).exists():
            raise forms.ValidationError(tr('This mobile number is already registered.'))
        return mobile

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password') and cleaned.get('confirm_password') \
                and cleaned['password'] != cleaned['confirm_password']:
            self.add_error('confirm_password', tr('Passwords do not match.'))
        return cleaned


class DonorProfileEditForm(forms.ModelForm):
    """Availability, last donation date and eligibility are deliberately NOT editable here."""
    full_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs=FC))

    class Meta:
        model = DonorProfile
        fields = ['date_of_birth', 'blood_group', 'district', 'locality',
                  'health_declaration', 'show_in_directory', 'share_contact', 'show_last_donation_date']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={**FC, 'type': 'date', 'id': 'id_date_of_birth'}, format='%Y-%m-%d'),
            'blood_group': forms.Select(attrs=FS),
            'district': forms.Select(attrs=FS),
            'locality': forms.TextInput(attrs=FC),
            'health_declaration': forms.CheckboxInput(attrs=FCHK),
            'show_in_directory': forms.CheckboxInput(attrs=FCHK),
            'share_contact': forms.CheckboxInput(attrs=FCHK),
            'show_last_donation_date': forms.CheckboxInput(attrs=FCHK),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date_of_birth'].required = True
        if self.instance and self.instance.pk:
            self.fields['full_name'].initial = self.instance.user.get_full_name()

    def clean_date_of_birth(self):
        dob = self.cleaned_data['date_of_birth']
        if dob > today():
            raise forms.ValidationError(tr('Date of birth cannot be in the future.'))
        if not eligibility.is_adult(dob, today()):
            raise forms.ValidationError(tr(UNDER_18_MESSAGE))
        return dob


class DonationUpdateForm(forms.Form):
    donation_date = forms.DateField(input_formats=['%Y-%m-%d'], widget=forms.DateInput(attrs={**FC, 'type': 'date'}, format='%Y-%m-%d'))
    donation_type = forms.ChoiceField(choices=DONATION_TYPES, initial='whole_blood', widget=forms.Select(attrs=FS))

    def __init__(self, *args, donor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.donor = donor
        self.fields['donation_type'].choices = _tr_choices(DONATION_TYPES)

    def clean(self):
        cleaned = super().clean()
        d, kind = cleaned.get('donation_date'), cleaned.get('donation_type')
        if d and kind:
            try:
                validate_donation_date(self.donor, d, kind)
            except DonationError as exc:
                msgs = {
                    'future': 'Donation date cannot be in the future.',
                    'before_18': 'Donation date cannot be before you turned 18.',
                    'duplicate': 'A donation is already recorded for this date.',
                    'too_close': 'This date is too close to another recorded donation.',
                }
                self.add_error('donation_date', tr(msgs.get(str(exc), 'Invalid donation date.')))
        return cleaned


class NotificationSettingsForm(forms.ModelForm):
    class Meta:
        model = DonorProfile
        fields = ['notify_reminders']
        widgets = {'notify_reminders': forms.CheckboxInput(attrs=FCHK)}


class MobileLoginForm(forms.Form):
    mobile = forms.CharField(max_length=10, widget=forms.TextInput(attrs={**FC, 'inputmode': 'numeric'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs=FC))


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'mobile', 'subject', 'message']
        widgets = {
            'name': forms.TextInput(attrs=FC), 'email': forms.EmailInput(attrs=FC),
            'mobile': forms.TextInput(attrs=FC), 'subject': forms.TextInput(attrs=FC),
            'message': forms.Textarea(attrs={**FC, 'rows': 5}),
        }


class DonorSearchForm(forms.Form):
    AVAIL = [('', 'All'), ('available', 'Available'), ('unavailable', 'Unavailable')]
    blood_group = forms.ChoiceField(choices=[('', '--')] + BLOOD_GROUPS, required=False, widget=forms.Select(attrs=FS))
    district = forms.ChoiceField(choices=[('', '--')] + list(KERALA_DISTRICTS), required=False, widget=forms.Select(attrs=FS))
    locality = forms.CharField(required=False, widget=forms.TextInput(attrs=FC))
    name = forms.CharField(required=False, widget=forms.TextInput(attrs=FC))
    availability = forms.ChoiceField(choices=AVAIL, required=False, widget=forms.Select(attrs=FS))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['availability'].choices = _tr_choices(self.AVAIL)
