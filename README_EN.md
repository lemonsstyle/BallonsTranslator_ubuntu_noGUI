# Manga Batch Translation Tool

中文版本: [README.md](README.md)

This project is based on BallonsTranslator and is currently focused on headless batch translation for manga image folders. It can detect text areas, run OCR, translate text, remove the original text, and export rendered result images according to `config/config.json`.

## Features

- Batch process one or more manga image folders.
- Detect speech bubbles/text regions and extract source text with OCR.
- Translate text with the configured translator, including `LLM_API_Translator`.
- Optionally generate book-level OCR context before translation so the LLM can keep names, terms, and tone consistent.
- Inpaint original text regions and export final translated images.

## Usage

Check `config/config.json` before running. The most important fields are:

- `module.translator`
- `module.translate_source`
- `module.translate_target`
- `module.translator_params`
- `module.enable_detect`
- `module.enable_ocr`
- `module.enable_translate`
- `module.enable_inpaint`

### Using Another AI Service

To use a third-party AI service that you configured yourself, confirm that the service provides an OpenAI-compatible API, then update three fields in `config/config.json`:

- `module.translator_params.LLM_API_Translator.endpoint`: set the provider's Base URL, for example `https://example.com/v1`. Do not include the full `/chat/completions` path.
- `module.translator_params.LLM_API_Translator.override model`: set the provider's actual model name, for example `deepseek-chat`, `qwen-plus`, or `provider/model-name`.
- `module.translator_params.LLM_API_Translator.apikey`: set the provider API key. Do not commit real keys to a public repository.

Minimal example:

```json
{
  "module": {
    "translator": "LLM_API_Translator",
    "translator_params": {
      "LLM_API_Translator": {
        "endpoint": "https://example.com/v1",
        "override model": "provider/model-name",
        "apikey": "YOUR_API_KEY"
      }
    }
  }
}
```

Run a batch job:

```bash
python launch.py --headless --exec_dirs "/path/to/chapter1,/path/to/chapter2"
```

Notes:

- `exec_dirs` is a comma-separated list of folders.
- Do not add spaces after commas.
- Each folder creates or reuses an `imgtrans_<folder-name>.json` project file.
- Final images are written to the folder's `result/` directory.
- To pass a glossary or reference document:

```bash
python launch.py --headless --exec_dirs "/path/to/chapter1" --reference "/path/to/reference.md"
```

## File Structure

- `launch.py`: entry point for command-line arguments, config loading, and environment setup.
- `config/config.json`: main runtime config for modules, languages, API settings, models, and stage switches.
- `modules/`: core processing modules for detection, OCR, translation, and inpainting.
- `modules/translators/`: translator implementations; `trans_llm_api.py` is the general LLM API translator.
- `ui/`: main workflow and Qt UI code; headless mode reuses the same pipeline control.
- `utils/`: project files, image I/O, config, logging, and shared helpers.
- `data/`: model, cache, or runtime data.
- `logs/`: runtime logs.

## Workflow

1. `launch.py` loads config and starts in headless mode.
2. `MainWindow.run_batch()` parses `exec_dirs` and opens each manga folder.
3. If no project JSON exists, the project scans images and creates one.
4. The pipeline runs text detection, OCR, mask saving, and inpainting page by page.
5. If `LLM_API_Translator.enable_book_context` is enabled, all OCR text is collected and sent once to the LLM to generate a context summary.
6. The translator translates each page or batch of text blocks and writes results back to the project.
7. Each completed page is saved to the project JSON and rendered to `result/`.

## Role of AI

- Detection, OCR, and inpainting models automate the image-processing stages.
- The LLM translator converts OCR text into the target language.
- With book-level context enabled, the LLM also creates a summary to improve consistency for names, terminology, tone, and setting.
