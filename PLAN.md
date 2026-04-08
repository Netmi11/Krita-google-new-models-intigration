# Plan: Krita + Gemini — Outpainting, Inpainting & Generate Workflows + Custom Mask Node

## Context

**Goal:** Build a complete integration of Google Gemini into Krita via ComfyUI, consisting of:
1. **6 workflow JSON files** for `krita-ai-diffusion` plugin (flash + pro variants for each of 3 workflows)
2. **A custom ComfyUI node** with full mask support for proper outpainting/inpainting

**Why Gemini:** Unlike local models (SDXL, Flux), Gemini has real-world knowledge — it knows what an Israeli cityscape, a specific restaurant, or a natural landscape looks like. This enables intelligent outpainting, not just texture continuation.

**User's request:** Both `gemini-3.1-flash-image-preview` (NanoBanana2AIO) and `gemini-3-pro-image-preview` (NanoBananaAIO) variants for each workflow, plus a custom node with mask support (researched first to leverage existing work).

---

## Research Findings: Existing Implementations

### 3 Key Projects Found:

| Project | API | Mask Support | Key Learning |
|---------|-----|-------------|--------------|
| **ComfyUI-Outpainting-Gemini** (jzhang-POP) | Vertex AI REST | No (padding+composite) | Pad calculator, feathered compositing, service account JWT auth |
| **ComfyUI-NanoB-Edit-Gemini** (comrender) | Generative Language REST | No (prompt-based) | Parallel generation, File API, seed normalization, safety settings, model capabilities map |
| **ComfyUI_Imagen** (ru4ls) | Vertex AI Python SDK | **YES** (`model.edit_image(mask=...)`) | Explicit mask tensor->PIL->Vertex Image conversion. But uses Imagen (deprecated June 2026) |

### Critical API Findings:
- **Gemini API (ai.google.dev):** Does NOT support mask-based editing natively. Only prompt-driven.
- **Vertex AI Imagen:** HAS mask support but Imagen deprecated June 2026.
- **Best hybrid approach:** Use Gemini API + send mask as additional image in prompt (Gemini's multimodal understanding can interpret masks) + compositing for clean blending.

---

## Part 1: Workflow JSON Files (6 files)

### File Structure
```
workflows/
  gemini-outpaint-flash.json    (NanoBanana2AIO - gemini-3.1-flash)
  gemini-outpaint-pro.json      (NanoBananaAIO - gemini-3-pro)
  gemini-inpaint-flash.json
  gemini-inpaint-pro.json
  gemini-generate-flash.json
  gemini-generate-pro.json
custom_node/
  ComfyUI-Gemini-Mask/
    __init__.py
    gemini_mask_node.py
    requirements.txt
```

### Node Types Reference

**Krita nodes** (`comfyui-tooling-nodes`):
- `ETN_KritaCanvas` — outputs: image(0), width(1), height(2), seed(3), mask(4)
- `ETN_KritaSelection` — inputs: context, padding; outputs: mask(0), active(1), x(2), y(3)
- `ETN_KritaOutput` — inputs: images, x, y, name, batch_mode, resize_canvas
- `ETN_Parameter` — inputs: name, type, default, min, max; output: value(0)

**Nano Banana nodes** (`ComfyUI_Nano_Banana`):
- `NanoBanana2AIO` — model: `gemini-3.1-flash-image-preview`, up to 14 image inputs, supports image_search
- `NanoBananaAIO` — model: `gemini-3-pro-image-preview`, up to 6 image inputs, use_search defaults True

### JSON Format (ComfyUI API format)
- Node IDs: numeric strings ("1", "2", ...)
- Connections: `["node_id", output_index]`
- Each node: `{ "inputs": {...}, "class_type": "...", "_meta": {"title": "..."} }`
- Parameter naming: `"<order>. <Group>/<Parameter Name>"` (e.g. `"2. Settings/1. Image Size"`)

---

### Workflow A: Outpaint (flash + pro)

**User flow:** Extend canvas in Krita -> empty area = transparent -> send full canvas to Gemini -> Gemini fills empty areas

**Nodes (7):**

| ID | class_type | Role |
|----|-----------|------|
| 1 | ETN_KritaCanvas | Get canvas with extended empty areas |
| 2 | ETN_Parameter | Prompt (default: outpaint instruction) |
| 3 | ETN_Parameter | Image Size (choice: 512px/1K/2K/4K) |
| 4 | ETN_Parameter | Temperature (default: 0.6) |
| 5 | ETN_Parameter | Use Search toggle |
| 6 | NanoBanana2AIO *or* NanoBananaAIO | Gemini outpainting |
| 7 | ETN_KritaOutput | Result to Krita |

**Connections:**
- Node 1 (image, idx 0) -> Node 6 (image_1)
- Node 2 (value) -> Node 6 (prompt)
- Node 3 (value) -> Node 6 (image_size)
- Node 4 (value) -> Node 6 (temperature)
- Node 5 (value) -> Node 6 (use_search)
- Node 6 (images, idx 0) -> Node 7 (images)

**Default prompt:** `"Extend and complete this image naturally, filling all empty or transparent areas while maintaining style and content consistency"`

**Flash vs Pro differences:**
- Flash: `NanoBanana2AIO`, model `gemini-3.1-flash-image-preview`, has `use_image_search: false`
- Pro: `NanoBananaAIO`, model `gemini-3-pro-image-preview`, no `use_image_search` field, `use_search` defaults `true`
- Pro: Image Size choices limited to `["1K", "2K", "4K"]` (no 512px)

---

### Workflow B: Inpaint (flash + pro)

**User flow:** Canvas has existing image -> user describes what to change -> Gemini edits

**Same 7-node structure as outpaint** but:
- Default prompt: `""` (empty - user must describe the edit)
- Temperature: 0.8
- Node title: "Gemini Inpaint"

---

### Workflow C: Generate (flash + pro)

**User flow:** Text prompt -> Gemini generates from scratch (no reference image)

**Nodes (7):**

| ID | class_type | Role |
|----|-----------|------|
| 1 | ETN_Parameter | Prompt |
| 2 | ETN_Parameter | Image Size (choice) |
| 3 | ETN_Parameter | Aspect Ratio (choice) |
| 4 | ETN_Parameter | Temperature (default: 1.0) |
| 5 | ETN_Parameter | Image Count (1-10) |
| 6 | NanoBanana2AIO *or* NanoBananaAIO | Gemini generation |
| 7 | ETN_KritaOutput | Result to Krita |

**Differences:** No ETN_KritaCanvas, has Aspect Ratio + Image Count params, temperature 1.0

---

## Part 2: Custom ComfyUI Node with Mask Support

### Architecture (inspired by existing projects)

Based on research, the best approach combines techniques from all 3 existing projects:

**From ComfyUI-NanoB-Edit-Gemini:** REST API pattern, API key auth, parallel generation, safety settings, model capabilities map, seed normalization
**From ComfyUI-Outpainting-Gemini:** Compositing approach - blend original + generated with feathered mask
**From ComfyUI_Imagen:** Tensor-to-PIL mask conversion patterns

### Node: `GeminiMaskEdit`

```python
INPUT_TYPES:
  required:
    - image: IMAGE          # [B,H,W,C] canvas image
    - mask: MASK            # [B,H,W] selection mask (white=edit area)
    - prompt: STRING        # Edit instruction
    - api_key: STRING       # Google AI Studio API key
    - model: ["gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview"]
    - mode: ["outpaint", "inpaint"]
    - image_size: ["1K", "2K", "4K"]
  optional:
    - temperature: FLOAT (0.0-2.0, default 0.8)
    - seed: INT
    - safety_filter: ["block_none", "block_few", "block_some", "block_most"]

RETURN_TYPES: ("IMAGE", "MASK")
RETURN_NAMES: ("image", "edit_mask")
```

### How mask editing works (without native API mask support):

1. **Receive** IMAGE + MASK from Krita (via ETN_KritaCanvas + ETN_KritaSelection)
2. **Send to Gemini**: Original image as `image_1`, mask as `image_2` (as visual reference), prompt includes instruction like "Edit only the white areas of the mask image"
3. **Gemini generates** a complete new image
4. **Composite**: Use the mask to blend - keep original pixels where mask=0, use Gemini output where mask=1
5. **Feather blending**: Apply Gaussian blur to mask edges for seamless transition (like ComfyUI-Outpainting-Gemini's approach)

### API Call Pattern (from ComfyUI-NanoB-Edit-Gemini):
```python
url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
payload = {
    "contents": [{"role": "user", "parts": [
        {"text": prompt_with_mask_instruction},
        {"inlineData": {"mimeType": "image/png", "data": image_b64}},
        {"inlineData": {"mimeType": "image/png", "data": mask_b64}},
    ]}],
    "generationConfig": {
        "responseModalities": ["IMAGE"],
        "imageConfig": {"imageSize": image_size},
        "seed": normalized_seed,
    },
    "safetySettings": [...]
}
```

### Tensor Conversion (proven patterns):
```python
# IMAGE tensor [B,H,W,C] -> PIL -> base64
img_np = (image[0].cpu().numpy() * 255).astype(np.uint8)
pil_img = Image.fromarray(img_np)

# MASK tensor [B,H,W] -> PIL grayscale -> base64
mask_np = (mask[0].cpu().numpy() * 255).astype(np.uint8)
pil_mask = Image.fromarray(mask_np, mode='L')

# PIL -> base64
buffer = BytesIO()
pil_img.save(buffer, format="PNG")
b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

# Result base64 -> tensor
result_pil = Image.open(BytesIO(base64.b64decode(response_b64)))
result_np = np.array(result_pil).astype(np.float32) / 255.0
result_tensor = torch.from_numpy(result_np).unsqueeze(0)  # [1,H,W,C]
```

### Compositing (feathered blending from Outpainting-Gemini):
```python
# Feather the mask edges
mask_blurred = gaussian_blur(mask, radius=blur_radius)
# Composite: original * (1-mask) + generated * mask
result = original * (1.0 - mask_blurred) + generated * mask_blurred
```

### Files:
- `custom_node/ComfyUI-Gemini-Mask/__init__.py` - Node registration
- `custom_node/ComfyUI-Gemini-Mask/gemini_mask_node.py` - Node implementation (~200 lines)
- `custom_node/ComfyUI-Gemini-Mask/requirements.txt` - `requests`, `Pillow`, `torch`, `numpy`

---

## Implementation Order

1. Create `workflows/` directory
2. Create 6 workflow JSON files (flash + pro for outpaint, inpaint, generate)
3. Create custom node `ComfyUI-Gemini-Mask` with full mask support
4. Create `README.md` with installation, usage, tips
5. Validate all JSON files
6. Commit and push to `claude/krita-google-models-Kw8hb`

---

## Verification

1. **JSON validity:** `python -c "import json; json.load(open('file.json'))"` for all 6 files
2. **Node references:** Script to verify all `["id", idx]` connections point to valid nodes
3. **Required nodes:** Each workflow has exactly one `ETN_KritaOutput`
4. **Custom node syntax:** `python -c "import ast; ast.parse(open('file.py').read())"` for Python files
5. **README completeness:** All prerequisites, installation steps, and usage documented
