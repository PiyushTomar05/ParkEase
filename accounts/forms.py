from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.validators import RegexValidator

User = get_user_model()


class UserRegisterForm(UserCreationForm):
    """
    User registration form extending Django's UserCreationForm.
    Requires username (strictly 10 characters or fewer), email, and confirmed password
    with full Django password validation.
    """
    username = forms.CharField(
        max_length=10,
        required=True,
        validators=[
            RegexValidator(
                regex=r'^[\w.@+-]+$',
                message='Enter a valid username. Letters, digits and @/./+/-/_ only.'
            )
        ],
        error_messages={
            'max_length': 'Username must be 10 characters or fewer.',
            'required': 'Username is required.',
        },
        help_text='Required. 10 characters or fewer. Letters, digits and @/./+/-/_ only.',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter username (max 10 chars)',
            'autocomplete': 'username',
            'maxlength': '10',
        })
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'name@example.com',
            'autocomplete': 'email',
        }),
        error_messages={
            'required': 'Email address is required.',
        },
        help_text='Required. Enter a valid email address.'
    )

    class Meta:
        model = User
        fields = ('username', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Enter username (max 10 chars)',
            'autocomplete': 'username',
            'maxlength': '10',
        })
        self.fields['username'].help_text = 'Required. 10 characters or fewer. Letters, digits and @/./+/-/_ only.'

        if 'password1' in self.fields:
            self.fields['password1'].widget.attrs.update({
                'class': 'form-control',
                'placeholder': 'Create a strong password',
                'autocomplete': 'new-password',
            })
        if 'password2' in self.fields:
            self.fields['password2'].widget.attrs.update({
                'class': 'form-control',
                'placeholder': 'Confirm your password',
                'autocomplete': 'new-password',
            })

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not username:
            raise forms.ValidationError('Username is required.')
        if len(username) > 10:
            raise forms.ValidationError('Username must be 10 characters or fewer.')
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('A user with that username already exists.')
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            raise forms.ValidationError('Email address is required.')
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('A user with that email already exists.')
        return email


class UserLoginForm(AuthenticationForm):
    """
    User login form extending Django's AuthenticationForm with Bootstrap classes.
    Accepts usernames up to 150 characters so existing accounts with legacy lengths
    continue to log in seamlessly.
    """
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your username',
            'autocomplete': 'username',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password',
        })
    )
