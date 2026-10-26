from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
import uuid

class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('user', 'User'),
        ('system_admin', 'System Administrator'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    phone = models.CharField(max_length=15, blank=True)
    organization = models.CharField(max_length=200, blank=True)
    consent_given = models.BooleanField(default=False)
    consent_date = models.DateTimeField(null=True, blank=True)
    profile_picture = models.ImageField(upload_to='profiles/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'users'
        ordering = ['-date_joined']
    
    def __str__(self):
        return f"{self.username} - {self.role}"
    
    def get_full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username
    
    def give_consent(self):
        self.consent_given = True
        self.consent_date = timezone.now()
        self.save()

class Session(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('interrupted', 'Interrupted'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    domain = models.CharField(max_length=50, default='education')  # education, corporate, healthcare
    # 🟢🟢🟢 YEH LINE ADD KARO 🟢🟢🟢
    ANALYSIS_MODES = (
        ('both', 'Focus + Emotion (Full)'),
        ('focus', 'Focus Only (Attention/Gaze)'),
        ('emotion', 'Emotion Only (Facial Expression)'),
    )
    analysis_mode = models.CharField(max_length=10, choices=ANALYSIS_MODES, default='both')
    # 🟢🟢🟢 YAHAN TAK 🟢🟢🟢
    
    class Meta:
        db_table = 'sessions'
        ordering = ['-start_time']
    
    def __str__(self):
        return f"Session {self.id} - {self.user.username}"
    
    def duration(self):
        if self.end_time:
            return self.end_time - self.start_time
        return timezone.now() - self.start_time
    
    def end_session(self):
        self.end_time = timezone.now()
        self.status = 'completed'
        self.save()

class EmotionData(models.Model):
    EMOTION_CHOICES = (
        ('happy', 'Happy'),
        ('sad', 'Sad'),
        ('angry', 'Angry'),
        ('surprised', 'Surprised'),
        ('fearful', 'Fearful'),
        ('disgusted', 'Disgusted'),
        ('neutral', 'Neutral'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='emotions')
    timestamp = models.DateTimeField(auto_now_add=True)
    emotion = models.CharField(max_length=20, choices=EMOTION_CHOICES)
    confidence = models.FloatField()
    frame_data = models.TextField(blank=True)  # Store frame metadata
    
    class Meta:
        db_table = 'emotion_data'
        ordering = ['timestamp']
    
    def __str__(self):
        return f"{self.emotion} - {self.confidence:.2f}"

class FocusData(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='focus_records')
    timestamp = models.DateTimeField(auto_now_add=True)
    attention_score = models.FloatField()  # 0-100
    gaze_direction = models.CharField(max_length=50, default='center')  # left, right, center, up, down
    head_pose = models.JSONField(default=dict)  # pitch, yaw, roll angles
    is_focused = models.BooleanField(default=True)
    engagement_score = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = 'focus_data'
        ordering = ['timestamp']
    
    def __str__(self):
        return f"Focus: {self.attention_score}% - {self.timestamp}"

class Alert(models.Model):
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='alerts')
    admin = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='handled_alerts')
    timestamp = models.DateTimeField(auto_now_add=True)
    alert_type = models.CharField(max_length=50)  # low_focus, negative_emotion, etc.
    message = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'alerts'
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"Alert: {self.alert_type} - {self.priority}"

class Report(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    generated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='generated_reports')
    session = models.ForeignKey(Session, on_delete=models.CASCADE, null=True, blank=True, related_name='reports')
    report_type = models.CharField(max_length=50)  # session, daily, weekly
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    generated_at = models.DateTimeField(auto_now_add=True)
    file_path = models.CharField(max_length=500, blank=True)
    data_summary = models.JSONField(default=dict)
    
    class Meta:
        db_table = 'reports'
        ordering = ['-generated_at']
    
    def __str__(self):
        return f"Report {self.report_type} - {self.generated_at}"
    # ✅ Add these methods for PKT time display
    def get_formatted_generated_at(self):
        """Return generated_at in PKT format"""
        return self.generated_at.strftime('%b %d, %Y %I:%M %p')
    
    def get_formatted_start_date(self):
        """Return start_date in PKT format"""
        return self.start_date.strftime('%b %d, %Y %I:%M %p')
    
    def get_formatted_end_date(self):
        """Return end_date in PKT format"""
        return self.end_date.strftime('%b %d, %Y %I:%M %p')
    
    def get_date_range(self):
        """Return formatted date range"""
        return f"{self.start_date.strftime('%b %d, %Y %I:%M %p')} - {self.end_date.strftime('%b %d, %Y %I:%M %p')}"

class SystemLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=200)
    details = models.TextField()
    ip_address = models.GenericIPAddressField(null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'system_logs'
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.timestamp}: {self.action}"

class SystemConfiguration(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        db_table = 'system_configurations'
    
    def __str__(self):
        return f"{self.key}: {self.value}"
    from django.db import models
# Create your models here.
