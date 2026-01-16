"""Model client for AI inference using OpenAI-compatible API."""

import json
import time
from dataclasses import dataclass, field
from typing import Any

from openai import APIError, OpenAI

from phone_agent.config.i18n import get_message


@dataclass
class ModelConfig:
    """Configuration for the AI model."""

    base_url: str = "http://localhost:8000/v1"
    api_key: str = "EMPTY"
    model_name: str = "autoglm-phone-9b"
    max_tokens: int = 3000
    temperature: float = 0.0
    top_p: float = 0.85
    frequency_penalty: float = 0.2
    extra_body: dict[str, Any] = field(default_factory=dict)
    lang: str = "cn"  # Language for UI messages: 'cn' or 'en'
    max_retry: int = 10  # Maximum retry attempts for API calls
    retry_wait_seconds: float = 3.0  # Initial wait time between retries (exponential backoff)


@dataclass
class ModelResponse:
    """Response from the AI model."""

    thinking: str
    action: str
    raw_content: str
    # Performance metrics
    time_to_first_token: float | None = None  # Time to first token (seconds)
    time_to_thinking_end: float | None = None  # Time to thinking end (seconds)
    total_time: float | None = None  # Total inference time (seconds)


class ModelClient:
    """
    Client for interacting with OpenAI-compatible vision-language models.

    Args:
        config: Model configuration.
    """

    def __init__(self, config: ModelConfig | None = None):
        self.config = config or ModelConfig()
        self.client = OpenAI(base_url=self.config.base_url, api_key=self.config.api_key)

    def request(self, messages: list[dict[str, Any]], app_name: str | None = None) -> ModelResponse:
        """
        Send a request to the model with retry logic.

        Args:
            messages: List of message dictionaries in OpenAI format.
            app_name: Optional app name for log identification.

        Returns:
            ModelResponse containing thinking and action.

        Raises:
            ValueError: If the response cannot be parsed.
            APIError: If all retry attempts fail.
        """
        max_retry = self.config.max_retry
        wait_seconds = self.config.retry_wait_seconds
        app_prefix = f"[{app_name}] " if app_name else ""

        for attempt in range(max_retry):
            try:
                return self._request_once(messages, app_name)
            except Exception as e:
                if attempt < max_retry - 1:
                    print(f"{app_prefix}API调用失败 (尝试 {attempt + 1}/{max_retry}): {e}")
                    print(f"{app_prefix}等待 {wait_seconds:.1f} 秒后重试...")
                    time.sleep(wait_seconds)
                    wait_seconds *= 1.5
                else:
                    print(f"{app_prefix}API调用失败，已重试 {max_retry} 次")
                    raise

    def _request_once(self, messages: list[dict[str, Any]], app_name: str | None = None) -> ModelResponse:
        """
        Send a single request to the model (without retry).

        Args:
            messages: List of message dictionaries in OpenAI format.
            app_name: Optional app name for log identification.

        Returns:
            ModelResponse containing thinking and action.

        Raises:
            APIError: If the API call fails.
        """
        # Start timing
        start_time = time.time()
        time_to_first_token = None
        time_to_thinking_end = None
        app_prefix = f"[{app_name}] " if app_name else ""

        stream = self.client.chat.completions.create(
            messages=messages,
            model=self.config.model_name,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            frequency_penalty=self.config.frequency_penalty,
            extra_body=self.config.extra_body,
            stream=True,
        )

        raw_content = ""
        buffer = ""  # Buffer to hold content that might be part of a marker
        action_markers = ["finish(message=", "do(action="]
        in_action_phase = False  # Track if we've entered the action phase
        first_token_received = False
        prefix_printed = False  # Track if app prefix has been printed for this thinking phase
        action_buffer = ""  # Buffer for action content after marker detected
        early_action_parsed = None  # Early parsed action (if complete)

        for chunk in stream:
            if len(chunk.choices) == 0:
                continue
            if chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                raw_content += content

                # Record time to first token
                if not first_token_received:
                    time_to_first_token = time.time() - start_time
                    first_token_received = True

                if in_action_phase:
                    # Already in action phase, accumulate action content
                    action_buffer += content
                    # Try early parsing for complete finish actions (only check once)
                    if early_action_parsed is None and action_buffer.startswith("finish(message="):
                        if self._is_complete_finish_action(action_buffer):
                            early_action_parsed = action_buffer
                    continue

                buffer += content

                # Check if any marker is fully present in buffer
                marker_found = False
                for marker in action_markers:
                    if marker in buffer:
                        # Marker found, print everything before it
                        thinking_part = buffer.split(marker, 1)[0]
                        if thinking_part:
                            print(thinking_part, end="", flush=True)
                            prefix_printed = True
                        print()  # Print newline after thinking is complete
                        in_action_phase = True
                        marker_found = True
                        # Start collecting action content (marker + remaining content in buffer)
                        buffer_parts = buffer.split(marker, 1)
                        action_buffer = marker + buffer_parts[1] if len(buffer_parts) > 1 else marker

                        # Record time to thinking end
                        if time_to_thinking_end is None:
                            time_to_thinking_end = time.time() - start_time

                        # Try early parsing for finish actions
                        if marker == "finish(message=" and self._is_complete_finish_action(action_buffer):
                            early_action_parsed = action_buffer

                        break

                if marker_found:
                    continue  # Continue to collect remaining content

                # Check if buffer ends with a prefix of any marker
                # If so, don't print yet (wait for more content)
                is_potential_marker = False
                for marker in action_markers:
                    for i in range(1, len(marker)):
                        if buffer.endswith(marker[:i]):
                            is_potential_marker = True
                            break
                    if is_potential_marker:
                        break

                if not is_potential_marker:
                    # Safe to print the buffer
                    if buffer:
                        print(buffer, end="", flush=True)
                        prefix_printed = True
                    buffer = ""

        # Calculate total time
        total_time = time.time() - start_time

        # Parse thinking and action from response
        # Use early parsed action if available (already validated as complete), otherwise parse from full content
        if early_action_parsed:
            # Use early parsed action for finish (simple case)
            thinking = raw_content.split(early_action_parsed, 1)[0].strip()
            action = early_action_parsed
        else:
            # Parse from full content (default, ensures correctness)
            thinking, action = self._parse_response(raw_content)

        # Print performance metrics
        lang = self.config.lang
        print()
        print("=" * 50)
        print(f"{app_prefix}⏱️  {get_message('performance_metrics', lang)}:")
        print("-" * 50)
        if time_to_first_token is not None:
            print(
                f"{get_message('time_to_first_token', lang)}: {time_to_first_token:.3f}s"
            )
        if time_to_thinking_end is not None:
            print(
                f"{get_message('time_to_thinking_end', lang)}:        {time_to_thinking_end:.3f}s"
            )
        print(
            f"{get_message('total_inference_time', lang)}:          {total_time:.3f}s"
        )
        print("=" * 50)

        return ModelResponse(
            thinking=thinking,
            action=action,
            raw_content=raw_content,
            time_to_first_token=time_to_first_token,
            time_to_thinking_end=time_to_thinking_end,
            total_time=total_time,
        )

    def _parse_response(self, content: str) -> tuple[str, str]:
        """
        Parse the model response into thinking and action parts.

        Parsing rules:
        1. If content contains 'finish(message=', everything before is thinking,
           everything from 'finish(message=' onwards is action.
        2. If rule 1 doesn't apply but content contains 'do(action=',
           everything before is thinking, everything from 'do(action=' onwards is action.
        3. Fallback: If content contains '<answer>', use legacy parsing with XML tags.
        4. Otherwise, return empty thinking and full content as action.

        Args:
            content: Raw response content.

        Returns:
            Tuple of (thinking, action).
        """
        # Rule 1: Check for finish(message=
        if "finish(message=" in content:
            parts = content.split("finish(message=", 1)
            thinking = parts[0].strip()
            action = "finish(message=" + parts[1]
            return thinking, action

        # Rule 2: Check for do(action=
        if "do(action=" in content:
            parts = content.split("do(action=", 1)
            thinking = parts[0].strip()
            action = "do(action=" + parts[1]
            return thinking, action

        # Rule 3: Fallback to legacy XML tag parsing
        if "<answer>" in content:
            parts = content.split("<answer>", 1)
            thinking = parts[0].replace("<think>", "").replace("</think>", "").strip()
            action = parts[1].replace("</answer>", "").strip()
            return thinking, action

        # Rule 4: No markers found, return content as action
        return "", content

    def _is_complete_finish_action(self, action_str: str) -> bool:
        """
        Check if a finish action is complete (has closing quote and parenthesis).
        
        Args:
            action_str: Action string starting with "finish(message="
        
        Returns:
            True if the action appears complete, False otherwise.
        """
        if not action_str.startswith("finish(message="):
            return False
        
        prefix_len = len("finish(message=")
        if len(action_str) < prefix_len + 3:  # At least finish(message="")
            return False
        
        # Find opening quote
        quote_start = action_str.find('"', prefix_len)
        if quote_start == -1:
            return False
        
        # Find closing quote (handle escaped quotes)
        i = quote_start + 1
        while i < len(action_str):
            if action_str[i] == '"' and action_str[i-1] != '\\':
                # Check if closing parenthesis follows
                return i + 1 < len(action_str) and action_str[i + 1] == ')'
            i += 1
        
        return False


class MessageBuilder:
    """Helper class for building conversation messages."""

    @staticmethod
    def create_system_message(content: str) -> dict[str, Any]:
        """Create a system message."""
        return {"role": "system", "content": content}

    @staticmethod
    def create_user_message(
        text: str, image_base64: str | None = None
    ) -> dict[str, Any]:
        """
        Create a user message with optional image.

        Args:
            text: Text content.
            image_base64: Optional base64-encoded image.

        Returns:
            Message dictionary.
        """
        content = []

        if image_base64:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                }
            )

        content.append({"type": "text", "text": text})

        return {"role": "user", "content": content}

    @staticmethod
    def create_assistant_message(content: str) -> dict[str, Any]:
        """Create an assistant message."""
        return {"role": "assistant", "content": content}

    @staticmethod
    def remove_images_from_message(message: dict[str, Any]) -> dict[str, Any]:
        """
        Remove image content from a message to save context space.

        Args:
            message: Message dictionary.

        Returns:
            Message with images removed.
        """
        if isinstance(message.get("content"), list):
            message["content"] = [
                item for item in message["content"] if item.get("type") == "text"
            ]
        return message

    @staticmethod
    def build_screen_info(current_app: str, **extra_info) -> str:
        """
        Build screen info string for the model.

        Args:
            current_app: Current app name.
            **extra_info: Additional info to include.

        Returns:
            JSON string with screen info.
        """
        info = {"current_app": current_app, **extra_info}
        return json.dumps(info, ensure_ascii=False)

