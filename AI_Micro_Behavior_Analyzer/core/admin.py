# from django.contrib import admin

# # Register your models here.
# from django.contrib.auth.admin import UserAdmin
# from .models import User

# admin.site.register(User, UserAdmin)
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Session, EmotionData, FocusData, Alert, Report, SystemLog, SystemConfiguration

# Custom User Admin
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role', 'is_active', 'date_joined')
    list_filter = ('role', 'is_active')
    search_fields = ('username', 'email')
    fieldsets = UserAdmin.fieldsets + (
        ('Additional Info', {'fields': ('role', 'phone', 'organization', 'consent_given')}),
    )

# Session Admin
class SessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'start_time', 'end_time', 'status', 'domain')
    list_filter = ('status', 'domain', 'start_time')
    search_fields = ('user__username',)
    readonly_fields = ('id',)

# Emotion Data Admin
class EmotionDataAdmin(admin.ModelAdmin):
    list_display = ('session', 'timestamp', 'emotion', 'confidence')
    list_filter = ('emotion', 'timestamp')
    search_fields = ('session__user__username',)

# Focus Data Admin
class FocusDataAdmin(admin.ModelAdmin):
    list_display = ('session', 'timestamp', 'attention_score', 'is_focused', 'gaze_direction')
    list_filter = ('is_focused', 'timestamp')
    search_fields = ('session__user__username',)

# Alert Admin
class AlertAdmin(admin.ModelAdmin):
    list_display = ('session', 'alert_type', 'priority', 'timestamp', 'is_resolved')
    list_filter = ('priority', 'is_resolved', 'alert_type')
    search_fields = ('session__user__username',)

# Report Admin
class ReportAdmin(admin.ModelAdmin):
    list_display = ('generated_by', 'report_type', 'generated_at', 'start_date', 'end_date')
    list_filter = ('report_type', 'generated_at')

# System Log Admin
class SystemLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'timestamp', 'ip_address')
    list_filter = ('timestamp',)
    search_fields = ('user__username', 'action')

# System Configuration Admin
class SystemConfigurationAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'updated_at', 'updated_by')
    search_fields = ('key',)

# Register all models
admin.site.register(User, CustomUserAdmin)
admin.site.register(Session, SessionAdmin)
admin.site.register(EmotionData, EmotionDataAdmin)
admin.site.register(FocusData, FocusDataAdmin)
admin.site.register(Alert, AlertAdmin)
admin.site.register(Report, ReportAdmin)
admin.site.register(SystemLog, SystemLogAdmin)
admin.site.register(SystemConfiguration, SystemConfigurationAdmin)