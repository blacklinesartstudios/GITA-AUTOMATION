import sys
import subprocess
from pathlib import Path
import cv2
import numpy as np

try:
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
except ImportError:
    print("  [SYSTEM] Installing required AI libraries...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "onnxruntime", "huggingface_hub"])
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download

# Global cache so the model loads only once per execution
_MODEL_SESSION = None
_INPUT_NAME = None

def get_depth_session():
    global _MODEL_SESSION, _INPUT_NAME
    if _MODEL_SESSION is None:
        model_file = hf_hub_download(
            repo_id="yuvraj108c/Depth-Anything-2-Onnx", 
            filename="depth_anything_v2_vits.onnx"
        )
        _MODEL_SESSION = ort.InferenceSession(model_file, providers=['CPUExecutionProvider'])
        _INPUT_NAME = _MODEL_SESSION.get_inputs()[0].name
    return _MODEL_SESSION, _INPUT_NAME

def make_depth(img_path: Path, depth_path: Path):
    img_path = Path(img_path)
    depth_path = Path(depth_path)
    depth_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"  [3D] Synthesizing Studio-Grade Depth for {img_path.name}...")
    try:
        session, input_name = get_depth_session()
    except Exception as e:
        print(f"  [ERROR] AI depth model load failed: {e}")
        return

    img = cv2.imread(str(img_path))
    if img is None:
        print(f"  [ERROR] Could not read image at {img_path}")
        return
        
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    orig_h, orig_w = img_rgb.shape[:2]

    target_size = 518
    img_resized = cv2.resize(img_rgb, (target_size, target_size), interpolation=cv2.INTER_CUBIC)
    
    img_norm = img_resized.astype(np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    img_norm = (img_norm - mean) / std
    img_norm = img_norm.transpose(2, 0, 1)
    img_norm = np.expand_dims(img_norm, axis=0)

    depth_map = session.run(None, {input_name: img_norm})[0]
    depth_map = np.squeeze(depth_map)
    
    depth_map = cv2.resize(depth_map, (orig_w, orig_h), interpolation=cv2.INTER_CUBIC)
    
    depth_min, depth_max = depth_map.min(), depth_map.max()
    if depth_max - depth_min > 0:
        depth_norm = (depth_map - depth_min) / (depth_max - depth_min)
    else:
        depth_norm = depth_map
        
    # Contrast expansion: Gamma 1.4 + Percentile normalisation
    gamma = 1.4  
    depth_norm = np.power(depth_norm, gamma)
    
    p_low, p_high = np.percentile(depth_norm, (5, 95))
    depth_norm = np.clip((depth_norm - p_low) / (p_high - p_low + 1e-5), 0, 1)
        
    depth_img = (depth_norm * 255.0).astype(np.uint8)
    depth_clean = cv2.bilateralFilter(depth_img, d=7, sigmaColor=50, sigmaSpace=50)

    cv2.imwrite(str(depth_path), depth_clean)
    print(f"  ✓ High-contrast depth map saved successfully to: {depth_path.name}")
