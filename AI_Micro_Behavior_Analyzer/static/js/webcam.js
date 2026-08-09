// Webcam handling and frame capture utilities
class WebcamManager {
    constructor(videoElementId, canvasElementId) {
        this.video = document.getElementById(videoElementId);
        this.canvas = document.getElementById(canvasElementId);
        this.context = this.canvas?.getContext('2d');
        this.stream = null;
        this.isActive = false;
    }
    
    async initialize() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                    frameRate: { ideal: 30 }
                }
            });
            this.video.srcObject = this.stream;
            await this.video.play();
            this.isActive = true;
            
            // Set canvas dimensions
            this.canvas.width = this.video.videoWidth;
            this.canvas.height = this.video.videoHeight;
            
            return true;
        } catch (error) {
            console.error('Webcam initialization failed:', error);
            return false;
        }
    }
    
    captureFrame() {
        if (!this.isActive || !this.video.videoWidth) return null;
        this.context.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
        return this.canvas.toDataURL('image/jpeg', 0.8);
    }
    
    stop() {
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.isActive = false;
        }
    }
}

class SessionManager {
    constructor(sessionId, apiEndpoint) {
        this.sessionId = sessionId;
        this.apiEndpoint = apiEndpoint;
        this.analysisInterval = null;
        this.frameRate = 1000; // ms between frames
    }
    
    startAnalysis(webcamManager, onResult) {
        this.analysisInterval = setInterval(async () => {
            const frameData = webcamManager.captureFrame();
            if (frameData) {
                const result = await this.analyzeFrame(frameData);
                if (onResult) onResult(result);
            }
        }, this.frameRate);
    }
    
    async analyzeFrame(imageData) {
        try {
            const response = await fetch(this.apiEndpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    image: imageData,
                    session_id: this.sessionId
                })
            });
            return await response.json();
        } catch (error) {
            console.error('Frame analysis failed:', error);
            return null;
        }
    }
    
    stopAnalysis() {
        if (this.analysisInterval) {
            clearInterval(this.analysisInterval);
            this.analysisInterval = null;
        }
    }
}

export { WebcamManager, SessionManager };