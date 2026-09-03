from pathlib import Path
import urllib.request
import cv2
import numpy as np

_ONNX_SESSION = None

MODEL_URL = "https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model_fp16.onnx"

def get_depth_session(project_root: Path):
    global _ONNX_SESSION
    if _ONNX_SESSION is not None:
        return _ONNX_SESSION

    try:
        import onnxruntime as ort
    except ImportError:
        print("  [DEPTH] onnxruntime not found. Falling back to default depth processor.")
        return None

    model_dir = project_root / "cache" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "depth_anything_v2_small.onnx"

    if not model_path.exists() or model_path.stat().st_size < 1000000:
        print(f"  [DEPTH] Downloading Depth Anything v2 ONNX model to {model_path.name}...")
        try:
            urllib.request.urlretrieve(MODEL_URL, str(model_path))
            print("  ✓ Depth model downloaded successfully.")
        except Exception as e:
            print(f"  [DEPTH] Failed downloading model: {e}")
            return None

    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    available = ort.get_available_providers()
    selected_providers = [p for p in providers if p in available]

    _ONNX_SESSION = ort.InferenceSession(str(model_path), providers=selected_providers)
    return _ONNX_SESSION

def enhance_depth_contrast(raw_depth: np.ndarray) -> np.ndarray:
    """
    Stretches dynamic range across the full 0-255 spectrum:
    Pure White (255) = Foreground Subject / Weapons (Maximum displacement)
    Mid Grey (128)   = Battlefield Ground / Chariots
    Pitch Black (0)  = Sky / Infinite Distance (Zero displacement)
    """
    # 1. Percentile stretch (clamps sensor noise & specular highlights)
    p_low, p_high = np.percentile(raw_depth, (2, 98))
    clipped = np.clip(raw_depth, p_low, p_high)
    norm = (clipped - p_low) / max(1e-5, (p_high - p_low))

    # 2. Gamma punch (1.45) to drop distant skies to true black
    punched = np.power(norm, 1.45)
    depth_u8 = (punched * 255.0).astype(np.uint8)

    # 3. CLAHE (Local Adaptive Contrast) for fabric, chariot, and facial detail
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    enhanced = clahe.apply(depth_u8)

    # 4. Bilateral edge smoothing to prevent jagged displacement borders
    return cv2.bilateralFilter(enhanced, 9, 75, 75)

def make_depth(image_path: Path, output_depth_path: Path):
    """
    Generates a high-contrast 3D depth map for image_path and caches it at output_depth_path.
    """
    output_depth_path = Path(output_depth_path)
    output_depth_path.parent.mkdir(parents=True, exist_ok=True)

    img_bgr = cv2.imread(str(image_path))
    if img_bgr is None:
        raise FileNotFoundError(f"Source image not found: {image_path}")

    h_orig, w_orig = img_bgr.shape[:2]
    project_root = output_depth_path.resolve().parent.parent if output_depth_path.resolve().parent.name in ("depth", "depths") else output_depth_path.resolve().parent
    session = get_depth_session(project_root)

    if session is not None:
        try:
            # Model inference: 518x518 input resolution
            input_size = 518
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            resized = cv2.resize(img_rgb, (input_size, input_size), interpolation=cv2.INTER_CUBIC)
            
            mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
            std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
            inp = ((resized / 255.0) - mean) / std
            inp = inp.transpose(2, 0, 1)[np.newaxis, ...].astype(np.float32)

            input_name = session.get_inputs()[0].name
            depth_out = session.run(None, {input_name: inp})[0].squeeze()

            depth_resized = cv2.resize(depth_out, (w_orig, h_orig), interpolation=cv2.INTER_CUBIC)
            final_depth = enhance_depth_contrast(depth_resized)
            cv2.imwrite(str(output_depth_path), final_depth)
            return final_depth
        except Exception as e:
            print(f"  [DEPTH] ONNX inference error: {e}. Using OpenCV gradient fallback.")

    # Fallback: High-contrast synthetic center-radial depth gradient
    y, x = np.indices((h_orig, w_orig), dtype=np.float32)
    cy, cx = h_orig * 0.45, w_orig * 0.5
    dist = np.sqrt(((x - cx) / (w_orig * 0.5)) ** 2 + ((y - cy) / (h_orig * 0.5)) ** 2)
    synth = np.clip(1.0 - (dist * 0.7), 0.0, 1.0)
    final_depth = (np.power(synth, 1.5) * 255.0).astype(np.uint8)
    cv2.imwrite(str(output_depth_path), final_depth)
    return final_depth
