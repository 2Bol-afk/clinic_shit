from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

class EmailOrUsernameModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        
        # Try email first
        try:
            # Use filter().first() to handle multiple users with same email
            user = UserModel.objects.filter(email__iexact=username).first()
            if user is None:
                # Fallback to username
                user = UserModel.objects.filter(**{UserModel.USERNAME_FIELD: username}).first()
        except Exception:
            # If any error occurs, try username fallback
            try:
                user = UserModel.objects.filter(**{UserModel.USERNAME_FIELD: username}).first()
            except Exception:
                return None
        
        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
