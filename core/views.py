import json
import base64
import cv2
import numpy as np
from django.shortcuts import render, redirect, get_object_or_404 
    # from django.shortcuts import render

from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Count, Avg, Q
from datetime import datetime, timedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import pandas as pd
from io import BytesIO

from .models import User, Session, EmotionData, FocusData, Alert, Report, SystemLog, SystemConfiguration
from .forms import UserRegistrationForm, UserEditForm, LoginForm
from .decorators import role_required
from ai_models.emotion_model import EmotionDetector
from ai_models.focus_model import FocusAnalyzer, EngagementAnalyzer
from pathlib import Path
from django.conf import settings
backup_dir = settings.BASE_DIR / 'backups'
# from .models import Session, FocusData, EmotionData
#auto generate rpoert

import os 
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from django.conf import settings
from django.db.models import Avg

# Initialize AI models
emotion_detector = EmotionDetector(settings.EMOTION_MODEL_PATH)   # ← Yeh line
focus_analyzer = FocusAnalyzer()
engagement_analyzer = EngagementAnalyzer()

# Active sessions tracking
active_sessions = {}


def login_view(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')
    
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                if user.consent_given or user.role == 'admin':
                    login(request, user)
                    messages.success(request, f'Welcome back, {user.get_full_name()}!')
                    return redirect('core:dashboard')
                else:
                    return redirect('core:consent')
            else:
                # ✅ Overall alert ke liye
                messages.error(request, 'Invalid username or password.')
        else:
            # Field errors ke liye bhi messages (optional)
            for error in form.non_field_errors():
                messages.error(request, error)
    else:
        form = LoginForm() 
    return render(request, 'login.html', {'form': form})


def register_view(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password1'])   # ← 'password1' likho
            user.save()
            messages.success(request, 'Registration successful! Please log in.')
            return redirect('core:login')
        else:
            # Agar form invalid hai to errors show karo
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = UserRegistrationForm()    
    
    return render(request, 'register.html', {'form': form})  
@login_required
def consent_view(request):
    if request.method == 'POST':
        consent = request.POST.get('consent')
        if consent == 'yes':
            request.user.give_consent()
            messages.success(request, 'Thank you for providing consent.')
            return redirect('core:dashboard')
        else:
            messages.warning(request, 'Consent is required to use the system.')
    
    return render(request, 'consent.html')

@login_required
def dashboard_view(request):
    user = request.user
    
    if user.role == 'admin':
        return redirect('core:admin_dashboard')
    elif user.role == 'system_admin':
        return redirect('core:system_dashboard')
    else:
        # User dashboard
        recent_sessions = Session.objects.filter(user=user)[:5]
        
        # Har session ke liye average attention calculate karo
        for session in recent_sessions:
            avg = FocusData.objects.filter(session=session).aggregate(Avg('attention_score'))['attention_score__avg']
            session.avg_attention = avg if avg is not None else 0
        # Current active session ka data
        active_session = Session.objects.filter(user=user, status='active').first()
        current_attention = 0
        current_emotion = 'Neutral'
        
        if active_session:
            last_focus = FocusData.objects.filter(session=active_session).last()
            last_emotion = EmotionData.objects.filter(session=active_session).last()
            
            if last_focus:
                current_attention = last_focus.attention_score
            if last_emotion:
                current_emotion = last_emotion.emotion.capitalize()
        stats = {
            'total_sessions': Session.objects.filter(user=user).count(),
            'total_time': sum((s.duration().total_seconds() / 3600) 
                             for s in Session.objects.filter(user=user, status='completed')),
            'avg_attention': FocusData.objects.filter(
                session__user=user
            ).aggregate(Avg('attention_score'))['attention_score__avg'] or 0,
             # ✅ Add current metrics
            'current_attention': current_attention,
            'current_emotion': current_emotion,
            'active_session': active_session
        }
        # ----- 1. Weekly Performance Data (Last 7 days) -----
        today = timezone.now().date()
        week_start = today - timedelta(days=6)
        weekly_data = []
        for i in range(7):
            day = week_start + timedelta(days=i)
            sessions_day = user.sessions.filter(
                start_time__date=day,
                status='completed'
            )
            avg_focus = sessions_day.aggregate(Avg('focus_records__attention_score'))['focus_records__attention_score__avg']
            avg_engagement = sessions_day.aggregate(Avg('focus_records__engagement_score'))['focus_records__engagement_score__avg']
            weekly_data.append({
                'day': day.strftime('%a'),
                'focus': round(avg_focus, 1) if avg_focus else 0,
                'engagement': round(avg_engagement, 1) if avg_engagement else 0
            })
            print("WEEKLY DATA:", weekly_data)
        # ----- 2. Emotion Summary Data -----
        recent_sessions_for_emotion = user.sessions.filter(
            start_time__date__gte=week_start,
            status='completed'
        )
        emotion_counts = recent_sessions_for_emotion.values('emotions__emotion').annotate(total=Count('emotions__emotion'))
        
        emotion_labels = ['Happy', 'Neutral', 'Surprised', 'Sad', 'Fearful', 'Angry', 'Others']
        emotion_values = []
        for label in emotion_labels:
            count = next((item['total'] for item in emotion_counts if item['emotions__emotion'] == label.lower()), 0)
            emotion_values.append(count)
        
        has_emotion_data = any(v > 0 for v in emotion_values)

        return render(request, 'dashboard/user_dashboard.html', {
            'user': user,
            'recent_sessions': recent_sessions,
            'stats': stats,
            # naya add keya h
            'weekly_chart_data': json.dumps(weekly_data),
            'emotion_labels': json.dumps(emotion_labels),
            'emotion_values': json.dumps(emotion_values),
            'has_emotion_data': has_emotion_data,
        })
@login_required
@role_required(['admin'])
def admin_dashboard(request):
    # Get date range filter
    days = int(request.GET.get('days', 7))
    start_date = timezone.now() - timedelta(days=days)
    
    # Get all sessions in date range
    sessions = Session.objects.filter(start_time__gte=start_date)
    users = User.objects.filter(role='user')

     # ========== DEBUG PRINTS ==========
    print("="*50)
    print("Days:", days)
    print("Start date:", start_date)
    print("Total sessions in date range:", sessions.count())
    print("Active sessions in date range:", sessions.filter(status='active').count())

    # Calculate statistics
    stats = {
        'active_sessions': sessions.filter(status='active').count(),
        'total_sessions': sessions.count(),
        'active_users': users.filter(is_active=True).count(),
        'total_users': users.count(),
        'avg_attention': FocusData.objects.filter(
            session__start_time__gte=start_date
        ).aggregate(Avg('attention_score'))['attention_score__avg'] or 0,
    }
    
    # Emotion distribution
    emotion_dist = EmotionData.objects.filter(
        session__start_time__gte=start_date
    ).values('emotion').annotate(count=Count('id'))
    
    # Daily trends
    daily_trends = []
    for i in range(days):
        day_start = timezone.now() - timedelta(days=days-i)
        day_end = day_start + timedelta(days=1)
        day_sessions = Session.objects.filter(start_time__gte=day_start, start_time__lt=day_end)
        day_attention = FocusData.objects.filter(
            session__start_time__gte=day_start,
            session__start_time__lt=day_end
        ).aggregate(Avg('attention_score'))['attention_score__avg'] or 0
        
        daily_trends.append({
            'date': day_start.strftime('%Y-%m-%d'),
            'sessions': day_sessions.count(),
            'avg_attention': day_attention
        })
         # =========================================================
        print("RAW emotion_dist:", list(emotion_dist))
        print("RAW daily_trends:", daily_trends)
        # ========== SAMPLE DATA FOR TESTING (AGAR DATA NAHI HAI) ==========

    # Agar emotion_dist empty hai to sample data daalo
    
    if not emotion_dist:
        emotion_dist = [
            {'emotion': 'happy', 'count': 5},
            {'emotion': 'neutral', 'count': 8},
            {'emotion': 'sad', 'count': 3},
            {'emotion': 'angry', 'count': 2},
            {'emotion': 'surprised', 'count': 1},
        ]
        print("⚠️ Using sample emotion data (no real data found)")

    # Agar daily_trends empty hai to sample data daalo
    if not daily_trends or all(t['avg_attention'] == 0 for t in daily_trends):
        daily_trends = []
        for i in range(days):
            day = timezone.now() - timedelta(days=days-i-1)
            daily_trends.append({
                'date': day.strftime('%Y-%m-%d'),
                'sessions': i + 1,
                'avg_attention': 20 + (i * 5)  # 20, 25, 30, 35, 40, 45, 50
            })
        print("⚠️ Using sample daily trend data (no real data found)")
    # ================================================================
    # Recent alerts
    recent_alerts = Alert.objects.filter(
        session__start_time__gte=start_date,
        is_resolved=False
    )[:20]
    
    # Active sessions with real-time data
    active_sessions_data = []
    for session in sessions.filter(status='active')[:10]:
        print("Processing session:", session.id, session.user.username)
        last_focus = FocusData.objects.filter(session=session).last()
        last_emotion = EmotionData.objects.filter(session=session).last()   # ← YEH LINE ADD KARO
        
        active_sessions_data.append({
            'session': session,
            'user': session.user,
            'current_attention': last_focus.attention_score if last_focus else 0,
            'current_emotion': last_emotion.emotion if last_emotion else None,  # ← YEH LINE ADD KARO

            'duration': session.duration().total_seconds() / 60
        })
    print("active_sessions_data length:", len(active_sessions_data))
    return render(request, 'dashboard/admin_dashboard.html', {
        'stats': stats,
        'emotion_dist': list(emotion_dist),
        'daily_trends': daily_trends,
        'recent_alerts': recent_alerts,
        'active_sessions': active_sessions_data,
        'days': days
    })

@login_required
@role_required(['system_admin'])
def system_admin_dashboard(request):
    # System health metrics
    system_stats = {
        'total_users': User.objects.count(),
        'active_sessions': Session.objects.filter(status='active').count(),
        'total_sessions_today': Session.objects.filter(
            start_time__date=timezone.now().date()
        ).count(),
        'storage_used': '2.3 GB',  # Would calculate from actual storage
        'api_calls_today': 1245,
        'avg_response_time': '245ms'
    }
    
    # Recent system logs
    recent_logs = SystemLog.objects.all()[:50]
    
    # Database stats
    db_stats = {
        'sessions': Session.objects.count(),
        'emotion_records': EmotionData.objects.count(),
        'focus_records': FocusData.objects.count(),
        'alerts': Alert.objects.count(),
        'reports': Report.objects.count()
    }
    
    # Configuration
    configs = SystemConfiguration.objects.all()
    
    return render(request, 'dashboard/system_admin.html', {
        'system_stats': system_stats,
        'recent_logs': recent_logs,
        'db_stats': db_stats,
        'configs': configs
    })

@login_required
def start_session(request):
    if request.method == 'POST':
        analysis_mode = request.POST.get('analysis_mode', 'both')
        domain = request.POST.get('domain', 'education')
        session = Session.objects.create(
            user=request.user,
            domain=domain,
            analysis_mode=analysis_mode   # 🟢 YEH LINE ADD KARO
        )
        # Initialize session in active sessions dict
        active_sessions[str(session.id)] = {
            'session': session,
            'start_time': timezone.now(),
            'frame_count': 0,
            'last_alert_check': timezone.now()
        }
        
        messages.success(request, 'Session started successfully!')
        return redirect('core:realtime_analysis', session_id=session.id)
    
    return render(request, 'sessions/start_session.html')

@login_required
def realtime_analysis(request, session_id):
    session = get_object_or_404(Session, id=session_id, user=request.user)
    
    if session.status != 'active':
        messages.warning(request, 'This session has already ended.')
        return redirect('core:dashboard')
    
    return render(request, 'sessions/realtime_analysis.html', {
        'session': session
    })

@login_required
def end_session(request, session_id):
    session = get_object_or_404(Session, id=session_id, user=request.user)
    
    if session.status == 'active':
        session.end_session()
        
        # Remove from active sessions
        if str(session_id) in active_sessions:
            del active_sessions[str(session_id)]
        
        messages.success(request, 'Session ended successfully!')
        
        # Generate summary report
        auto_generate_report(session)
    
    return redirect('core:session_detail', session_id=session.id)
@csrf_exempt
@login_required
def analyze_frame_api(request):
    """API endpoint for real-time frame analysis"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        image_data = data.get('image')
        session_id = data.get('session_id')
        
        if not image_data or not session_id:
            return JsonResponse({'error': 'Missing image or session_id'}, status=400)
        
        # Decode base64 image
        image_bytes = base64.b64decode(image_data.split(',')[1])
        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        
        # ============================================
        # 1. Session fetch karo aur mode dekho
        # ============================================
        session = Session.objects.get(id=session_id)
        mode = session.analysis_mode
        
        # ============================================
        # 2. Face detection
        # ============================================
        faces = focus_analyzer.face_detector.detect_faces(frame) if hasattr(focus_analyzer, 'face_detector') else []
        face_detected = len(faces) > 0
        gaze_direction = 'center'  # Default value for gaze
        attention_score = 0
        is_focused = False
        head_pose = {'pitch': 0, 'yaw': 0, 'roll': 0}
        # faces = focus_analyzer.face_detector.detect_faces(frame) if hasattr(focus_analyzer, 'face_detector') else []
        # face_detected = len(faces) > 0
        
        # ============================================
        # 3. Focus analysis
        focus_result = None
        if mode in ['both', 'focus']:
            focus_result = focus_analyzer.analyze_frame(frame)
        else:
            focus_result = {
                'attention_score': 0,
                'gaze_direction': 'center',
                'head_pose': {'pitch': 0, 'yaw': 0, 'roll': 0},
                'is_focused': False,
                'face_detected': face_detected
            }
       #If  face detected, calculate metrics
        if face_detected:
            # Get largest face
            face = max(faces, key=lambda f: f[2] * f[3])
            x, y, w, h = face
            
            # Frame dimensions
            frame_height, frame_width = frame.shape[:2]
            frame_center_x = frame_width / 2
            frame_center_y = frame_height / 2
            
            # Face center
            face_center_x = x + w/2
            face_center_y = y + h/2
            # HEAD POSE CALCULATION (YEH NAYA HAI)
            # ============================================
            # Yaw: Left-Right movement (-30 to +30 degrees)
            yaw = ((face_center_x - frame_center_x) / frame_center_x) * 30
            yaw = max(-30, min(30, yaw))
            
            # Pitch: Up-Down movement (-20 to +20 degrees)
            pitch = ((face_center_y - frame_center_y) / frame_center_y) * 20
            pitch = max(-20, min(20, pitch))
            
            head_pose = {
                'pitch': round(pitch, 1),
                'yaw': round(yaw, 1),
                'roll': 0
            }
            
            # Gaze Direction from head pose
            if yaw < -10:
                gaze_direction = 'left'
            elif yaw > 10:
                gaze_direction = 'right'
            elif pitch < -10:
                gaze_direction = 'up'
            elif pitch > 10:
                gaze_direction = 'down'
            else:
                gaze_direction = 'center'
            
            # Attention Score
            distance_x = abs(face_center_x - frame_center_x) / frame_center_x
            distance_y = abs(face_center_y - frame_center_y) / frame_center_y
            distance = max(distance_x, distance_y)
            attention_score = max(0, 100 - (distance * 100))
            is_focused = attention_score > 60
            #YEH LINES ADD KAREIN (focus_result ko update karein)
            if focus_result:
                focus_result['head_pose'] = head_pose
                focus_result['gaze_direction'] = gaze_direction
                focus_result['attention_score'] = attention_score
                focus_result['is_focused'] = is_focused
        # ============================================
        # 4. Emotion detection
        # ============================================
        emotion = 'neutral'
        emotion_confidence = 0
        if face_detected and mode in ['both', 'emotion']:
            face = max(faces, key=lambda f: f[2] * f[3])
            x, y, w, h = face
            face_roi = frame[y:y+h, x:x+w]
            emotion, emotion_confidence = emotion_detector.detect_emotion(face_roi)
        
        # ============================================
        # 5. Engagement score
        # ============================================
        engagement = 0
        if mode in ['both', 'focus'] and focus_result and focus_result.get('attention_score', 0) > 0:
            engagement = engagement_analyzer.calculate_engagement_score(
                focus_result['attention_score'],
                emotion if mode == 'both' else 'neutral',
                emotion_confidence if mode == 'both' else 0
            )
            engagement_analyzer.engagement_history.append(engagement)
        
        # ============================================
        # 6. Save Focus Data
        # ============================================
        if mode in ['both', 'focus'] and focus_result and focus_result.get('attention_score', 0) > 0:
            FocusData.objects.create(
                session=session,
                attention_score=focus_result['attention_score'],
                gaze_direction=focus_result['gaze_direction'],
                head_pose=focus_result['head_pose'],
                is_focused=focus_result['is_focused'],
                engagement_score=engagement if engagement else None
            )
        
        # ============================================
        # 7. Save Emotion Data
        # ============================================
        if mode in ['both', 'emotion'] and face_detected:
            EmotionData.objects.create(
                session=session,
                emotion=emotion,
                confidence=emotion_confidence
            )
        
        # ============================================
        # 8. Alerts
        # ============================================
        alerts = []
        if mode in ['both', 'focus'] and focus_result:
            alerts = focus_analyzer.check_alert_conditions(
                focus_result['attention_score'],
                emotion if mode == 'both' else 'neutral'
            )
        elif mode == 'emotion' and face_detected:
            if emotion in ['angry', 'sad', 'fearful']:
                alerts.append({
                    'type': 'negative_emotion',
                    'message': f'Negative emotion detected: {emotion}',
                    'priority': 'medium'
                })
        for alert in alerts:
            Alert.objects.create(
                session=session,
                alert_type=alert['type'],
                message=alert['message'],
                priority=alert['priority']
            )
        
        # ============================================
        # 9. Response
        # ============================================
        # ✅ SIRF YE CHANGE KARO - float() aur bool() add karo
        return JsonResponse({
            'success': True,
            'attention_score': float(attention_score),                    # ✅ float() add
            'is_focused': bool(is_focused),                               # ✅ bool() add
            'gaze_direction': str(gaze_direction),                        # ✅ str() add
            'head_pose': head_pose,                                       # ✅ already ok
            'emotion': str(emotion),                                      # ✅ str() add
            'emotion_confidence': float(emotion_confidence),              # ✅ float() add
            'engagement_score': float(engagement),                        # ✅ float() add
            'alerts': alerts,
            'mode': str(mode),                                            # ✅ str() add
            'face_detected': bool(face_detected)                          # ✅ bool() add
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
@login_required
def session_detail(request, session_id):
    session = get_object_or_404(Session, id=session_id)
    
    # Check permission
    if request.user.role not in ['admin', 'system_admin'] and session.user != request.user:
        messages.error(request, 'You do not have permission to view this session.')
        return redirect('core:dashboard')
    
    # Get session data
    emotions = EmotionData.objects.filter(session=session)
    focus_records = FocusData.objects.filter(session=session)
    alerts = Alert.objects.filter(session=session)
    
    # ========== YEH NAYA CODE ADD KARO ==========
    # Focused percentage calculate karo
    total_records = focus_records.count()
    focused_records = focus_records.filter(is_focused=True).count()
    focused_percentage = (focused_records / total_records * 100) if total_records > 0 else 0
    # ============================================
    
    # Calculate statistics
    emotion_counts = {}
    for emotion_data in emotions:
        emotion_counts[emotion_data.emotion] = emotion_counts.get(emotion_data.emotion, 0) + 1
    
    avg_attention = focus_records.aggregate(Avg('attention_score'))['attention_score__avg'] or 0
    total_analysis = focus_records.count()
    
    # Time series data for charts
    time_series = []
    for i, record in enumerate(focus_records[:100]):
        time_series.append({
            'time': record.timestamp.strftime('%H:%M:%S'),
            'attention': record.attention_score
        })
    
    return render(request, 'sessions/session_report.html', {
        'session': session,
        'emotion_counts': emotion_counts,
        'avg_attention': avg_attention,
        'total_analysis': total_analysis,
        'alerts': alerts,
        'time_series': time_series,
        'focus_records': focus_records[:50],
        # ========== YEH DO NAYE VARIABLES ADD KARO ==========
        'total_records': total_records,
        'focused_records': focused_records,
        'focused_percentage': focused_percentage,
        # ====================================================
    })
@login_required
@role_required(['admin', 'system_admin'])
def generate_report(request):
    if request.method == 'POST':
        report_type = request.POST.get('report_type')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        user_id = request.POST.get('user_id')
        
        # Parse dates
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        
        # Build query
        sessions = Session.objects.filter(
            start_time__gte=start,
            start_time__lt=end,
            status='completed'
        )
        
        if user_id and user_id != 'all':
            sessions = sessions.filter(user_id=user_id)
        
        # Generate report
        report_data = generate_detailed_report(sessions, start, end, report_type)
        
        # Save report to database
        report = Report.objects.create(
            generated_by=request.user,
            report_type=report_type,
            start_date=start,
            end_date=end,
            data_summary=report_data['summary']
        )
        
        # Generate PDF
        pdf_buffer = create_pdf_report(report, report_data)
        
        # Save PDF
        report_path = f'reports/report_{report.id}.pdf'
        with open(f'media/{report_path}', 'wb') as f:
            f.write(pdf_buffer.getvalue())
        report.file_path = report_path
        report.save()
        
        messages.success(request, 'Report generated successfully!')
        return redirect('core:download_report', report_id=report.id)
    
    # GET request - show form
    users = User.objects.filter(role='user')
    return render(request, 'reports/generate_report.html', {
        'users': users
    })

@login_required
def download_report(request, report_id):
    report = get_object_or_404(Report, id=report_id)
    
    if report.file_path:
        with open(f'media/{report.file_path}', 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="report_{report_id}.pdf"'
            return response
    
    messages.error(request, 'Report file not found.')
    return redirect('core:reports')

def auto_generate_report(session):
    """Generate summary report for a session"""
    focus_records = FocusData.objects.filter(session=session)
    emotion_records = EmotionData.objects.filter(session=session)
    
    avg_attention = focus_records.aggregate(Avg('attention_score'))['attention_score__avg'] or 0
    
    emotion_summary = {}
    for emotion in emotion_records:
        emotion_summary[emotion.emotion] = emotion_summary.get(emotion.emotion, 0) + 1
    
    # Create report in database
    report = Report.objects.create(
        generated_by=session.user,
        session=session,
        report_type='session',
        start_date=session.start_time,
        end_date=session.end_time or timezone.now(),
        data_summary={
            'avg_attention': avg_attention,
            'emotion_summary': emotion_summary,
            'duration_minutes': session.duration().total_seconds() / 60,
            'total_alerts': Alert.objects.filter(session=session).count()
        }
    )
    
    # Generate PDF
    try:
        print(f"🔵 Generating PDF for report: {report.id}")
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor('#2c3e50'))
        story.append(Paragraph(f"Session Report - {session.start_time.strftime('%Y-%m-%d %H:%M')}", title_style))
        story.append(Spacer(1, 12))
        
        story.append(Paragraph(f"User: {session.user.get_full_name()}", styles['Normal']))
        story.append(Paragraph(f"Duration: {int(session.duration().total_seconds() / 60)} minutes", styles['Normal']))
        story.append(Paragraph(f"Average Focus: {avg_attention:.1f}%", styles['Normal']))
        story.append(Paragraph(f"Total Alerts: {Alert.objects.filter(session=session).count()}", styles['Normal']))
        story.append(Spacer(1, 12))
        
        if emotion_summary:
            story.append(Paragraph("Emotion Distribution:", styles['Heading2']))
            for emotion, count in emotion_summary.items():
                story.append(Paragraph(f"- {emotion.title()}: {count}", styles['Normal']))
        
        doc.build(story)
        buffer.seek(0)
        print("✅ PDF generated successfully!")
        
        # Save PDF
        report_dir = os.path.join(settings.MEDIA_ROOT, 'reports')
        print(f"🔵 Report Directory: {report_dir}")
        os.makedirs(report_dir, exist_ok=True)
        file_path = os.path.join(report_dir, f'report_{report.id}.pdf')
        print(f"🔵 File Path: {file_path}")
        
        with open(file_path, 'wb') as f:
            f.write(buffer.getvalue())
        print("✅ PDF saved successfully!")
        
        report.file_path = f'reports/report_{report.id}.pdf'
        report.save()
        print(f"✅ Report saved with file_path: {report.file_path}")
        
    except Exception as e:
        print(f"❌ ERROR in auto_generate_report: {e}")
        import traceback
        traceback.print_exc()
    
    return report

def generate_detailed_report(sessions, start_date, end_date, report_type):
    """Generate detailed analytics report"""
    total_sessions = sessions.count()
    total_users = sessions.values('user').distinct().count()
    
    # Overall attention
    focus_data = FocusData.objects.filter(session__in=sessions)
    avg_attention = focus_data.aggregate(Avg('attention_score'))['attention_score__avg'] or 0
    
    # Emotion distribution across all sessions
    emotion_data = EmotionData.objects.filter(session__in=sessions)
    emotion_dist = {}
    for emotion in emotion_data:
        emotion_dist[emotion.emotion] = emotion_dist.get(emotion.emotion, 0) + 1
    
    # Per-user statistics
    user_stats = []
    for user in User.objects.filter(sessions__in=sessions).distinct():
        user_sessions = sessions.filter(user=user)
        user_focus = FocusData.objects.filter(session__in=user_sessions)
        user_stats.append({
            'username': user.username,
            'full_name': user.get_full_name(),
            'session_count': user_sessions.count(),
            'avg_attention': user_focus.aggregate(Avg('attention_score'))['attention_score__avg'] or 0,
            'total_time': sum((s.duration().total_seconds() / 3600) for s in user_sessions)
        })
    
    return {
        'summary': {
            'total_sessions': total_sessions,
            'total_users': total_users,
            'date_range': f'{start_date.strftime("%Y-%m-%d")} to {end_date.strftime("%Y-%m-%d")}',
            'avg_attention': avg_attention,
            'total_analysis_records': focus_data.count()
        },
        'emotion_distribution': emotion_dist,
        'user_statistics': user_stats,
        'attention_trend': list(focus_data.values('timestamp', 'attention_score')[:100])
    }

def create_pdf_report(report, report_data):
    """Create PDF report using ReportLab"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=30
    )
    story.append(Paragraph(f"AI Micro-Behavior Analyzer Report", title_style))
    story.append(Spacer(1, 12))
    
    # Report Info
    info_style = ParagraphStyle('Info', parent=styles['Normal'], fontSize=10)
    story.append(Paragraph(f"Report Type: {report.report_type}", info_style))
    story.append(Paragraph(f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M')}", info_style))
    story.append(Paragraph(f"Date Range: {report.start_date.strftime('%Y-%m-%d')} to {report.end_date.strftime('%Y-%m-%d')}", info_style))
    story.append(Spacer(1, 20))
    
    # Summary Table
    summary_data = report_data['summary']
    summary_table_data = [
        ['Metric', 'Value'],
        ['Total Sessions', str(summary_data['total_sessions'])],
        ['Total Users', str(summary_data['total_users'])],
        ['Average Attention Score', f"{summary_data['avg_attention']:.1f}%"],
        ['Total Analysis Records', str(summary_data['total_analysis_records'])],
    ]
    
    summary_table = Table(summary_table_data, colWidths=[200, 150])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 20))
    
    # Emotion Distribution
    story.append(Paragraph("Emotion Distribution", styles['Heading2']))
    story.append(Spacer(1, 10))
    
    emotion_data = [[emotion.upper(), str(count)] for emotion, count in report_data['emotion_distribution'].items()]
    emotion_data.insert(0, ['Emotion', 'Count'])
    emotion_table = Table(emotion_data, colWidths=[200, 150])
    emotion_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    story.append(emotion_table)
    
    doc.build(story)
    buffer.seek(0)
    return buffer
@login_required
def get_session_stats(request, session_id):
    """API endpoint to get session statistics"""
    try:
        session = Session.objects.get(id=session_id)
        focus_data = FocusData.objects.filter(session=session)
        emotion_data = EmotionData.objects.filter(session=session)
        
        stats = {
            'session_id': str(session.id),
            'duration_minutes': session.duration().total_seconds() / 60,
            'avg_attention': focus_data.aggregate(Avg('attention_score'))['attention_score__avg'] or 0,
            'total_frames': focus_data.count(),
            'emotion_counts': {},
        }
        
        for emotion in emotion_data:
            stats['emotion_counts'][emotion.emotion] = stats['emotion_counts'].get(emotion.emotion, 0) + 1
        
        return JsonResponse({'success': True, 'stats': stats})
    except Session.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)

@login_required
def get_dashboard_data(request):
    """API endpoint to get dashboard data for admin"""
    try:
        days = int(request.GET.get('days', 7))
        start_date = timezone.now() - timedelta(days=days)
        sessions = Session.objects.filter(start_time__gte=start_date)
        
        stats = {
            'active_sessions': sessions.filter(status='active').count(),
            'total_sessions': sessions.count(),
            'active_users': User.objects.filter(is_active=True, role='user').count(),
            'total_users': User.objects.filter(role='user').count(),
            'avg_attention': FocusData.objects.filter(
                session__start_time__gte=start_date
            ).aggregate(Avg('attention_score'))['attention_score__avg'] or 0,
        }
        
        emotion_data = EmotionData.objects.filter(
            session__start_time__gte=start_date
        ).values('emotion').annotate(count=Count('id'))
        emotion_dist = list(emotion_data)
        
        daily_trends = []
        for i in range(days):
            day_start = timezone.now() - timedelta(days=days-i-1)
            day_end = day_start + timedelta(days=1)
            day_sessions = Session.objects.filter(
                start_time__gte=day_start, 
                start_time__lt=day_end
            )
            day_attention = FocusData.objects.filter(
                session__start_time__gte=day_start,
                session__start_time__lt=day_end
            ).aggregate(Avg('attention_score'))['attention_score__avg'] or 0
            
            daily_trends.append({
                'date': day_start.strftime('%Y-%m-%d'),
                'sessions': day_sessions.count(),
                'avg_attention': day_attention
            })
        
        recent_alerts = list(Alert.objects.filter(
            session__start_time__gte=start_date,
            is_resolved=False
        ).values('id', 'alert_type', 'message', 'priority', 'timestamp')[:20])
        
        for alert in recent_alerts:
            alert['timestamp'] = alert['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        
        return JsonResponse({
            'success': True,
            'stats': stats,
            'emotion_distribution': emotion_dist,
            'daily_trends': daily_trends,
            'recent_alerts': recent_alerts
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def reports_view(request):    
    """View to show all reports"""
    # Get all reports
    if request.user.role in ['admin', 'system_admin']:
        reports = Report.objects.all()
    else:
        reports = Report.objects.filter(generated_by=request.user)
    
    # Filter by date if provided
    date_filter = request.GET.get('date_filter')
    if date_filter == 'today':
        reports = reports.filter(generated_at__date=timezone.now().date())
    elif date_filter == 'week':
        week_ago = timezone.now() - timedelta(days=7)
        reports = reports.filter(generated_at__gte=week_ago)
    elif date_filter == 'month':
        month_ago = timezone.now() - timedelta(days=30)
        reports = reports.filter(generated_at__gte=month_ago)
    
    # Pagination
    paginator = Paginator(reports.order_by('-generated_at'), 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'reports/reports_list.html', {
        'reports': page_obj,
        'date_filter': date_filter
    })
@login_required
def profile_view(request):
    """Simple profile view"""
    return render(request, 'profile.html', {'user': request.user})

@login_required
def sessions_view(request):
    sessions = Session.objects.filter(user=request.user).order_by('-start_time')
    
    for session in sessions:
        # Avg Focus
        avg = FocusData.objects.filter(session=session).aggregate(Avg('attention_score'))['attention_score__avg']
        session.avg_attention = avg if avg is not None else 0
        
        # Duration in minutes
        if session.end_time:
            duration_seconds = (session.end_time - session.start_time).total_seconds()
            session.duration_minutes = int(duration_seconds / 60)
        else:
            session.duration_minutes = 0
    
    return render(request, 'sessions/sessions_list.html', {'sessions': sessions})

    # sessions = Session.objects.filter(user=request.user).order_by('-start_time')
    # return render(request, 'sessions/sessions_list.html', {'sessions': sessions})
@login_required
def export_session_data(request, session_id):
    """Export session data as CSV"""
    import csv
    from django.http import HttpResponse
    
    session = get_object_or_404(Session, id=session_id)
    focus_data = FocusData.objects.filter(session=session)
    emotion_data = EmotionData.objects.filter(session=session)
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="session_{session_id}_data.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Timestamp', 'Attention Score', 'Gaze Direction', 'Is Focused', 'Emotion', 'Emotion Confidence'])
    
    # Combine focus and emotion data (by timestamp)
    focus_list = list(focus_data)
    emotion_list = list(emotion_data)
    
    for i, focus in enumerate(focus_list):
        emotion = emotion_list[i] if i < len(emotion_list) else None
        writer.writerow([
            focus.timestamp, 
            focus.attention_score, 
            focus.gaze_direction, 
            focus.is_focused,
            emotion.emotion if emotion else '',
            emotion.confidence if emotion else ''
        ])
    
    return response
@login_required
@role_required(['admin', 'system_admin'])
def alerts_view(request):
    """View to show all alerts"""
    alerts = Alert.objects.all().order_by('-timestamp')
    
    # Filter by status
    status = request.GET.get('status')
    if status == 'resolved':
        alerts = alerts.filter(is_resolved=True)
    elif status == 'unresolved':
        alerts = alerts.filter(is_resolved=False)
    
    # Filter by priority
    priority = request.GET.get('priority')
    if priority:
        alerts = alerts.filter(priority=priority)
    
    # Pagination
    paginator = Paginator(alerts, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'admin/alerts_list.html', {
        'alerts': page_obj,
        'status': status,
        'priority': priority
    })

@login_required
@role_required(['admin', 'system_admin'])
def resolve_alert(request, alert_id):
    """Mark alert as resolved"""
    alert = get_object_or_404(Alert, id=alert_id)
    if request.method == 'POST':
        alert.is_resolved = True
        alert.resolved_at = timezone.now()
        alert.save()
        messages.success(request, 'Alert resolved successfully!')
    return redirect('core:alerts')
@login_required
def user_sessions_api(request, user_id):
    """API to get user sessions for dropdown"""
    if request.user.role not in ['admin', 'system_admin']:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    user = get_object_or_404(User, id=user_id)
    sessions = Session.objects.filter(user=user).order_by('-start_time')
    
    data = {
        'sessions': [{
            'id': str(session.id),
            'date': session.start_time.strftime('%Y-%m-%d %H:%M'),
            'duration': session.duration().total_seconds() // 60
        } for session in sessions]
    }
    return JsonResponse(data)

@login_required
def recent_reports_api(request):
    """API to get recent reports"""
    reports = Report.objects.filter(generated_by=request.user).order_by('-generated_at')[:5]
    
    data = {
        'reports': [{
            'id': str(report.id),
            'date': report.generated_at.strftime('%Y-%m-%d %H:%M'),
            'type': report.report_type,
            'format': 'PDF'
        } for report in reports]
    }
    return JsonResponse(data)
# ==================== SYSTEM ADMIN APIs ====================

@login_required
@role_required(['system_admin'])
def system_stats_api(request):
    """API to get system statistics for system admin dashboard"""
    try:
        stats = {
            'active_sessions': Session.objects.filter(status='active').count(),
            'api_calls_today': SystemLog.objects.filter(
                action__icontains='API',
                timestamp__date=timezone.now().date()
            ).count(),
            'avg_response_time': '245ms',
            'storage_used': '2.3 GB',
            'storage_used_percent': 28,
            'cpu_usage': 45,
            'memory_usage': 62,
            'gpu_usage': 35,
            'uptime': '14 days, 6 hours',
            'last_backup': '2024-01-15 03:00 AM'
        }
        return JsonResponse({'success': True, 'stats': stats})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@role_required(['system_admin'])
def backup_database_api(request):
    """API to backup database"""
    import shutil
    import zipfile
    from django.conf import settings  # ✅ YEH IMPORT KARO
    from pathlib import Path   
    
    try:
        data = json.loads(request.body)
        include_media = data.get('include_media', False)
        
        # Create backup directory if not exists
        backup_dir = settings.BASE_DIR / 'backups'
        backup_dir.mkdir(exist_ok=True)
        # Backup SQLite database
        db_path = settings.DATABASES['default']['NAME']
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        backup_file = backup_dir / f'backup_{timestamp}.db'
        shutil.copy2(db_path, backup_file)
        
        # Create zip file
        zip_path = backup_dir / f'backup_{timestamp}.zip'
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            zipf.write(backup_file, arcname='database.sqlite3')
            if include_media:
                media_dir = settings.BASE_DIR / 'media'
                if media_dir.exists():
                    for file in media_dir.rglob('*'):
                        if file.is_file():
                            zipf.write(file, arcname=str(file.relative_to(BASE_DIR)))
        
        # Delete temporary db backup
        backup_file.unlink()
        
        # Log the backup action
        SystemLog.objects.create(
            user=request.user,
            action='Database Backup',
            details=f'Backup created: {zip_path.name}',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({'success': True, 'backup_file': str(zip_path)})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@role_required(['system_admin'])
def restart_services_api(request):
    """API to restart AI services"""
    try:
        # Re-initialize AI models
        global emotion_detector, focus_analyzer, engagement_analyzer
        emotion_detector = EmotionDetector(settings.EMOTION_MODEL_PATH)
        focus_analyzer = FocusAnalyzer()
        engagement_analyzer = EngagementAnalyzer()
        
        # Clear active sessions
        global active_sessions
        active_sessions.clear()
        
        SystemLog.objects.create(
            user=request.user,
            action='Restart Services',
            details='AI services restarted successfully',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({'success': True, 'message': 'Services restarted successfully'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@role_required(['system_admin'])
def clear_cache_api(request):
    """API to clear system cache"""
    try:
        from django.core.cache import cache
        cache.clear()
        
        SystemLog.objects.create(
            user=request.user,
            action='Clear Cache',
            details='System cache cleared',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({'success': True, 'message': 'Cache cleared successfully'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@role_required(['system_admin'])
def diagnostics_api(request):
    """API to run system diagnostics"""
    try:
        from django.db import connections
        from django.db.utils import OperationalError
        
        
        # Check database
        db_conn = False
        try:
            connections['default'].cursor()
            db_conn = True
        except OperationalError:
            db_conn = False
        
        # Check Redis (if configured)
        redis_conn = False
        try:
            import redis
            r = redis.Redis(host='localhost', port=6379, decode_responses=True)
            r.ping()
            redis_conn = True
        except:
            redis_conn = False
        
        # Check AI models
        ai_models_loaded = emotion_detector.model is not None
        
        # Check storage
        import shutil
        total, used, free = shutil.disk_usage(settings.BASE_DIR)
        storage_status = f"Free: {free // (2**30)} GB, Total: {total // (2**30)} GB"
        
        return JsonResponse({
            'success': True,
            'database': db_conn,
            'redis': redis_conn,
            'ai_models': ai_models_loaded,
            'storage_status': storage_status
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@role_required(['system_admin'])
def system_config_api(request):
    """API to save system configuration"""
    try:
        data = json.loads(request.body)
        
        # Save configurations to database
        configs = {
            'attention_threshold': data.get('attention_threshold', '70'),
            'alert_cooldown': data.get('alert_cooldown', '30'),
            'max_concurrent_sessions': data.get('max_sessions', '50'),
            'frame_processing_interval': data.get('frame_interval', '1.0'),
            'low_memory_mode': data.get('low_memory', 'false')
        }
        
        for key, value in configs.items():
            SystemConfiguration.objects.update_or_create(
                key=key,
                defaults={'value': value, 'updated_by': request.user}
            )
        
        SystemLog.objects.create(
            user=request.user,
            action='Update Configuration',
            details=f'Updated {len(configs)} configuration items',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({'success': True, 'message': 'Configuration saved successfully'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@role_required(['system_admin'])
def clear_logs_api(request):
    """API to clear system logs"""
    try:
        # Keep only last 100 logs
        logs_to_delete = SystemLog.objects.all().order_by('-timestamp')[100:]
        deleted_count = logs_to_delete.count()
        logs_to_delete.delete()
        
        SystemLog.objects.create(
            user=request.user,
            action='Clear Logs',
            details=f'Deleted {deleted_count} old logs',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({'success': True, 'message': f'Deleted {deleted_count} old logs'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@role_required(['system_admin'])
def download_logs_api(request):
    """API to download system logs as CSV"""
    import csv
    
    logs = SystemLog.objects.all().order_by('-timestamp')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="system_logs.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Timestamp', 'User', 'Action', 'Details', 'IP Address'])
    
    for log in logs:
        writer.writerow([
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            log.user.username if log.user else 'System',
            log.action,
            log.details,
            log.ip_address or '-'
        ])
    
    return response

    # User Management (Admin only)
@login_required
@role_required(['admin', 'system_admin'])
def user_management(request):
    """View to manage all users"""
    users = User.objects.all().order_by('-date_joined')
    paginator = Paginator(users, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'admin/user_management.html', {'users': page_obj})

@login_required
@role_required(['admin', 'system_admin'])
def add_user(request):
    """Add a new user"""
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'User {user.username} created successfully!')
            return redirect('core:user_management')
    else:
        form = UserRegistrationForm()
    return render(request, 'admin/user_form.html', {'form': form, 'title': 'Add User'})

@login_required
@role_required(['admin', 'system_admin'])
def edit_user(request, user_id):
    """Edit an existing user"""
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f'User {user.username} updated successfully!')
            return redirect('core:user_management')
    else:
        form = UserEditForm(instance=user)
    return render(request, 'admin/user_form.html', {'form': form, 'title': 'Edit User', 'user': user})

@login_required
@role_required(['admin', 'system_admin'])
def delete_user(request, user_id):
    """Delete a user"""
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f'User {username} deleted successfully!')
        return redirect('core:user_management')
    return render(request, 'admin/user_confirm_delete.html', {'user': user})
# System Configuration (System Admin only)
@login_required
@role_required(['system_admin'])
def system_config(request):
    """System configuration view"""
    configs = SystemConfiguration.objects.all()
    if request.method == 'POST':
        for config in configs:
            new_value = request.POST.get(f'config_{config.id}')
            if new_value:
                config.value = new_value
                config.updated_by = request.user
                config.save()
        messages.success(request, 'Configuration updated successfully!')
        return redirect('core:system_config')
    return render(request, 'admin/system_config.html', {'configs': configs})

@login_required
@role_required(['system_admin'])
def system_logs(request):
    """System logs view"""
    logs = SystemLog.objects.all().order_by('-timestamp')
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'admin/system_logs.html', {'logs': page_obj})

@login_required
@role_required(['system_admin'])
def backup_database(request):
    """Backup database"""
    import shutil    
    try:
        db_path = settings.DATABASES['default']['NAME']
        backup_dir = settings.BASE_DIR / 'backups'
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        backup_file = backup_dir / f'backup_{timestamp}.sqlite3'
        shutil.copy2(db_path, backup_file)
        
        messages.success(request, f'Backup created: {backup_file.name}')
    except Exception as e:
        messages.error(request, f'Backup failed: {str(e)}')
    
    return redirect('core:system_dashboard')