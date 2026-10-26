import numpy as np
import cv2
from collections import deque
import time
from .face_utils import FaceDetector, GazeTracker, HeadPoseEstimator

class FocusAnalyzer:
    """Real-time focus and attention analysis"""
    
    def __init__(self):
        self.face_detector = FaceDetector()
        self.gaze_tracker = GazeTracker()
        self.head_pose_estimator = HeadPoseEstimator()
        
        # Rolling window for attention scores
        self.attention_window = deque(maxlen=30)  # Last 30 seconds of data
        self.emotion_window = deque(maxlen=30)
        
        # Thresholds
        self.attention_threshold = 70  # 70% minimum for "focused"
        
        # State tracking
        self.last_alert_time = 0
        self.alert_cooldown = 30  # seconds between same-type alerts
        
    def analyze_frame(self, frame: np.ndarray) -> dict:
        """Analyze a single frame for focus and emotion"""
        result = {
            'face_detected': False,
            'attention_score': 0,
            'gaze_direction': 'unknown',
            'head_pose': {'pitch': 0, 'yaw': 0, 'roll': 0},
            'is_focused': False,
            'emotion': 'neutral',
            'emotion_confidence': 0
        }
        
        # Detect faces
        faces = self.face_detector.detect_faces(frame)
        
        if len(faces) == 0:
            result['attention_score'] = 0
            result['is_focused'] = False
            return result
        
        # Process the largest face (main user)
        face = max(faces, key=lambda f: f[2] * f[3])
        x, y, w, h = face
        face_roi = frame[y:y+h, x:x+w]
        
        result['face_detected'] = True
        
        # Get facial landmarks
        landmarks = self.face_detector.get_face_landmarks(frame, face)
        
        # Estimate head pose
        if landmarks:
            head_pose = self.head_pose_estimator.estimate_pose(landmarks, frame.shape)
            result['head_pose'] = head_pose
        
        # Estimate gaze
        gaze = self.gaze_tracker.estimate_gaze(frame, face)
        result['gaze_direction'] = gaze
        
        # Calculate attention score
        attention_score = self.gaze_tracker.calculate_attention_score(gaze, result['head_pose'])
        result['attention_score'] = attention_score
        result['is_focused'] = attention_score >= self.attention_threshold
        
        # Add to rolling window
        self.attention_window.append(attention_score)
        
        return result
    
    def get_average_attention(self) -> float:
        """Get average attention score from rolling window"""
        if len(self.attention_window) == 0:
            return 0
        return sum(self.attention_window) / len(self.attention_window)
    
    def check_alert_conditions(self, current_score: float, emotion: str) -> dict:
        """Check if conditions warrant an alert"""
        current_time = time.time()
        alerts = []
        
        # Check low attention
        if current_score < 50:
            if current_time - self.last_alert_time > self.alert_cooldown:
                alerts.append({
                    'type': 'low_focus',
                    'priority': 'high',
                    'message': f'Attention score dropped to {current_score:.1f}%'
                })
                self.last_alert_time = current_time
        
        # Check negative emotions
        negative_emotions = ['angry', 'sad', 'fearful', 'disgusted']
        if emotion in negative_emotions:
            alerts.append({
                'type': 'negative_emotion',
                'priority': 'medium',
                'message': f'Negative emotion detected: {emotion}'
            })
        
        return alerts
    
    def reset(self):
        """Reset analyzer state for new session"""
        self.attention_window.clear()
        self.emotion_window.clear()
        self.last_alert_time = 0

class EngagementAnalyzer:
    """Analyze overall engagement using multiple metrics"""
    
    def __init__(self):
        self.focus_analyzer = FocusAnalyzer()
        self.engagement_history = deque(maxlen=300)  # 5 minutes at 1fps
        
    def calculate_engagement_score(self, attention_score: float, 
                                   emotion: str, 
                                   confidence: float) -> float:
        """Calculate composite engagement score"""
        # Base weight: attention is 60% of engagement
        engagement = attention_score * 0.6
        
        # Emotion contribution: positive emotions increase engagement
        positive_emotions = ['happy', 'surprised']
        if emotion in positive_emotions:
            engagement += 15 * confidence
        elif emotion == 'neutral':
            engagement += 5 * confidence
        else:
            engagement -= 10 * confidence
        
        # Confidence penalty
        if confidence < 0.5:
            engagement -= 10
        
        return max(0, min(100, engagement))
    
    def get_engagement_trend(self) -> str:
        """Determine engagement trend based on recent history"""
        if len(self.engagement_history) < 10:
            return 'stable'
        
        recent = list(self.engagement_history)[-10:]
        first_half = sum(recent[:5]) / 5
        second_half = sum(recent[5:]) / 5
        
        if second_half > first_half + 10:
            return 'improving'
        elif second_half < first_half - 10:
            return 'declining'
        else:
            return 'stable'
    
    def generate_insights(self) -> dict:
        """Generate insights from engagement data"""
        if len(self.engagement_history) == 0:
            return {}
        
        avg_engagement = sum(self.engagement_history) / len(self.engagement_history)
        
        insights = {
            'average_engagement': avg_engagement,
            'trend': self.get_engagement_trend(),
            'consistency': np.std(list(self.engagement_history)) if len(self.engagement_history) > 1 else 0
        }
        
        # Add recommendations
        if avg_engagement < 50:
            insights['recommendations'] = [
                'Student shows low engagement levels',
                'Consider interactive activities',
                'Take a short break'
            ]
        elif avg_engagement < 70:
            insights['recommendations'] = [
                'Engagement is moderate',
                'Add more interactive elements',
                'Check for distractions'
            ]
        else:
            insights['recommendations'] = [
                'Good engagement level maintained',
                'Continue current teaching approach'
            ]
        
        return insights