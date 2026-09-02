import cv2
import numpy as np
import onnxruntime as ort
from pathlib import Path

class UltraDepthRenderer:
    """
    High-performance Ultra Depth 3D Renderer utilizing Depth Anything v2 via ONNX.
    Includes temporal smoothing, percentile clipping, and gamma contrast enhancement.
    """
    def __init__(self, project_root: Path, model_path: str = "models/depth_anything_v2_vits.onnx"):
        self.project_root = Path(project_root).resolve()
        self.model_file = self.project_root / model_path
        
        if not self.model_file.exists():
            print(f"  [DEPTH WARN] ONNX depth model not found at {self.model_file}. Falling back to standard processing.")
            self.session = None
        else:
            # Initialize ONNX Runtime session with CPU/CUDA execution providers
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if ort.get_device() == 'GPU' else ['CPUExecutionProvider']
            try:
                self.session = ort.InferenceSession(str(self.model_file), providers=providers)
                print(f"  [DEPTH] Initialized Ultra Depth ONNX model successfully.")
            except Exception as e:
                print(f"  [DEPTH WARN] Failed to load ONNX session: {e}")
                self.session = None

        self.prev_depth_frame = None

    def preprocess_image(self, img_bgr: np.ndarray, target_size: int = 518):
        """Prepares and normalizes input image for Depth Anything v2 ONNX inference."""
        h, w = img_bgr.shape[:2]
        # Resize maintaining aspect ratio or standard input dimensions
        img = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (target_size, target_size), interpolation=cv2.INTER_CUBIC)
        img = img.astype(np.float32) / 255.0
        # Normalize with ImageNet mean/std
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        img = (img - mean) / std
        img = np.transpose(img, (2, 0, 1))  # HWC to CHW
        img = np.expand_dims(img, axis=0)     # Add batch dimension
        return img, h, w

    def generate_depth_map(self, frame_bgr: np.ndarray) -> np.ndarray:
        """
        Generates a crisp, jitter-free ultra depth map with gamma correction and bilateral temporal smoothing.
        """
        if self.session is None:
            # Fallback simple grayscale gradient depth if model isn't present
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            return cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

        h_orig, w_orig = frame_bgr.shape[:2]
        input_tensor, _, _ = self.preprocess_image(frame_bgr)

        # Run ONNX inference
        input_name = self.session.get_inputs()[0].name
        outputs = self.session.run(None, {input_name: input_tensor})
        depth = outputs[0][0]

        # Post-process depth map: resize back to original frame dimensions
        depth = cv2.resize(depth, (w_orig, h_orig), interpolation=cv2.INTER_CUBIC)

        # Normalize depth map to 0-1 range
        d_min, d_max = depth.min(), depth.max()
        if d_max - d_min > 1e-5:
            depth = (depth - d_min) / (d_max - d_min)
        else:
            depth = np.zeros_like(depth)

        # Percentile clipping & Contrast enhancement (Gamma correction) for dramatic 3D separation
        p_low, p_high = np.percentile(depth, 2), np.percentile(depth, 98)
        depth = np.clip(depth, p_low, p_high)
        depth = (depth - depth.min()) / (depth.max() - depth.min() + 1e-5)
        
        # Apply gamma correction for richer depth contrast
        gamma = 1.2
        depth = np.power(depth, gamma)

        # Convert to 8-bit grayscale
        depth_8bit = (depth * 255).astype(np.uint8)

        # Temporal smoothing via Bilateral Filter to eliminate frame-to-frame jitter/flicker
        depth_8bit = cv2.bilateralFilter(depth_8bit, d=9, sigmaColor=75, sigmaSpace=75)

        # Frame-to-frame temporal blending for ultra-smooth transition
        if self.prev_depth_frame is not None:
            depth_8bit = cv2.addWeighted(depth_8bit, 0.7, self.prev_depth_frame, 0.3, 0)
        
        self.prev_depth_frame = depth_8bit
        return depth_8bit
