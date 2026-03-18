# ============================================================
# DRF serializers for User, UserProfile, TradingAccount
# ============================================================
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, UserProfile, TradingAccount
from utils.constants import Broker, AccountType
from utils.validators import validate_api_key_format


# ── User Registration ────────────────────────────────────────
class RegisterSerializer(serializers.ModelSerializer):
    password         = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model  = User
        fields = ('email', 'first_name', 'last_name', 'password', 'password_confirm')

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password_confirm'):
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


class RegisterResponseSerializer(serializers.Serializer):
    """Shape of the response returned after successful registration."""
    user    = serializers.DictField()
    tokens  = serializers.DictField()
    message = serializers.CharField()


# ── Login ────────────────────────────────────────────────────
class LoginSerializer(serializers.Serializer):
    email    = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email    = attrs.get('email', '').lower().strip()
        password = attrs.get('password', '')

        user = authenticate(
            request=self.context.get('request'),
            username=email,
            password=password,
        )

        if not user:
            raise serializers.ValidationError(
                {'non_field_errors': 'Invalid email or password.'}
            )
        if not user.is_active:
            raise serializers.ValidationError(
                {'non_field_errors': 'This account has been deactivated.'}
            )

        attrs['user'] = user
        return attrs


# ── Token Pair ───────────────────────────────────────────────
class TokenResponseSerializer(serializers.Serializer):
    access  = serializers.CharField()
    refresh = serializers.CharField()

    @staticmethod
    def get_tokens(user) -> dict:
        refresh = RefreshToken.for_user(user)
        return {
            'access':  str(refresh.access_token),
            'refresh': str(refresh),
        }


# ── User Profile ─────────────────────────────────────────────
class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model  = UserProfile
        fields = (
            'timezone', 'currency', 'language',
            'email_alerts', 'email_on_trade', 'email_on_error',
            'dashboard_theme', 'nlp_enabled', 'nlp_model',
            'created_at', 'updated_at',
        )
        read_only_fields = ('created_at', 'updated_at')


# ── User (read) ───────────────────────────────────────────────
class UserSerializer(serializers.ModelSerializer):
    profile    = UserProfileSerializer(read_only=True)
    full_name  = serializers.CharField(read_only=True)
    bot_count  = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = (
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'is_active', 'is_verified', 'date_joined', 'last_login',
            'profile', 'bot_count',
        )
        read_only_fields = ('id', 'is_active', 'is_verified', 'date_joined', 'last_login')

    def get_bot_count(self, obj) -> int:
        return obj.bots.filter(is_active=True).count()


# ── User (update) ────────────────────────────────────────────
class UserUpdateSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(required=False)

    class Meta:
        model  = User
        fields = ('first_name', 'last_name', 'profile')

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', None)

        # Update user fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update nested profile
        if profile_data:
            profile = instance.profile
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            profile.save()

        return instance


# ── Change Password ──────────────────────────────────────────
class ChangePasswordSerializer(serializers.Serializer):
    old_password     = serializers.CharField(write_only=True)
    new_password     = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError(
                {'confirm_password': 'New passwords do not match.'}
            )
        return attrs

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Current password is incorrect.')
        return value


# ── TradingAccount (write) ───────────────────────────────────
class TradingAccountCreateSerializer(serializers.ModelSerializer):
    """
    Used when creating/updating a TradingAccount.
    api_key and api_secret are write-only — they get encrypted
    before storage via set_api_key() / set_api_secret() methods.
    """
    api_key    = serializers.CharField(write_only=True, required=True)
    api_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model  = TradingAccount
        fields = (
            'name', 'broker', 'account_id', 'account_type',
            'currency', 'api_key', 'api_secret',
        )

    def validate(self, attrs):
        broker  = attrs.get('broker', '')
        api_key = attrs.get('api_key', '')
        if not validate_api_key_format(api_key, broker):
            raise serializers.ValidationError({
                'api_key': f'API key format is invalid for broker {broker}.'
            })
        return attrs

    def create(self, validated_data):
        api_key    = validated_data.pop('api_key')
        api_secret = validated_data.pop('api_secret', '')
        user       = self.context['request'].user

        account = TradingAccount(user=user, **validated_data)
        account.set_api_key(api_key)
        if api_secret:
            account.set_api_secret(api_secret)
        account.save()
        return account

    def update(self, instance, validated_data):
        api_key    = validated_data.pop('api_key', None)
        api_secret = validated_data.pop('api_secret', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if api_key:
            instance.set_api_key(api_key)
        if api_secret:
            instance.set_api_secret(api_secret)

        instance.save()
        return instance


# ── TradingAccount (read) ────────────────────────────────────
class TradingAccountSerializer(serializers.ModelSerializer):
    """
    Safe read serializer — never exposes api_key or api_secret.
    Shows masked key hint instead (last 4 chars).
    """
    api_key_hint = serializers.SerializerMethodField()
    bot_count    = serializers.SerializerMethodField()

    class Meta:
        model  = TradingAccount
        fields = (
            'id', 'name', 'broker', 'account_id', 'account_type',
            'balance', 'equity', 'margin_used', 'margin_free', 'currency',
            'is_active', 'is_verified', 'last_synced',
            'api_key_hint', 'bot_count',
            'created_at', 'updated_at',
        )
        read_only_fields = fields

    def get_api_key_hint(self, obj) -> str:
        """Show only last 4 chars of encrypted token length as a hint."""
        if obj._api_key_encrypted:
            return f"****{obj._api_key_encrypted[-4:]}"
        return None

    def get_bot_count(self, obj) -> int:
        return obj.bots.filter(is_active=True).count()


# ── Verify Connection ────────────────────────────────────────
class VerifyConnectionSerializer(serializers.Serializer):
    """Response shape when testing broker connection."""
    success     = serializers.BooleanField()
    message     = serializers.CharField()
    account_id  = serializers.CharField(allow_blank=True)
    balance     = serializers.FloatField(allow_null=True)
    currency    = serializers.CharField(allow_blank=True)