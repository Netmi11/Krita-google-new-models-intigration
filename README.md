# Krita + Google Gemini Integration

Complete integration of Google Gemini image models into [Krita](https://krita.org/) via [ComfyUI](https://github.com/comfyanonymous/ComfyUI) and the [krita-ai-diffusion](https://github.com/Acly/krita-ai-diffusion) plugin.

## What's Included

### 6 Workflow Files (for krita-ai-diffusion custom workflows)

| Workflow | Model | File |
|----------|-------|------|
| **Outpaint** (extend canvas) | Gemini 3.1 Flash | `workflows/gemini-outpaint-flash.json` |
| **Outpaint** (extend canvas) | Gemini 3 Pro | `workflows/gemini-outpaint-pro.json` |
| **Inpaint** (edit regions) | Gemini 3.1 Flash | `workflows/gemini-inpaint-flash.json` |
| **Inpaint** (edit regions) | Gemini 3 Pro | `workflows/gemini-inpaint-pro.json` |
| **Generate** (text to image) | Gemini 3.1 Flash | `workflows/gemini-generate-flash.json` |
| **Generate** (text to image) | Gemini 3 Pro | `workflows/gemini-generate-pro.json` |

### Custom ComfyUI Node — GeminiMaskEdit

A dedicated node with full mask support for precise inpainting/outpainting with feathered blending.

Located in `custom_node/ComfyUI-Gemini-Mask/`.

## Prerequisites

- [Krita](https://krita.org/) (5.2+)
- [krita-ai-diffusion](https://github.com/Acly/krita-ai-diffusion) plugin (v1.26.0+)
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) running locally
- [ComfyUI_Nano_Banana](https://github.com/ru4ls/ComfyUI_Nano_Banana) custom nodes installed
- Google AI Studio API key ([get one here](https://aistudio.google.com/apikey))

## Installation

### 1. Install NanoBanana nodes

```bash
cd ComfyUI/custom_nodes/
git clone https://github.com/ru4ls/ComfyUI_Nano_Banana.git
cd ComfyUI_Nano_Banana
pip install -r requirements.txt
```

Create a `.env` file in the ComfyUI_Nano_Banana folder:
```
GOOGLE_API_KEY=your_api_key_here
```

### 2. Install workflows

Copy all JSON files from `workflows/` into your krita-ai-diffusion custom workflows folder:
- **Windows:** `%APPDATA%/krita-ai-diffusion/workflows/`
- **Linux:** `~/.local/share/krita-ai-diffusion/workflows/`
- **macOS:** `~/Library/Application Support/krita-ai-diffusion/workflows/`

Or import them directly in Krita via the krita-ai-diffusion plugin UI.

### 3. Install custom mask node (optional)

```bash
cd ComfyUI/custom_nodes/
cp -r /path/to/this/repo/custom_node/ComfyUI-Gemini-Mask .
cd ComfyUI-Gemini-Mask
pip install -r requirements.txt
```

Restart ComfyUI after installation.

## Usage

### Outpaint
1. Open an image in Krita
2. Extend the canvas (Image > Resize Canvas) in any direction
3. Select the Gemini Outpaint workflow in krita-ai-diffusion
4. Optionally edit the prompt (default handles most cases)
5. Click Generate

### Inpaint
1. Open an image in Krita
2. Select the Gemini Inpaint workflow
3. Write a prompt describing the edit you want
4. Click Generate

### Generate
1. Select the Gemini Generate workflow
2. Write your prompt
3. Adjust aspect ratio, image size, and temperature as needed
4. Click Generate

### GeminiMaskEdit Node (advanced)
Use this node in custom ComfyUI workflows for precise mask-based editing:
- Connect `ETN_KritaCanvas` image output to the `image` input
- Connect `ETN_KritaSelection` mask output to the `mask` input
- Set your API key, model, mode (inpaint/outpaint), and prompt
- The `blur_radius` parameter controls feathering at mask edges (default: 12)

## Models

| Model | Speed | Quality | Max Size | Cost/Image |
|-------|-------|---------|----------|------------|
| **Gemini 3.1 Flash** | Fast (3-8s) | Good | 4K | ~$0.045-0.151 |
| **Gemini 3 Pro** | Slow (10-20s) | Best | 4K | ~$0.134-0.240 |

**Flash** is recommended for iterative work. **Pro** is recommended for final quality output.

## Known Limitations

- Gemini does not have native mask support — masks are sent as a reference image with prompt instructions
- Mask-based editing may have "partial instruction following" — the model doesn't always respect mask boundaries perfectly
- The feathered compositing mitigates this by blending original pixels at mask edges
- Only 1 image is generated per API request (multiple images = multiple requests)
- Transparent backgrounds are not supported
- Small text rendering can be blurry at 1K resolution

## License

MIT
