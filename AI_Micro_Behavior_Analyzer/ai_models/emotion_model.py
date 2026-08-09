import cv2
import numpy as np
import tensorflow as tf
# from tensorflow import keras
import tensorflow.keras as keras
from tensorflow.keras import layers
import pickle
import os
from pathlib import Path

class EmotionDetector:
    """CNN-based emotion detection from facial expressions"""
    
    def __init__(self, model_path=None):
        self.emotion_labels = ['angry', 'disgusted', 'fearful', 'happy', 'sad', 'surprised', 'neutral']
        self.input_shape = (48, 48, 1)
        self.model = None
        
        if model_path and os.path.exists(model_path):
            self.load_model(model_path)
        else:
            self.build_model()
    
    def build_model(self):
        """Build CNN model for emotion detection"""
        model = keras.Sequential([
            # First convolutional block
            layers.Conv2D(64, (3, 3), activation='relu', input_shape=self.input_shape),
            layers.BatchNormalization(),
            layers.MaxPooling2D((2, 2)),
            layers.Dropout(0.25),
            
            # Second convolutional block
            layers.Conv2D(128, (3, 3), activation='relu'),
            layers.BatchNormalization(),
            layers.MaxPooling2D((2, 2)),
            layers.Dropout(0.25),
            
            # Third convolutional block
            layers.Conv2D(256, (3, 3), activation='relu'),
            layers.BatchNormalization(),
            layers.MaxPooling2D((2, 2)),
            layers.Dropout(0.25),
            
            # Fourth convolutional block
            layers.Conv2D(512, (3, 3), activation='relu'),
            layers.BatchNormalization(),
            layers.MaxPooling2D((2, 2)),
            layers.Dropout(0.25),
            
            # Fully connected layers
            layers.Flatten(),
            layers.Dense(256, activation='relu'),
            layers.BatchNormalization(),
            layers.Dropout(0.5),
            layers.Dense(7, activation='softmax')
        ])
        
        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=0.0001),
            loss='categorical_crossentropy',
            metrics=['accuracy']
        )
        
        self.model = model
        return model
    
    def preprocess_face(self, face_img: np.ndarray) -> np.ndarray:
        """Preprocess face image for emotion detection"""
        # Convert to grayscale if needed
        if len(face_img.shape) == 3:
            gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
        else:
            gray = face_img
        
        # Resize to 48x48
        resized = cv2.resize(gray, (48, 48))
        
        # Normalize pixel values
        normalized = resized / 255.0
        
        # Reshape for model input
        reshaped = normalized.reshape(1, 48, 48, 1)
        
        return reshaped
    
    def detect_emotion(self, face_img: np.ndarray) -> tuple:
        """Detect emotion from face image"""
        if face_img is None or face_img.size == 0:
            return 'neutral', 0.0
        
        try:
            processed = self.preprocess_face(face_img)
            predictions = self.model.predict(processed, verbose=0)
            emotion_idx = np.argmax(predictions[0])
            confidence = float(predictions[0][emotion_idx])
            
            return self.emotion_labels[emotion_idx], confidence
            
        except Exception as e:
            print(f"Emotion detection error: {e}")
            return 'neutral', 0.0
    
    def train_model(self, X_train, y_train, X_val, y_val, epochs=50):
        """Train the emotion detection model"""
        # Convert labels to categorical
        y_train_cat = keras.utils.to_categorical(y_train, 7)
        y_val_cat = keras.utils.to_categorical(y_val, 7)
        
        # Callbacks
        callbacks = [
            keras.callbacks.EarlyStopping(
                monitor='val_loss',
                patience=10,
                restore_best_weights=True
            ),
            keras.callbacks.ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=5,
                min_lr=0.00001
            ),
            keras.callbacks.ModelCheckpoint(
                'best_emotion_model.h5',
                monitor='val_accuracy',
                save_best_only=True
            )
        ]
        
        # Train
        history = self.model.fit(
            X_train, y_train_cat,
            validation_data=(X_val, y_val_cat),
            epochs=epochs,
            batch_size=64,
            callbacks=callbacks,
            verbose=1
        )
        
        return history
    
    def save_model(self, path: str):
        """Save model to file"""
        self.model.save(path)
        print(f"Model saved to {path}")
    
    def load_model(self, path: str):
        """Load model from file"""
        try:    
            self.model = keras.models.load_model(path)
            print(f"✅ Model loaded successfully from {path}")
        except Exception as e:
            print(f"❌ Error loading model: {e}")
            print("⚠️ Building new model (random weights)")
            self.model = None
            self.build_model()
# Pre-trained model weights for transfer learning
class TransferLearningEmotionDetector(EmotionDetector):
    """Emotion detector using transfer learning (VGG16-based)"""
    
    def build_model(self):
        """Build model using transfer learning"""
        base_model = keras.applications.VGG16(
            weights='imagenet',
            include_top=False,
            input_shape=(48, 48, 3)
        )
        
        # Freeze base model layers
        base_model.trainable = False
        
        model = keras.Sequential([
            layers.Lambda(lambda x: tf.image.grayscale_to_rgb(x)),
            base_model,
            layers.GlobalAveragePooling2D(),
            layers.Dense(256, activation='relu'),
            layers.Dropout(0.5),
            layers.Dense(7, activation='softmax')
        ])
        
        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=0.0001),
            loss='categorical_crossentropy',
            metrics=['accuracy']
        )
        
        self.model = model
        return model