import os
import requests
from pathlib import Path
from google import genai

def generate_cinematic_verse_image(chapter: int, verse: int, output_path: Path):
    """
    Generates ultra-realistic 9:16 cinematic visuals matching the exact mood of the verse.
    Uses Google Imagen API.
    """
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    
    prompt = (
        f"Cinematic ultra-realistic 8k masterpiece depicting the ancient epic scene of Bhagavad Gita, "
        f"Chapter {chapter}, Verse {verse}. Dramatic Kurukshetra battlefield background, atmospheric lighting, "
        f"volumetric golden rays, cinematic depth of field, 3D hyper-detailed lighting, epic Indian mythology "
        f"aesthetic, photorealistic, Unreal Engine 5 render style, 9:16 vertical composition."
    )

    try:
        result = client.models.generate_images(
            model='imagen-3.0-generate-002',
            prompt=prompt,
            config=dict(
                number_of_images=1,
                aspect_ratio="9:16",
                output_mime_type="image/jpeg"
            )
        )
        for generated_image in result.generated_images:
            output_path.write_bytes(generated_image.image.image_bytes)
            print(f"[IMAGEN] Generated original background: {output_path.name}")
            return output_path
    except Exception as e:
        print(f"[WARNING] Image generation error ({e}). Using existing assets.")
        return None