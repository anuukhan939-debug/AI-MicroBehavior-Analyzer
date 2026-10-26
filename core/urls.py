from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views

app_name = 'core'

urlpatterns = [
    # Authentication
    path('', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', LogoutView.as_view(next_page='core:login'), name='logout'),
    path('consent/', views.consent_view, name='consent'),

    path('profile/', views.profile_view, name='profile'),
    
    # Dashboard
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/system/', views.system_admin_dashboard, name='system_dashboard'),
    
    # Sessions
    path('sessions/', views.sessions_view, name='sessions'),
    path('session/start/', views.start_session, name='start_session'),
    path('session/end/<uuid:session_id>/', views.end_session, name='end_session'),
    path('session/<uuid:session_id>/', views.session_detail, name='session_detail'),
    path('session/<uuid:session_id>/realtime/', views.realtime_analysis, name='realtime_analysis'),
    path('sessions/', views.sessions_view, name='sessions_view'),
    # API endpoints for real-time data

    path('api/user-sessions/<uuid:user_id>/', views.user_sessions_api, name='user_sessions_api'),
    path('api/recent-reports/', views.recent_reports_api, name='recent_reports_api'),

    path('api/analyze-frame/', views.analyze_frame_api, name='analyze_frame'),
    path('api/session-stats/<uuid:session_id>/', views.get_session_stats, name='session_stats'),
    path('api/dashboard-data/', views.get_dashboard_data, name='dashboard_data'),
    
    # Reports
    path('reports/', views.reports_view, name='reports'),
    path('reports/generate/', views.generate_report, name='generate_report'),
    path('reports/download/<uuid:report_id>/', views.download_report, name='download_report'),
    path('api/export-session-data/<uuid:session_id>/', views.export_session_data, name='export_session_data'),
    # User Management (Admin only)
    path('users/', views.user_management, name='user_management'),
    path('users/add/', views.add_user, name='add_user'),
    path('users/edit/<uuid:user_id>/', views.edit_user, name='edit_user'),
    path('users/delete/<uuid:user_id>/', views.delete_user, name='delete_user'),
    
    # System Configuration (System Admin only)
    path('system/config/', views.system_config, name='system_config'),
    path('system/logs/', views.system_logs, name='system_logs'),
    path('system/backup/', views.backup_database, name='backup_database'),
    
    # Alerts
    path('alerts/', views.alerts_view, name='alerts'),
    path('alerts/resolve/<uuid:alert_id>/', views.resolve_alert, name='resolve_alert'),
    # System Admin API endpoints
    path('api/system-stats/', views.system_stats_api, name='system_stats_api'),
    path('api/backup/', views.backup_database_api, name='backup_database_api'),
    path('api/restart-services/', views.restart_services_api, name='restart_services_api'),
    path('api/clear-cache/', views.clear_cache_api, name='clear_cache_api'),
    path('api/diagnostics/', views.diagnostics_api, name='diagnostics_api'),
    path('api/system-config/', views.system_config_api, name='system_config_api'),
    path('api/clear-logs/', views.clear_logs_api, name='clear_logs_api'),
    path('api/download-logs/', views.download_logs_api, name='download_logs_api'),
]