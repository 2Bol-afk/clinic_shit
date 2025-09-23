/**
 * Camera Capture Component for Profile Photos
 * Provides camera access for mobile devices with fallback options
 */

class CameraCapture {
    constructor(inputElement, previewElement = null) {
        this.input = inputElement;
        this.preview = previewElement;
        this.video = null;
        this.canvas = null;
        this.stream = null;
        this.isCapturing = false;
        
        this.init();
    }
    
    init() {
        // Add camera button if not exists
        this.addCameraButton();
        
        // Handle file input change
        this.input.addEventListener('change', (e) => {
            this.handleFileSelect(e);
        });
        
        // Add camera capture functionality
        this.addCameraCapture();
    }
    
    addCameraButton() {
        const container = this.input.parentElement;
        if (container.querySelector('.camera-capture-btn')) return;
        
        const cameraBtn = document.createElement('button');
        cameraBtn.type = 'button';
        cameraBtn.className = 'btn btn-outline-primary btn-sm camera-capture-btn';
        cameraBtn.innerHTML = '<i class="bi bi-camera me-1"></i>Take Photo';
        cameraBtn.addEventListener('click', () => this.openCamera());
        
        container.appendChild(cameraBtn);
    }
    
    addCameraCapture() {
        // Create modal for camera capture
        const modal = document.createElement('div');
        modal.className = 'modal fade camera-modal';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="bi bi-camera me-2"></i>Take Profile Photo
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body text-center">
                        <div class="camera-container mb-3">
                            <video id="camera-video" autoplay playsinline style="max-width: 100%; border-radius: 8px;"></video>
                            <canvas id="camera-canvas" style="display: none;"></canvas>
                        </div>
                        <div class="camera-controls">
                            <button type="button" class="btn btn-primary me-2" id="capture-btn">
                                <i class="bi bi-camera-fill me-1"></i>Capture
                            </button>
                            <button type="button" class="btn btn-secondary me-2" id="switch-camera-btn">
                                <i class="bi bi-arrow-repeat me-1"></i>Switch Camera
                            </button>
                            <button type="button" class="btn btn-outline-secondary" id="cancel-camera-btn">
                                <i class="bi bi-x-lg me-1"></i>Cancel
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        this.modal = new bootstrap.Modal(modal);
        this.video = modal.querySelector('#camera-video');
        this.canvas = modal.querySelector('#camera-canvas');
        
        // Add event listeners
        modal.querySelector('#capture-btn').addEventListener('click', () => this.capturePhoto());
        modal.querySelector('#switch-camera-btn').addEventListener('click', () => this.switchCamera());
        modal.querySelector('#cancel-camera-btn').addEventListener('click', () => this.closeCamera());
        
        // Close camera when modal is hidden
        modal.addEventListener('hidden.bs.modal', () => this.closeCamera());
    }
    
    async openCamera() {
        try {
            // Try to get back camera first (environment), then front camera
            const constraints = {
                video: {
                    facingMode: { ideal: 'environment' },
                    width: { ideal: 1280 },
                    height: { ideal: 720 }
                }
            };
            
            this.stream = await navigator.mediaDevices.getUserMedia(constraints);
            this.video.srcObject = this.stream;
            this.modal.show();
            
        } catch (error) {
            console.error('Error accessing camera:', error);
            this.showCameraError();
        }
    }
    
    async switchCamera() {
        if (!this.stream) return;
        
        try {
            // Stop current stream
            this.stream.getTracks().forEach(track => track.stop());
            
            // Get current facing mode
            const currentFacingMode = this.stream.getVideoTracks()[0].getSettings().facingMode;
            
            // Switch to opposite camera
            const newConstraints = {
                video: {
                    facingMode: currentFacingMode === 'environment' ? 'user' : 'environment',
                    width: { ideal: 1280 },
                    height: { ideal: 720 }
                }
            };
            
            this.stream = await navigator.mediaDevices.getUserMedia(newConstraints);
            this.video.srcObject = this.stream;
            
        } catch (error) {
            console.error('Error switching camera:', error);
            this.showCameraError();
        }
    }
    
    capturePhoto() {
        if (!this.video || !this.canvas) return;
        
        const context = this.canvas.getContext('2d');
        this.canvas.width = this.video.videoWidth;
        this.canvas.height = this.video.videoHeight;
        
        // Draw video frame to canvas
        context.drawImage(this.video, 0, 0);
        
        // Convert canvas to blob and create file
        this.canvas.toBlob((blob) => {
            const file = new File([blob], 'profile-photo.jpg', { type: 'image/jpeg' });
            
            // Create new FileList
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            this.input.files = dataTransfer.files;
            
            // Trigger change event
            this.input.dispatchEvent(new Event('change', { bubbles: true }));
            
            // Close camera
            this.closeCamera();
            
        }, 'image/jpeg', 0.8);
    }
    
    closeCamera() {
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        this.modal.hide();
    }
    
    handleFileSelect(event) {
        const file = event.target.files[0];
        if (!file) return;
        
        // Show preview if preview element exists
        if (this.preview) {
            const reader = new FileReader();
            reader.onload = (e) => {
                this.preview.src = e.target.result;
                this.preview.style.display = 'block';
            };
            reader.readAsDataURL(file);
        }
        
        // Update camera button text
        const cameraBtn = this.input.parentElement.querySelector('.camera-capture-btn');
        if (cameraBtn) {
            cameraBtn.innerHTML = '<i class="bi bi-camera-fill me-1"></i>Retake Photo';
        }
    }
    
    showCameraError() {
        alert('Camera access denied or not available. Please use the file input to select a photo.');
    }
}

// Auto-initialize camera capture for all file inputs with camera attributes
document.addEventListener('DOMContentLoaded', function() {
    const fileInputs = document.querySelectorAll('input[type="file"][accept*="image"]');
    
    fileInputs.forEach(input => {
        if (input.hasAttribute('capture')) {
            new CameraCapture(input);
        }
    });
});

// Export for manual initialization
window.CameraCapture = CameraCapture;
