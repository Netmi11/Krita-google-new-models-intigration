"""
ComfyUI custom node for Gemini mask-based image editing.
Sends image + mask to Gemini API and composites the result with feathered blending.
"""

import base64
import json
import os
from io import BytesIO

import numpy as np
import requests
import torch
from PIL import Image, ImageFilter


class GeminiMaskEdit:
    CATEGORY = "Gemini"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "edit_mask")

    MODELS = [
        "gemini-3.1-flash-image-preview",
        "gemini-3-pro-image-preview",
    ]

    SAFETY_LEVELS = ["block_none", "block_few", "block_some", "block_most"]

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mask": ("MASK",),
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "api_key": ("STRING", {"default": ""}),
                "model": (cls.MODELS,),
                "mode": (["inpaint", "outpaint"],),
                "image_size": (["1K", "2K", "4K"],),
            },
            "optional": {
                "temperature": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 2.0, "step": 0.1}),
                "seed": ("INT", {"default": -1, "min": -1, "max": 2**31 - 1}),
                "safety_filter": (cls.SAFETY_LEVELS, {"default": "block_none"}),
                "blur_radius": ("INT", {"default": 12, "min": 0, "max": 64, "step": 1}),
            },
        }

    @staticmethod
    def _tensor_to_pil(tensor):
        arr = (tensor[0].cpu().numpy() * 255).astype(np.uint8)
        return Image.fromarray(arr, mode="RGB")

    @staticmethod
    def _mask_to_pil(mask):
        arr = (mask[0].cpu().numpy() * 255).astype(np.uint8)
        return Image.fromarray(arr, mode="L")

    @staticmethod
    def _pil_to_b64(img, fmt="PNG"):
        buf = BytesIO()
        img.save(buf, format=fmt)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    @staticmethod
    def _b64_to_pil(data):
        return Image.open(BytesIO(base64.b64decode(data)))

    @staticmethod
    def _pil_to_tensor(img):
        arr = np.array(img.convert("RGB")).astype(np.float32) / 255.0
        return torch.from_numpy(arr).unsqueeze(0)

    def _build_payload(self, prompt, image_b64, mask_b64, mode, image_size, temperature, seed, safety_filter):
        mode_instruction = {
            "outpaint": (
                "The first image is the original photo. The second image is a binary mask "
                "where WHITE areas represent empty/transparent regions that need to be filled. "
                "Extend and complete the image naturally into the white masked areas, "
                "maintaining perfect style and content consistency with the original."
            ),
            "inpaint": (
                "The first image is the original photo. The second image is a binary mask "
                "where WHITE areas indicate the regions to edit. "
                "Modify ONLY the white masked areas according to the user instruction below, "
                "keeping all black masked areas completely unchanged."
            ),
        }

        full_prompt = f"{mode_instruction[mode]}\n\nUser instruction: {prompt}" if prompt else mode_instruction[mode]

        parts = [
            {"text": full_prompt},
            {"inlineData": {"mimeType": "image/png", "data": image_b64}},
            {"inlineData": {"mimeType": "image/png", "data": mask_b64}},
        ]

        generation_config = {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"imageSize": image_size},
        }
        if temperature is not None:
            generation_config["temperature"] = temperature
        if seed >= 0:
            generation_config["seed"] = seed % (2**31)

        safety_threshold_map = {
            "block_none": "BLOCK_NONE",
            "block_few": "BLOCK_ONLY_HIGH",
            "block_some": "BLOCK_MEDIUM_AND_ABOVE",
            "block_most": "BLOCK_LOW_AND_ABOVE",
        }
        threshold = safety_threshold_map.get(safety_filter, "BLOCK_NONE")
        safety_settings = [
            {"category": cat, "threshold": threshold}
            for cat in [
                "HARM_CATEGORY_HARASSMENT",
                "HARM_CATEGORY_HATE_SPEECH",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "HARM_CATEGORY_DANGEROUS_CONTENT",
                "HARM_CATEGORY_CIVIC_INTEGRITY",
            ]
        ]

        return {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": generation_config,
            "safetySettings": safety_settings,
        }

    def _call_gemini(self, api_key, model, payload):
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{model}:generateContent?key={api_key}"
        )
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            block_reason = data.get("promptFeedback", {}).get("blockReason", "UNKNOWN")
            raise RuntimeError(f"Gemini blocked the request: {block_reason}")

        for part in candidates[0].get("content", {}).get("parts", []):
            inline = part.get("inlineData")
            if inline and inline.get("mimeType", "").startswith("image/"):
                return inline["data"]

        raise RuntimeError("No image returned in Gemini response")

    @staticmethod
    def _composite(original, generated, mask, blur_radius):
        generated = generated.resize(original.size, Image.LANCZOS)
        mask = mask.resize(original.size, Image.NEAREST)

        if blur_radius > 0:
            mask = mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        orig_arr = np.array(original, dtype=np.float32)
        gen_arr = np.array(generated, dtype=np.float32)
        mask_arr = np.array(mask, dtype=np.float32) / 255.0
        mask_3ch = np.stack([mask_arr] * 3, axis=-1)

        result = orig_arr * (1.0 - mask_3ch) + gen_arr * mask_3ch
        return Image.fromarray(result.astype(np.uint8), mode="RGB")

    def execute(self, image, mask, prompt, api_key, model, mode, image_size,
                temperature=0.8, seed=-1, safety_filter="block_none", blur_radius=12):

        if not api_key:
            api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            raise ValueError("API key required: provide it as input or set GOOGLE_API_KEY env var")

        pil_image = self._tensor_to_pil(image)
        pil_mask = self._mask_to_pil(mask)
        image_b64 = self._pil_to_b64(pil_image)
        mask_b64 = self._pil_to_b64(pil_mask)

        payload = self._build_payload(prompt, image_b64, mask_b64, mode, image_size, temperature, seed, safety_filter)
        result_b64 = self._call_gemini(api_key, model, payload)

        generated_pil = self._b64_to_pil(result_b64)
        composited_pil = self._composite(pil_image, generated_pil, pil_mask, blur_radius)

        result_tensor = self._pil_to_tensor(composited_pil)
        mask_tensor = torch.from_numpy(
            np.array(pil_mask, dtype=np.float32) / 255.0
        ).unsqueeze(0)

        return (result_tensor, mask_tensor)


NODE_CLASS_MAPPINGS = {
    "GeminiMaskEdit": GeminiMaskEdit,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GeminiMaskEdit": "Gemini Mask Edit",
}
