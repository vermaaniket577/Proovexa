"""
Authentication and registration forms.
"""
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User, Institution


class LoginForm(AuthenticationForm):
    """Custom login form with Bootstrap styling."""
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Username or Email',
            'id': 'login-username',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password',
            'id': 'login-password',
        })
    )


class RegistrationForm(UserCreationForm):
    """User registration form."""
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email address',
            'id': 'register-email',
        })
    )
    first_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'First name',
            'id': 'register-first-name',
        })
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Last name',
            'id': 'register-last-name',
        })
    )
    role = forms.ChoiceField(
        choices=[
            (User.Role.STUDENT, 'Student / Author'),
            (User.Role.TEACHER, 'Teacher / Researcher'),
        ],
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'register-role',
        })
    )
    institution = forms.ModelChoiceField(
        queryset=Institution.objects.filter(is_active=True),
        required=False,
        empty_label="Select institution (optional)",
        widget=forms.Select(attrs={
            'class': 'form-select',
            'id': 'register-institution',
        })
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'role', 'institution', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Username',
                'id': 'register-username',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Password',
            'id': 'register-password1',
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Confirm password',
            'id': 'register-password2',
        })


class UserProfileForm(forms.ModelForm):
    """User profile update form."""
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'department', 'phone', 'bio']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class AdminUserForm(forms.ModelForm):
    """Admin form for creating/editing users."""
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'role', 'institution',
                  'department', 'is_active', 'is_verified']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'institution': forms.Select(attrs={'class': 'form-select'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_verified': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
