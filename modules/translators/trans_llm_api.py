import re
import time
import json
import traceback
from typing import List, Dict, Optional, Type

import httpx
import openai
from pydantic import BaseModel, Field, ValidationError

from .base import BaseTranslator, register_translator


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
            "value": False,
            "description": "Enable pre-analysis of all OCR text before translation for consistent naming and style.",
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
        "manga_title": {
            "value": "",
            "description": "Optional: Manga/comic title (e.g., 'Naruto', '火影忍者'). Leave empty to auto-extract from folder name. AI will search online for character names and terminology to improve translation accuracy.",
        },
        "enable_web_search": {
            "value": True,
            "description": "Enable searching wiki pages (萌娘百科, 百度百科, Wikipedia) for manga background information to improve translation quality.",
        },
        "search_engine": {
            "value": "google",
            "options": ["google", "bing", "none"],
            "description": "Search engine to use for finding wiki pages. 'google' is recommended. Set to 'none' to use AI knowledge only.",
        },
        "google_api_key": {
            "value": "",
            "description": "Google Custom Search API key. Get free tier (100 queries/day) at https://developers.google.com/custom-search/v1/overview",
        },
        "google_search_engine_id": {
            "value": "",
            "description": "Google Custom Search Engine ID (CX). Create at https://programmablesearchengine.google.com/",
        },
        "bing_search_key": {
            "value": "",
            "description": "Bing Search API key (optional, if using Bing). Get free tier at https://www.microsoft.com/en-us/bing/apis/bing-web-search-api",
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
        self._manga_info: str = ""

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
        http_client = None
        if proxy:
            try:
                proxy_mounts = {
                    "http://": httpx.HTTPTransport(proxy=proxy),
                    "https://": httpx.HTTPTransport(proxy=proxy),
                }
                http_client = httpx.Client(mounts=proxy_mounts)
            except Exception as e:
                self.logger.error(
                    f"Failed to initialize proxy '{proxy}': {e}. Proceeding without proxy."
                )
                http_client = httpx.Client()
        else:
            http_client = httpx.Client()

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
    def proxy(self) -> str:
        return self.get_param_value("proxy")

    @property
    def system_prompt(self) -> str:
        return self.get_param_value("system_prompt")

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
    def manga_title(self) -> str:
        return self.get_param_value("manga_title").strip()

    @property
    def enable_web_search(self) -> bool:
        return bool(self.get_param_value("enable_web_search"))

    @property
    def search_engine(self) -> str:
        return self.get_param_value("search_engine")

    @property
    def google_api_key(self) -> str:
        return self.get_param_value("google_api_key").strip()

    @property
    def google_search_engine_id(self) -> str:
        return self.get_param_value("google_search_engine_id").strip()

    @property
    def bing_search_key(self) -> str:
        return self.get_param_value("bing_search_key").strip()

    def _extract_manga_title_from_path(self, project_dir: str) -> str:
        """Extract manga title from project directory path."""
        import os
        import re

        # Get the last directory name
        dir_name = os.path.basename(project_dir.rstrip('/'))

        # Remove common patterns like chapter numbers, volume numbers
        # Examples: "火影忍者_第1话" -> "火影忍者", "Naruto Vol 1" -> "Naruto"
        patterns = [
            r'[_\s]*第?\d+[话話集卷].*$',  # Remove chapter/volume numbers (Chinese)
            r'[_\s]*Vol\.?\s*\d+.*$',       # Remove "Vol 1", "Vol.1"
            r'[_\s]*Chapter\s*\d+.*$',      # Remove "Chapter 1"
            r'[_\s]*Ch\.?\s*\d+.*$',        # Remove "Ch 1", "Ch.1"
            r'[_\s]*\d+$',                  # Remove trailing numbers
        ]

        title = dir_name
        for pattern in patterns:
            title = re.sub(pattern, '', title, flags=re.IGNORECASE)

        return title.strip()

    def _search_wiki_pages(self, manga_title: str) -> str:
        """Search for wiki pages about the manga and extract content."""
        if not manga_title:
            return ""

        # Priority: Chinese wikis (萌娘百科, 百度百科) > Wikipedia
        search_queries = [
            f"{manga_title} 萌娘百科",
            f"{manga_title} 百度百科",
            f"{manga_title} 角色 wiki",
            f"{manga_title} wikipedia",
        ]

        wiki_content = []
        import requests

        if self.search_engine == "google" and self.google_api_key and self.google_search_engine_id:
            # Use Google Custom Search API
            for query in search_queries[:2]:  # Only search first 2 to save API calls
                try:
                    params = {
                        "key": self.google_api_key,
                        "cx": self.google_search_engine_id,
                        "q": query,
                        "num": 3,
                        "lr": "lang_zh-CN|lang_zh-TW|lang_ja",  # Prefer Chinese and Japanese results
                    }
                    response = requests.get(
                        "https://www.googleapis.com/customsearch/v1",
                        params=params,
                        timeout=10
                    )

                    if response.status_code == 200:
                        results = response.json()
                        for item in results.get("items", [])[:2]:
                            url = item.get("link", "")
                            snippet = item.get("snippet", "")
                            title = item.get("title", "")

                            # Check if it's a wiki page
                            if any(wiki in url.lower() for wiki in ["moegirl", "baike.baidu", "wikipedia", "fandom", "wikia"]):
                                wiki_content.append(f"Source: {title}\nURL: {url}\n{snippet}")
                                self.logger.info(f"Found wiki page: {url}")

                    if wiki_content:
                        break  # Found content, no need to continue

                except Exception as e:
                    self.logger.warning(f"Google search failed for '{query}': {e}")
                    continue

        elif self.search_engine == "bing" and self.bing_search_key:
            # Use Bing Search API
            for query in search_queries[:2]:  # Only search first 2 to save API calls
                try:
                    headers = {"Ocp-Apim-Subscription-Key": self.bing_search_key}
                    params = {"q": query, "count": 3, "mkt": "zh-CN"}
                    response = requests.get(
                        "https://api.bing.microsoft.com/v7.0/search",
                        headers=headers,
                        params=params,
                        timeout=10
                    )

                    if response.status_code == 200:
                        results = response.json()
                        for item in results.get("webPages", {}).get("value", [])[:2]:
                            url = item.get("url", "")
                            snippet = item.get("snippet", "")

                            # Check if it's a wiki page
                            if any(wiki in url.lower() for wiki in ["moegirl", "baike.baidu", "wikipedia"]):
                                wiki_content.append(f"Source: {url}\n{snippet}")
                                self.logger.info(f"Found wiki page: {url}")

                    if wiki_content:
                        break  # Found content, no need to continue

                except Exception as e:
                    self.logger.warning(f"Bing search failed for '{query}': {e}")
                    continue

        return "\n\n".join(wiki_content) if wiki_content else ""

    def _search_manga_info(self, manga_title: str) -> str:
        """Search for manga info and extract terminology using LLM."""
        if not manga_title:
            return ""

        try:
            # First, try to get wiki content via search API
            wiki_content = ""
            if self.search_engine != "none":
                wiki_content = self._search_wiki_pages(manga_title)

            current_api_key = self._select_api_key()
            if not current_api_key:
                self.logger.warning("No API key available for manga info extraction.")
                return ""

            if not self._initialize_client(current_api_key):
                self.logger.warning("Failed to initialize client for manga info extraction.")
                return ""

            self._respect_delay()

            model_name = self.override_model or self.model
            if ": " in model_name:
                model_name = model_name.split(": ", 1)[1]

            # Build prompt based on whether we have wiki content
            if wiki_content:
                search_prompt = (
                    f"You are helping translate a manga/anime titled '{manga_title}'.\n\n"
                    f"Below is information from wiki pages about this work:\n\n"
                    f"{wiki_content}\n\n"
                    f"Based on this information, create a concise terminology reference (under 400 words) including:\n"
                    f"1. **Character Names**: Original names and their Chinese translations\n"
                    f"   - Format: 'OriginalName (原文)' → 'ChineseName (中文)'\n"
                    f"   - Example: '火影様 (Hokage-sama)' → '火影大人' (keep as complete unit, don't split)\n"
                    f"2. **Titles & Ranks**: Special titles, positions, honorifics\n"
                    f"3. **Key Terms**: Unique terminology, abilities, locations specific to this series\n"
                    f"4. **Translation Notes**: Important conventions for this work\n\n"
                    f"Focus on information that helps maintain consistency and accuracy in translation."
                )
            else:
                # Fallback to AI's knowledge if no wiki content found
                search_prompt = (
                    f"You are helping translate a manga/anime titled '{manga_title}'.\n\n"
                    f"Based on your knowledge, provide a concise reference guide (under 300 words) including:\n"
                    f"1. **Main Characters**: Names in original language and common translations\n"
                    f"   - Example: '火影様' (Hokage-sama) should be translated as '火影大人' (not split into parts)\n"
                    f"2. **Key Terminology**: Titles, ranks, special terms specific to this series\n"
                    f"3. **Translation Conventions**: How character names and terms are typically translated\n"
                    f"4. **Important Context**: Any cultural or story-specific information helpful for translation\n\n"
                    f"If you don't know this work, simply say 'Unknown series' and provide general translation guidelines."
                )

            messages = [
                {"role": "system", "content": "You are a manga/anime translation assistant with knowledge of popular series."},
                {"role": "user", "content": search_prompt},
            ]

            completion = self.client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.3,
                max_tokens=500,
            )

            if completion.choices and completion.choices[0].message and completion.choices[0].message.content:
                info = completion.choices[0].message.content.strip()
                self.logger.info(f"Manga info generated for '{manga_title}' ({len(info)} chars)")
                return info
            else:
                self.logger.warning("Empty response from manga info search.")
                return ""

        except Exception as e:
            self.logger.warning(f"Failed to search manga info: {e}")
            return ""

    def generate_book_context(self, pages, project_dir: str = None) -> None:
        """Generate book context from OCR text and optionally search for manga info."""

        # Try to extract and search manga title if enabled
        manga_info = ""
        if self.enable_web_search and project_dir:
            # Extract manga title from project directory
            extracted_title = self._extract_manga_title_from_path(project_dir)

            # Use configured title if available, otherwise use extracted title
            title_to_search = self.manga_title or extracted_title

            if title_to_search:
                self.logger.info(f"Searching for manga info: '{title_to_search}'")
                manga_info = self._search_manga_info(title_to_search)
                if manga_info and "Unknown series" not in manga_info:
                    self.logger.info(f"Manga info found for '{title_to_search}'")
                    # Store it for use in translation
                    self._manga_info = manga_info

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
            return

        all_text = "\n\n".join(all_text_parts)
        user_message = self.book_context_prompt + "\n\nBelow is the OCR text from the book:\n\n" + all_text

        current_api_key = self._select_api_key()
        if not current_api_key:
            self.logger.error("No API key available for book context generation.")
            return

        if not self._initialize_client(current_api_key):
            self.logger.error("Failed to initialize client for book context generation.")
            return

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
            )
            if completion.choices and completion.choices[0].message and completion.choices[0].message.content:
                self._book_context_summary = completion.choices[0].message.content.strip()
                self.logger.info(f"Book context summary generated ({len(self._book_context_summary)} chars):\n{self._book_context_summary}")
            else:
                self.logger.warning("Empty response from book context pre-analysis.")
        except Exception as e:
            self.logger.error(f"Book context pre-analysis failed: {e}")

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

        # Add manga info from web search if available
        if self._manga_info:
            system_content += (
                f"\n\n## Manga/Anime Background Information\n"
                f"{self._manga_info}"
            )

        # Add manga title context if manually provided
        if self.manga_title:
            system_content += (
                f"\n\n## Source Material\n"
                f"You are translating from: {self.manga_title}\n"
                f"IMPORTANT: Use your knowledge of this work to:\n"
                f"1. Translate character names and titles correctly (e.g., '火影様' → '火影大人', not '影大人火影大人')\n"
                f"2. Keep proper nouns and titles as complete units - do not split them\n"
                f"3. Use established terminology from official translations when available\n"
                f"4. Maintain consistency with the source material's naming conventions"
            )

        # Add book context summary if available
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
            completion = self.client.chat.completions.create(**api_args)
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

        RETRYABLE_EXCEPTIONS = (
            openai.RateLimitError,
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.InternalServerError,
            openai.APIStatusError,
            httpx.RequestError,
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
                    api_retry_attempt += 1
                    self.logger.warning(
                        f"API Error (retryable): {type(e).__name__} - {e}. Attempt {api_retry_attempt}/{self.retry_attempts}."
                    )
                    if api_retry_attempt >= self.retry_attempts:
                        self.logger.error(
                            f"Fatal Error: Failed to connect to API after {self.retry_attempts} attempts."
                        )
                        translations.extend([f"[ERROR: API Failed]"] * num_src)
                        break
                    time.sleep(self.retry_timeout)

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
