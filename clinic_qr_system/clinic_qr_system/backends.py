from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

class EmailOrUsernameModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if not username or not password:
            return None

        # Normalize input
        lookup_value = (username or '').strip()

        # 1) Try by email: check all users with this email and return the one whose password matches
        try:
            email_candidates = list(UserModel.objects.filter(email__iexact=lookup_value))
            for candidate in email_candidates:
                if candidate.check_password(password) and self.user_can_authenticate(candidate):
                    return candidate
        except Exception:
            pass

        # 2) Fallback: try username
        try:
            user = UserModel.objects.filter(**{UserModel.USERNAME_FIELD: lookup_value}).first()
            if user and user.check_password(password) and self.user_can_authenticate(user):
                return user
        except Exception:
            return None

        return None
