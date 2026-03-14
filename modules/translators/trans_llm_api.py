import re
import time
import json
import traceback
import os
from pathlib import Path
from typing import List, Dict, Optional, Type

import httpx
import openai
from pydantic import BaseModel, Field, ValidationError

from .base import BaseTranslator, register_translator
from utils import shared


class InvalidNumTranslations(Exception):
    """Exception raised when the number of translations does not match the number of sources."""

    pass


class TranslationElement(BaseModel):
    id: int = Field(..., description="The original numeric ID of the text snippet.")
    translation: str = Field(
        ..., description="The translated text corresponding to the id."
    )


class TranslationResponse(BaseModel):
    translations: List[TranslationElement] = Field(
        ..., description="A list of all translated elements."
    )


@register_translator("LLM_API_Translator")
class LLM_API_Translator(BaseTranslator):
    concate_text = False
    cht_require_convert = True
    params: Dict = {
        "provider": {
            "type": "selector",
            "options": ["OpenAI", "Google", "Grok", "OpenRouter", "LLM Studio"],
            "value": "OpenAI",
            "description": "Select the LLM provider.",
        },
        "apikey": {
            "value": "",
            "description": "Single API key to use if multiple keys are not provided.",
        },
        "multiple_keys": {
            "type": "editor",
            "value": "",
            "description": "API keys separated by semicolons (;). Requests will rotate through these keys.",
        },
        "model": {
            "type": "selector",
            "options": [
                "OAI: gpt-4o",
                "OAI: gpt-4-turbo",
                "OAI: gpt-3.5-turbo",
                "GGL: gemini-1.5-pro-latest",
                "GGL: gemini-2.5-flash",
                "GGL: gemini-2.5-flash-lite",
                "XAI: grok-4",
                "XAI: grok-3",
                "XAI: grok-3-mini",
                "LLMS: (override model field)",
            ],
            "value": "OAI: gpt-4o",
            "description": "Select a model that supports JSON Mode for structured output.",
        },
        "override model": {
            "value": "",
            "description": "Specify a custom model name to override the selected model.",
        },
        "endpoint": {
            "value": "",
            "description": "Base URL for the API. Leave empty for provider default.",
        },
        "system_prompt": {
            "type": "editor",
            "value": 'You are an expert translator. Your task is to accurately translate the given text snippets. You MUST provide the output strictly in the specified JSON format, without any additional explanations or markdown formatting. The JSON object must have a single key \'translations\', which is a list of objects, each with an \'id\' (integer) and a \'translation\' (string).\n\nExample Output Schema:\n{"translations": [{"id": 1, "translation": "Translated text here."}]}',
            "description": "System message to instruct the LLM on its role and required output format.",
        },
        "invalid repeat count": {
            "value": 2,
            "description": "Number of retries if the count of translations mismatches the source count.",
        },
        "max requests per minute": {
            "value": 20,
            "description": "Maximum requests per minute for EACH API key.",
        },
        "delay": {
            "value": 0.3,
            "description": "Global delay in seconds between requests.",
        },
        "max tokens": {
            "value": 4096,
            "description": "Maximum tokens for the response.",
        },
        "temperature": {
            "value": 0.1,
            "description": "Sampling temperature. Lower values are recommended for structured output.",
        },
        "top p": {
            "value": 1.0,
            "description": "Top P for sampling.",
        },
        "retry attempts": {
            "value": 3,
            "description": "Number of retry attempts on API connection or parsing failures.",
        },
        "retry timeout": {
            "value": 15,
            "description": "Timeout between retry attempts (seconds).",
        },
        "request timeout": {
            "value": 12,
            "description": "Per-request API timeout in seconds.",
        },
        "book context timeout": {
            "value": 30,
            "description": "Timeout in seconds for the whole-book context pre-analysis request.",
        },
        "max consecutive api failures": {
            "value": 2,
            "description": "Open a fail-fast circuit after this many failed translation batches.",
        },
        "proxy": {
            "value": "",
            "description": "Proxy address (e.g., http(s)://user:password@host:port or socks4/5://user:password@host:port)",
        },
        "frequency penalty": {
            "value": 0.0,
            "description": "Frequency penalty (OpenAI).",
        },
        "presence penalty": {"value": 0.0, "description": "Presence penalty (OpenAI)."},
        "enable_book_context": {
            "value": True,
            "description": "Enable pre-analysis of all OCR text before translation for consistent naming and style.",
        },
        "reference_doc_path": {
            "value": "",
            "description": "Optional reference document path. CLI --reference overrides this value.",
        },
        "reference_document": {
            "type": "editor",
            "value": "",
            "description": "Optional inline reference document text for terminology, lore, and naming consistency.",
        },
        "book_context_prompt": {
            "type": "editor",
            "value": "You are given all OCR-extracted text from a manga/comic, organized by page.\n"
                     "Analyze the content and produce a concise reference summary for a translator.\n\n"
                     "Your summary MUST include:\n"
                     "1. **Characters**: Each character name in original language, with relationships if apparent.\n"
                     "2. **Setting**: Genre, time period, world details.\n"
                     "3. **Tone**: Dialogue style (formal/casual/humorous/dark, etc.)\n"
                     "4. **Key Terms**: Recurring terms, fictional words, or jargon that need consistent translation.\n"
                     "5. **Translation Notes**: Any other observations helpful for maintaining consistency.\n\n"
                     "Keep the summary under 500 words. Do NOT translate the text — only analyze it.",
            "description": "Prompt template for the book context pre-analysis call.",
        },
        "translation batch pages": {
            "value": 5,
            "description": "Maximum number of pages to combine into one deferred translation dispatch.",
        },
        "translation batch textblocks": {
            "value": 50,
            "description": "Maximum number of non-empty text blocks to combine into one deferred translation dispatch.",
        },
    }

    def _setup_translator(self):
        self.lang_map = {
            "简体中文": "Simplified Chinese",
            "繁體中文": "Traditional Chinese",
            "日本語": "Japanese",
            "English": "English",
            "한국어": "Korean",
            "Tiếng Việt": "Vietnamese",
            "čeština": "Czech",
            "Français": "French",
            "Deutsch": "German",
            "magyar nyelv": "Hungarian",
            "Italiano": "Italian",
            "Polski": "Polish",
            "Português": "Portuguese",
            "limba română": "Romanian",
            "русский язык": "Russian",
            "Español": "Spanish",
            "Türk dili": "Turkish",
            "украї́нська мо́ва": "Ukrainian",
            "Thai": "Thai",
            "Arabic": "Arabic",
            "Malayalam": "Malayalam",
            "Tamil": "Tamil",
            "Hindi": "Hindi",
        }
        self.token_count = 0
        self.token_count_last = 0
        self.current_key_index = 0
        self.last_request_time = 0
        self.request_count_minute = 0
        self.minute_start_time = time.time()
        self.key_usage = {}
        self.client = None
        self._book_context_summary: str = ""
        self._reference_document: str = ""
        self._reference_source: str = ""
        self._consecutive_api_failures = 0
        self._api_failure_circuit_open = False
        self._load_reference_document()

    def _initialize_client(self, api_key_to_use: str) -> bool:
        endpoint = self.endpoint
        provider = self.provider
        if not endpoint:
            if provider == "Google":
                endpoint = "https://generativelanguage.googleapis.com/v1beta/openai"
            elif provider == "OpenAI":
                endpoint = "https://api.openai.com/v1"
            elif provider == "OpenRouter":
                endpoint = "https://openrouter.ai/api/v1"
            elif provider == "Grok":
                endpoint = "https://api.x.ai/v1"

        proxy = self.proxy
        timeout = self.request_timeout
        http_client = None
        if proxy:
            try:
                proxy_mounts = {
                    "http://": httpx.HTTPTransport(proxy=proxy),
                    "https://": httpx.HTTPTransport(proxy=proxy),
                }
                http_client = httpx.Client(mounts=proxy_mounts, timeout=timeout)
            except Exception as e:
                self.logger.error(
                    f"Failed to initialize proxy '{proxy}': {e}. Proceeding without proxy."
                )
                http_client = httpx.Client(timeout=timeout)
        else:
            http_client = httpx.Client(timeout=timeout)

        masked_key = (
            api_key_to_use[:4] + "..." + api_key_to_use[-4:]
            if len(api_key_to_use) > 8
            else api_key_to_use
        )
        self.logger.debug(
            f"Initializing client for {provider} with key {masked_key} at endpoint {endpoint}"
        )

        try:
            self.client = openai.OpenAI(
                api_key=api_key_to_use, base_url=endpoint, http_client=http_client
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize OpenAI client: {e}")
            self.client = None
            return False

    # --- Property getters ---
    @property
    def provider(self) -> str:
        return self.get_param_value("provider")

    @property
    def apikey(self) -> str:
        env_key = os.getenv("BA_API_KEY", "").strip()
        if env_key:
            return env_key
        return self.get_param_value("apikey")

    @property
    def multiple_keys_list(self) -> List[str]:
        keys_str = self.get_param_value("multiple_keys")
        if not isinstance(keys_str, str):
            return []
        return [
            key.strip()
            for key in keys_str.strip().replace("\n", ";").split(";")
            if key.strip()
        ]

    @property
    def model(self) -> str:
        return self.get_param_value("model")

    @property
    def override_model(self) -> Optional[str]:
        return self.get_param_value("override model") or None

    @property
    def endpoint(self) -> Optional[str]:
        return self.get_param_value("endpoint") or None

    @property
    def temperature(self) -> float:
        return float(self.get_param_value("temperature"))

    @property
    def top_p(self) -> float:
        return float(self.get_param_value("top p"))

    @property
    def max_tokens(self) -> int:
        return int(self.get_param_value("max tokens"))

    @property
    def retry_attempts(self) -> int:
        return int(self.get_param_value("retry attempts"))

    @property
    def retry_timeout(self) -> int:
        return int(self.get_param_value("retry timeout"))

    @property
    def request_timeout(self) -> float:
        return float(self.get_param_value("request timeout"))

    @property
    def book_context_timeout(self) -> float:
        timeout = self.get_param_value("book context timeout")
        if timeout in (None, ""):
            return max(30.0, self.request_timeout)
        return max(float(timeout), self.request_timeout)

    @property
    def max_consecutive_api_failures(self) -> int:
        return max(1, int(self.get_param_value("max consecutive api failures")))

    @property
    def proxy(self) -> str:
        return self.get_param_value("proxy")

    @property
    def system_prompt(self) -> str:
        return self.get_param_value("system_prompt")

    @property
    def reference_doc_path(self) -> str:
        return self.get_param_value("reference_doc_path")

    @property
    def reference_document(self) -> str:
        return self.get_param_value("reference_document")

    @property
    def invalid_repeat_count(self) -> int:
        return int(self.get_param_value("invalid repeat count"))

    @property
    def frequency_penalty(self) -> float:
        return float(self.get_param_value("frequency penalty"))

    @property
    def presence_penalty(self) -> float:
        return float(self.get_param_value("presence penalty"))

    @property
    def max_rpm(self) -> int:
        return int(self.get_param_value("max requests per minute"))

    @property
    def global_delay(self) -> float:
        return float(self.get_param_value("delay"))

    @property
    def enable_book_context(self) -> bool:
        return bool(self.get_param_value("enable_book_context"))

    @property
    def book_context_prompt(self) -> str:
        return self.get_param_value("book_context_prompt")

    @property
    def needs_book_context(self) -> bool:
        return self.enable_book_context

    @property
    def translation_batch_page_size(self) -> int:
        return max(1, int(self.get_param_value("translation batch pages")))

    @property
    def translation_batch_textblk_size(self) -> int:
        return max(0, int(self.get_param_value("translation batch textblocks")))

    def _cli_reference_path(self) -> str:
        args = shared.args
        if args is None:
            return ""
        return getattr(args, "reference", "") or ""

    def _read_reference_file(self, path_str: str) -> str:
        path = Path(path_str).expanduser()
        if not path.exists():
            self.logger.warning(f"Reference document does not exist: {path}")
            return ""
        if not path.is_file():
            self.logger.warning(f"Reference path is not a file: {path}")
            return ""

        for encoding in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue

        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            self.logger.warning(f"Failed to read reference document {path}: {e}")
            return ""

    def _load_reference_document(self) -> None:
        inline_reference = (self.reference_document or "").strip()
        path_reference = ""
        path_source = ""

        cli_path = self._cli_reference_path()
        cfg_path = (self.reference_doc_path or "").strip()
        resolved_path = cli_path or cfg_path
        if resolved_path:
            path_reference = self._read_reference_file(resolved_path).strip()
            if path_reference:
                path_source = resolved_path

        parts = []
        if path_reference:
            parts.append(path_reference)
        if inline_reference:
            parts.append(inline_reference)

        self._reference_document = "\n\n".join(parts).strip()
        self._reference_source = path_source or ("inline config" if inline_reference else "")

        if self._reference_document:
            source_desc = self._reference_source or "unknown source"
            self.logger.info(
                f"Loaded reference document from {source_desc} "
                f"({len(self._reference_document)} chars)."
            )

    def generate_book_context(self, pages) -> bool:
        self._book_context_summary = ""
        all_text_parts = []
        for page_name, blk_list in pages.items():
            texts = []
            for i, blk in enumerate(blk_list):
                text = blk.get_text().strip()
                if text:
                    texts.append(f"[{i + 1}] {text}")
            if texts:
                all_text_parts.append(f"=== Page: {page_name} ===\n" + "\n".join(texts))

        if not all_text_parts:
            self.logger.warning("No OCR text found in any page, skipping book context generation.")
            return False

        all_text = "\n\n".join(all_text_parts)
        user_message = self.book_context_prompt + "\n\nBelow is the OCR text from the book:\n\n" + all_text
        if self._reference_document:
            user_message += (
                "\n\nReference document for canon names, worldbuilding, and style:\n\n"
                + self._reference_document
            )

        current_api_key = self._select_api_key()
        if not current_api_key:
            self.logger.error("No API key available for book context generation.")
            return False

        if not self._initialize_client(current_api_key):
            self.logger.error("Failed to initialize client for book context generation.")
            return False

        self._respect_delay()

        model_name = self.override_model or self.model
        if ": " in model_name:
            model_name = model_name.split(": ", 1)[1]

        messages = [
            {"role": "system", "content": "You are a text analysis assistant for manga/comic translation."},
            {"role": "user", "content": user_message},
        ]

        try:
            completion = self.client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.3,
                max_tokens=self.max_tokens,
                timeout=self.book_context_timeout,
            )
            if completion.choices and completion.choices[0].message and completion.choices[0].message.content:
                self._book_context_summary = completion.choices[0].message.content.strip()
                self.logger.info(f"Book context summary generated ({len(self._book_context_summary)} chars):\n{self._book_context_summary}")
                return True
            else:
                self.logger.warning("Empty response from book context pre-analysis.")
                return False
        except Exception as e:
            self.logger.error(
                f"Book context pre-analysis failed after {self.book_context_timeout:.0f}s timeout: {e}"
            )
            return False

    def _assemble_prompts(self, queries: List[str], to_lang: str):
        from_lang = self.lang_map.get(self.lang_source, self.lang_source)
        batch_size = 50

        for batch_start in range(0, len(queries), batch_size):
            batch = queries[batch_start:batch_start + batch_size]
            input_elements = [
                {"id": i + 1, "source": query} for i, query in enumerate(batch)
            ]
            input_json_str = json.dumps(input_elements, ensure_ascii=False, indent=2)

            prompt = (
                f"Please translate the following text snippets from {from_lang} to {to_lang}. "
                f"The input is provided as a JSON array. Respond with a JSON object in the specified format.\n\n"
                f"INPUT:\n{input_json_str}"
            )

            yield prompt, len(batch)

    def _respect_delay(self):
        current_time = time.time()
        rpm = self.max_rpm
        delay = self.global_delay
        if rpm > 0:
            if current_time - self.minute_start_time >= 60:
                self.request_count_minute = 0
                self.minute_start_time = current_time
            if self.request_count_minute >= rpm:
                wait_time = 60.1 - (current_time - self.minute_start_time)
                if wait_time > 0:
                    self.logger.warning(
                        f"Global RPM limit ({rpm}) reached. Waiting {wait_time:.2f} seconds."
                    )
                    time.sleep(wait_time)
                self.request_count_minute = 0
                self.minute_start_time = time.time()

        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < delay:
            sleep_time = delay - time_since_last_request
            if hasattr(self, "debug_mode") and self.debug_mode:
                self.logger.debug(f"Global delay: Waiting {sleep_time:.3f} seconds.")
            time.sleep(sleep_time)

        self.last_request_time = time.time()
        self.request_count_minute += 1

    def _respect_key_limit(self, key: str) -> bool:
        rpm = self.max_rpm
        if rpm <= 0:
            return True
        now = time.time()
        count, start_time = self.key_usage.get(key, (0, now))
        if now - start_time >= 60:
            count, start_time = 0, now
            self.key_usage[key] = (count, start_time)
        if count >= rpm:
            wait_time = 60.1 - (now - start_time)
            if wait_time > 0:
                self.logger.warning(
                    f"RPM limit ({rpm}) reached for key {key[:6]}... Waiting {wait_time:.2f} seconds."
                )
                time.sleep(wait_time)
            self.key_usage[key] = (0, time.time())
            return False
        return True

    def _select_api_key(self) -> Optional[str]:
        api_keys = self.multiple_keys_list
        single_key = self.apikey
        if not api_keys and not single_key:
            self.logger.error("No API keys provided in parameters.")
            return None

        if not api_keys:
            if self._respect_key_limit(single_key):
                now = time.time()
                count, start_time = self.key_usage.get(single_key, (0, now))
                if now - start_time >= 60:
                    count = 0
                    start_time = now
                self.key_usage[single_key] = (count + 1, start_time)
                return single_key
            return None

        start_index = self.current_key_index
        for i in range(len(api_keys)):
            index = (start_index + i) % len(api_keys)
            key = api_keys[index]
            if self._respect_key_limit(key):
                now = time.time()
                count, start_time = self.key_usage.get(key, (0, now))
                self.key_usage[key] = (count + 1, start_time)
                self.current_key_index = (index + 1) % len(api_keys)
                return key
        self.logger.error("All available API keys are currently rate-limited.")
        return None

    def _usable_key_count(self) -> int:
        if self.multiple_keys_list:
            return len(self.multiple_keys_list)
        return 1 if self.apikey else 0

    def _error_text(self, exc: Exception) -> str:
        parts = [str(exc)]
        body = getattr(exc, "body", None)
        if body:
            try:
                parts.append(json.dumps(body, ensure_ascii=False))
            except Exception:
                parts.append(str(body))
        return " ".join(part for part in parts if part).lower()

    def _is_quota_exhausted_error(self, exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        if status_code not in (402, 403, 429):
            return False
        detail = self._error_text(exc)
        quota_markers = (
            "key usage limit exceeded",
            "usage limit exceeded",
            "quota exceeded",
            "quota",
            "insufficient credits",
            "credit balance is too low",
            "billing",
        )
        return any(marker in detail for marker in quota_markers)

    def _is_non_retryable_auth_error(self, exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        return status_code in (401, 403)

    def _request_translation(self, prompt: str) -> Optional[TranslationResponse]:
        current_api_key = "lm-studio"
        if self.provider != "LLM Studio":
            current_api_key = self._select_api_key()
            if not current_api_key:
                raise ConnectionError("No available API key found.")

        if self.provider == "LLM Studio" and not self.endpoint:
            raise ValueError(
                "Endpoint must be specified when using the LLM Studio provider (e.g., http://localhost:1234/v1)."
            )

        if not self._initialize_client(current_api_key):
            raise ConnectionError("Failed to initialize API client.")

        self._respect_delay()

        model_name = self.override_model or self.model
        if ": " in model_name:
            model_name = model_name.split(": ", 1)[1]

        system_content = self.system_prompt
        if self._reference_document:
            system_content += (
                "\n\n## Reference Document\n"
                "Use the following reference as authoritative guidance for names, "
                "terms, fixed titles, lore, relationships, and tone:\n\n"
                + self._reference_document
            )
        if self._book_context_summary:
            system_content += (
                "\n\n## Book Context Summary\n"
                "Use the following context to maintain consistency "
                "in character names, terminology, and tone:\n\n"
                + self._book_context_summary
            )
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ]

        api_args = {
            "model": model_name,
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
        }

        if self.provider == "LLM Studio":
            self.logger.debug("Using 'json_schema' mode for LLM Studio.")
            api_args["response_format"] = {
                "type": "json_schema",
                "json_schema": {"schema": TranslationResponse.model_json_schema()},
            }
        elif self.provider in ["OpenAI", "Grok", "Google", "OpenRouter"]:
            self.logger.debug(f"Using 'json_object' mode for {self.provider}.")
            api_args["response_format"] = {"type": "json_object"}

        if self.provider == "OpenAI":
            api_args["frequency_penalty"] = self.frequency_penalty
            api_args["presence_penalty"] = self.presence_penalty

        try:
            completion = self.client.chat.completions.create(
                **api_args,
                timeout=self.request_timeout,
            )
        except Exception as e:
            self.logger.error(f"API request failed: {e}")
            raise

        if (
            completion.choices
            and completion.choices[0].message
            and completion.choices[0].message.content
        ):
            raw_content = completion.choices[0].message.content
            json_to_parse = raw_content.strip()

            match = re.search(
                r"```(?:json)?\s*(\{.*?\})\s*```", json_to_parse, re.DOTALL
            )
            if match:
                self.logger.debug(
                    "Markdown code block detected. Extracting JSON content."
                )
                json_to_parse = match.group(1)
            else:
                start = json_to_parse.find("{")
                end = json_to_parse.rfind("}")
                if start != -1 and end != -1 and end > start:
                    json_to_parse = json_to_parse[start : end + 1]
            try:
                data_to_validate = json.loads(json_to_parse)
                validated_response = TranslationResponse.model_validate(
                    data_to_validate
                )
            except (ValidationError, json.JSONDecodeError) as e:
                self.logger.warning(
                    f"Initial Pydantic validation failed: {e}. Attempting to fix simple dictionary or list format."
                )
                try:
                    simple_data = json.loads(json_to_parse)
                    fixed_translations = []

                    if isinstance(simple_data, dict) and all(
                        k.isdigit() for k in simple_data.keys()
                    ):
                        fixed_translations = [
                            {"id": int(k), "translation": v}
                            for k, v in simple_data.items()
                        ]
                    elif isinstance(simple_data, list):
                        fixed_translations = simple_data

                    if fixed_translations:
                        fixed_data = {"translations": fixed_translations}
                        self.logger.debug(
                            f"Transformed simple response to: {fixed_data}"
                        )
                        validated_response = TranslationResponse.model_validate(
                            fixed_data
                        )
                        self.logger.info(
                            "Successfully parsed response after fixing simple format."
                        )
                    else:
                        raise e
                except (ValidationError, json.JSONDecodeError, Exception) as final_e:
                    self.logger.error(
                        f"Pydantic validation or JSON parsing failed even after attempting fix: {final_e}"
                    )
                    self.logger.debug(f"Raw JSON content from API: {raw_content}")
                    raise
        else:
            self.logger.warning("No valid message content in API response.")
            return None

        if hasattr(completion, "usage") and completion.usage:
            self.token_count += completion.usage.total_tokens
            self.token_count_last = completion.usage.total_tokens
        else:
            self.token_count_last = 0

        return validated_response

    def _translate(self, src_list: List[str]) -> List[str]:
        if not src_list:
            return []
        if self._api_failure_circuit_open:
            self.logger.warning(
                "Skip translation batch because API fail-fast circuit is open."
            )
            return ["[ERROR: API Unavailable]"] * len(src_list)

        RETRYABLE_EXCEPTIONS = (
            openai.RateLimitError,
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.InternalServerError,
            openai.APIStatusError,
            httpx.RequestError,
            ConnectionError,
        )

        translations = []
        to_lang = self.lang_map.get(self.lang_target, self.lang_target)

        for prompt, num_src in self._assemble_prompts(src_list, to_lang=to_lang):
            api_retry_attempt = 0
            mismatch_retry_attempt = 0

            while True:
                try:
                    parsed_response = self._request_translation(prompt)

                    if not parsed_response or not parsed_response.translations:
                        raise ValueError(
                            "Received empty or invalid parsed response from API."
                        )

                    if len(parsed_response.translations) != num_src:
                        raise InvalidNumTranslations(
                            f"Expected {num_src}, got {len(parsed_response.translations)}"
                        )

                    translations_dict = {
                        item.id: item.translation
                        for item in parsed_response.translations
                    }
                    ordered_translations = [
                        translations_dict.get(i, "") for i in range(1, num_src + 1)
                    ]

                    translations.extend(ordered_translations)
                    self._consecutive_api_failures = 0
                    self._api_failure_circuit_open = False
                    self.logger.info(
                        f"Successfully translated batch of {num_src}. Tokens used: {self.token_count_last}"
                    )
                    break

                except InvalidNumTranslations as e:
                    mismatch_retry_attempt += 1
                    self.logger.warning(
                        f"Translation structure mismatch: {e}. Attempt {mismatch_retry_attempt}/{self.invalid_repeat_count}."
                    )
                    if mismatch_retry_attempt >= self.invalid_repeat_count:
                        self.logger.error(
                            "Fatal Error: Failed to get correct translation structure after retries."
                        )
                        translations.extend(["[ERROR: Structure Mismatch]"] * num_src)
                        break
                    time.sleep(self.retry_timeout / 2)

                except RETRYABLE_EXCEPTIONS as e:
                    if self._usable_key_count() <= 1 and self._is_non_retryable_auth_error(e):
                        self._consecutive_api_failures += 1
                        self._api_failure_circuit_open = True
                        if self._is_quota_exhausted_error(e):
                            self.logger.error(
                                "Fatal Error: API quota or key usage limit exceeded. "
                                "Stopping retries because only one usable API key is configured."
                            )
                            translations.extend(["[ERROR: API Quota Exceeded]"] * num_src)
                        else:
                            self.logger.error(
                                "Fatal Error: API authentication or permission denied. "
                                "Stopping retries because only one usable API key is configured."
                            )
                            translations.extend(["[ERROR: API Permission Denied]"] * num_src)
                        self.logger.error(
                            "Opening API fail-fast circuit after non-retryable authentication/quota failure. "
                            "Remaining pages will be skipped quickly."
                        )
                        break
                    api_retry_attempt += 1
                    self.logger.warning(
                        f"API Error (retryable): {type(e).__name__} - {e}. Attempt {api_retry_attempt}/{self.retry_attempts}."
                    )
                    if api_retry_attempt >= self.retry_attempts:
                        self._consecutive_api_failures += 1
                        self.logger.error(
                            f"Fatal Error: Failed to connect to API after {self.retry_attempts} attempts."
                        )
                        if (
                            self._consecutive_api_failures
                            >= self.max_consecutive_api_failures
                        ):
                            self._api_failure_circuit_open = True
                            self.logger.error(
                                "Opening API fail-fast circuit after consecutive failures. "
                                "Remaining pages will be skipped quickly."
                            )
                        translations.extend([f"[ERROR: API Failed]"] * num_src)
                        break
                    wait_time = self.retry_timeout
                    if isinstance(
                        e,
                        (
                            openai.APIConnectionError,
                            openai.APITimeoutError,
                            httpx.RequestError,
                            ConnectionError,
                        ),
                    ):
                        wait_time = min(wait_time, 3)
                    time.sleep(wait_time)

                except (
                    ValidationError,
                    json.JSONDecodeError,
                    openai.BadRequestError,
                    openai.AuthenticationError,
                    ValueError,
                ) as e:
                    self.logger.error(
                        f"Fatal Error: An unrecoverable error occurred: {type(e).__name__} - {e}"
                    )
                    self.logger.debug(traceback.format_exc())
                    translations.extend([f"[ERROR: {type(e).__name__}]"] * num_src)
                    break

        return translations

    def updateParam(self, param_key: str, param_content):
        super().updateParam(param_key, param_content)

        if param_key in ["proxy", "multiple_keys", "apikey", "provider", "endpoint"]:
            self.client = None
