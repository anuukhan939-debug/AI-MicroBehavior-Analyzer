import cv2
import numpy as np
import dlib
from typing import Tuple, Dict, Optional

class FaceDetector:
    """Face detection and landmark extraction utility"""
    
    def __init__(self):
        # Initialize face detector
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        # Initialize dlib's face detector and landmark predictor
        self.detector = dlib.get_frontal_face_detector()
        try:
            self.predictor = dlib.shape_predictor('shape_predictor_68_face_landmarks.dat')
        except:
            print("Warning: shape_predictor not found. Using basic detection only.")
            self.predictor = None
        
    def detect_faces(self, frame: np.ndarray) -> list:
        """Detect all faces in frame"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.1, 5)
        return faces
    
    def get_face_landmarks(self, frame: np.ndarray, face_rect: Tuple) -> Optional[Dict]:
        """Get 68 facial landmarks for a face"""
        if self.predictor is None:
            return None
            
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        x, y, w, h = face_rect
        dlib_rect = dlib.rectangle(int(x), int(y), int(x + w), int(y + h))
        
        try:
            landmarks = self.predictor(gray, dlib_rect)
            points = {}
            for i in range(68):
                points[i] = (landmarks.part(i).x, landmarks.part(i).y)
            return points
        except:
            return None
    
    def get_eye_regions(self, landmarks: Dict) -> Tuple:
        """Extract left and right eye regions from landmarks"""
        if not landmarks:
            return None, None
            
        # Left eye indices: 36-41
        left_eye = np.array([landmarks[i] for i in range(36, 42)])
        # Right eye indices: 42-47
        right_eye = np.array([landmarks[i] for i in range(42, 48)])
        
        return left_eye, right_eye

class GazeTracker:
    """Eye gaze tracking for attention analysis"""
    
    def __init__(self):
        self.face_detector = FaceDetector()
        
    def eye_aspect_ratio(self, eye_points: np.ndarray) -> float:
        """Calculate Eye Aspect Ratio (EAR) for blink detection"""
        # Vertical distances
        A = np.linalg.norm(eye_points[1] - eye_points[5])
        B = np.linalg.norm(eye_points[2] - eye_points[4])
        # Horizontal distance
        C = np.linalg.norm(eye_points[0] - eye_points[3])
        
        ear = (A + B) / (2.0 * C)
        return ear
    
    def estimate_gaze(self, frame: np.ndarray, face_rect: Tuple) -> str:
        """Estimate gaze direction based on pupil position"""
        x, y, w, h = face_rect
        face_center_x = x + w // 2
        face_center_y = y + h // 2
        
        # Detect eyes (simplified - using face proportions)
        left_eye_region = frame[y + h//3:y + h//2, x + w//4:x + w//2]
        right_eye_region = frame[y + h//3:y + h//2, x + w//2:x + 3*w//4]
        
        # Estimate gaze based on face orientation
        # This is simplified; for production, use more sophisticated methods
        
        return "center"  # Default return
    
    def calculate_attention_score(self, gaze_direction: str, head_pose: Dict) -> float:
        """Calculate attention score based on gaze and head pose"""
        score = 100.0
        
        # Penalize based on gaze direction
        if gaze_direction != "center":
            score -= 30
        elif gaze_direction in ["left", "right"]:
            score -= 20
        elif gaze_direction in ["up", "down"]:
            score -= 10
        
        # Penalize based on head pose
        if abs(head_pose.get('yaw', 0)) > 20:
            score -= 20
        if abs(head_pose.get('pitch', 0)) > 15:
            score -= 15
        if abs(head_pose.get('roll', 0)) > 15:
            score -= 10
        
        return max(0, min(100, score))

class HeadPoseEstimator:
    """Head pose estimation using facial landmarks"""
    
    def __init__(self):
        # 3D model points of facial landmarks
        self.model_points = np.array([
            (0.0, 0.0, 0.0),          # Nose tip
            (0.0, -330.0, -65.0),      # Chin
            (-225.0, 170.0, -135.0),   # Left eye left corner
            (225.0, 170.0, -135.0),    # Right eye right corner
            (-150.0, -150.0, -125.0),  # Left mouth corner
            (150.0, -150.0, -125.0)    # Right mouth corner
        ])
        
        # Camera internals
        self.focal_length = 320
        self.center = (320, 240)
        self.camera_matrix = np.array(
            [[self.focal_length, 0, self.center[0]],
             [0, self.focal_length, self.center[1]],
             [0, 0, 1]], dtype="double"
        )
        self.dist_coeffs = np.zeros((4, 1))
        
    def estimate_pose(self, landmarks: Dict, frame_shape: Tuple) -> Dict:
        """Estimate head pose angles (pitch, yaw, roll)"""
        if not landmarks or len(landmarks) < 68:
            return {'pitch': 0, 'yaw': 0, 'roll': 0}
        
        # Get relevant landmarks
        image_points = np.array([
            landmarks[30],      # Nose tip
            landmarks[8],       # Chin
            landmarks[36],      # Left eye left corner
            landmarks[45],      # Right eye right corner
            landmarks[48],      # Left mouth corner
            landmarks[54]       # Right mouth corner
        ], dtype="double")
        
        # Solve PnP
        try:
            success, rotation_vector, translation_vector = cv2.solvePnP(
                self.model_points, image_points, self.camera_matrix, self.dist_coeffs
            )
            
            # Convert rotation vector to rotation matrix
            rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
            
            # Get euler angles
            sy = np.sqrt(rotation_matrix[0,0]**2 + rotation_matrix[1,0]**2)
            singular = sy < 1e-6
            
            if not singular:
                pitch = np.arctan2(-rotation_matrix[2,0], sy)
                yaw = np.arctan2(rotation_matrix[1,0], rotation_matrix[0,0])
                roll = np.arctan2(rotation_matrix[2,1], rotation_matrix[2,2])
            else:
                pitch = np.arctan2(-rotation_matrix[2,0], sy)
                yaw = 0
                roll = np.arctan2(rotation_matrix[1,2], rotation_matrix[1,1])
            
            # Convert to degrees
            pitch = np.degrees(pitch)
            yaw = np.degrees(yaw)
            roll = np.degrees(roll)
            
            return {'pitch': pitch, 'yaw': yaw, 'roll': roll}
            
        except:
            return {'pitch': 0, 'yaw': 0, 'roll': 0}