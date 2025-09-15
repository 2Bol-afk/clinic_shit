from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

class EmailOrUsernameModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        # Try email first
        try:
            user = UserModel.objects.get(email__iexact=username)
        except UserModel.DoesNotExist:
            # Fallback to username
            try:
                user = UserModel.objects.get(**{UserModel.USERNAME_FIELD: username})
            except UserModel.DoesNotExist:
                return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
