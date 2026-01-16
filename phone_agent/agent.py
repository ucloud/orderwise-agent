"""Main PhoneAgent class for orchestrating phone automation."""

import json
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from phone_agent.actions import ActionHandler
from phone_agent.actions.handler import do, finish, parse_action
from phone_agent.adb import get_current_app, get_screenshot
from phone_agent.config import get_messages, get_system_prompt
from phone_agent.model import ModelClient, ModelConfig
from phone_agent.model.client import MessageBuilder


@dataclass
class AgentConfig:
    """Configuration for the PhoneAgent."""

    max_steps: int = 100
    device_id: str | None = None
    lang: str = "cn"
    system_prompt: str | None = None
    verbose: bool = True
    enable_screenshot_cache: bool = True
    screenshot_cache_max_age: float = 1.0
    app_name: str | None = None  # App name for log identification
    takeover_check_callback: Callable[[], bool] | None = None  # Callback to check for manual takeover, returns True if task should be terminated

    def __post_init__(self):
        if self.system_prompt is None:
            self.system_prompt = get_system_prompt(self.lang)


@dataclass
class StepResult:
    """Result of a single agent step."""

    success: bool
    finished: bool
    action: dict[str, Any] | None
    thinking: str
    message: str | None = None


class PhoneAgent:
    """
    AI-powered agent for automating Android phone interactions.

    The agent uses a vision-language model to understand screen content
    and decide on actions to complete user tasks.

    Args:
        model_config: Configuration for the AI model.
        agent_config: Configuration for the agent behavior.
        confirmation_callback: Optional callback for sensitive action confirmation.
        takeover_callback: Optional callback for takeover requests.

    Example:
        >>> from phone_agent import PhoneAgent
        >>> from phone_agent.model import ModelConfig
        >>>
        >>> model_config = ModelConfig(base_url="http://localhost:8000/v1")
        >>> agent = PhoneAgent(model_config)
        >>> agent.run("Open WeChat and send a message to John")
    """

    def __init__(
        self,
        model_config: ModelConfig | None = None,
        agent_config: AgentConfig | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
    ):
        self.model_config = model_config or ModelConfig()
        self.agent_config = agent_config or AgentConfig()

        self.model_client = ModelClient(self.model_config)
        self.action_handler = ActionHandler(
            device_id=self.agent_config.device_id,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )

        # Initialize screenshot cache if enabled (lazy import to avoid circular dependency)
        self._screenshot_cache = None
        if self.agent_config.enable_screenshot_cache:
            from phone_agent.utils.screenshot_cache import ScreenshotCache
            device_id = self.agent_config.device_id
            get_screenshot_fn = lambda dev_id=device_id: get_screenshot(dev_id)
            self._screenshot_cache = ScreenshotCache(
                get_screenshot_fn, self.agent_config.screenshot_cache_max_age
            )

        self._context: list[dict[str, Any]] = []
        self._step_count = 0

    def run(self, task: str) -> str:
        """
        Run the agent to complete a task.

        Args:
            task: Natural language description of the task.

        Returns:
            Final message from the agent.
        """
        self.reset()

        # First step with user prompt
        result = self._execute_step(task, is_first=True)

        if result.finished:
            return result.message or "Task completed"

        # Continue until finished or max steps reached
        while self._step_count < self.agent_config.max_steps:
            # Check for manual takeover before each step
            if self.agent_config.takeover_check_callback:
                if self.agent_config.takeover_check_callback():
                    app_prefix = f"[{self.agent_config.app_name}] " if self.agent_config.app_name else ""
                    print(f"\n{app_prefix}⚠️ 任务已终止")
                    return "任务已终止"
            
            result = self._execute_step(is_first=False)

            if result.finished:
                return result.message or "Task completed"

        return "Max steps reached"

    def step(self, task: str | None = None) -> StepResult:
        """
        Execute a single step of the agent.

        Useful for manual control or debugging.

        Args:
            task: Task description (only needed for first step).

        Returns:
            StepResult with step details.
        """
        is_first = len(self._context) == 0

        if is_first and not task:
            raise ValueError("Task is required for the first step")

        return self._execute_step(task, is_first)

    def reset(self) -> None:
        """Reset the agent state for a new task."""
        self._context = []
        self._step_count = 0
        if self._screenshot_cache:
            self._screenshot_cache.invalidate()

    def _execute_step(
        self, user_prompt: str | None = None, is_first: bool = False
    ) -> StepResult:
        """Execute a single step of the agent loop."""
        self._step_count += 1

        # Capture current screen state (parallel execution for screenshot and app detection)
        get_screenshot_fn = self._screenshot_cache.get if self._screenshot_cache else lambda: get_screenshot(self.agent_config.device_id)
        with ThreadPoolExecutor(max_workers=2) as executor:
            screenshot_future = executor.submit(get_screenshot_fn)
            app_future = executor.submit(get_current_app, self.agent_config.device_id)
            screenshot, current_app = screenshot_future.result(), app_future.result()

        # Build messages
        if is_first:
            self._context.append(
                MessageBuilder.create_system_message(self.agent_config.system_prompt)
            )

            screen_info = MessageBuilder.build_screen_info(current_app)
            text_content = f"{user_prompt}\n\n{screen_info}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot.base64_data
                )
            )
        else:
            screen_info = MessageBuilder.build_screen_info(current_app)
            text_content = f"** Screen Info **\n\n{screen_info}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot.base64_data
                )
            )

        # Get model response
        try:
            msgs = get_messages(self.agent_config.lang)
            app_prefix = f"[{self.agent_config.app_name}] " if self.agent_config.app_name else ""
            print("\n" + "=" * 50)
            print(f"{app_prefix}💭 {msgs['thinking']}:")
            print("-" * 50)
            response = self.model_client.request(self._context, app_name=self.agent_config.app_name)
        except Exception as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            return StepResult(
                success=False,
                finished=True,
                action=None,
                thinking="",
                message=f"Model error: {e}",
            )

        # Parse action from response
        try:
            action = parse_action(response.action)
        except ValueError:
            if self.agent_config.verbose:
                traceback.print_exc()
            action = finish(message=response.action)
        
        # Force finish if "去凑单" scenario is detected (code-level enforcement)
        if action.get("_metadata") != "finish":
            from phone_agent.utils.price_extractor import is_coupon_scenario
            if is_coupon_scenario(f"{response.thinking or ''} {action.get('message', '')}"):
                action = finish(message=action.get('message') or response.thinking or "检测到凑单场景，已停止操作")
                if self.agent_config.verbose:
                    app_prefix = f"[{self.agent_config.app_name}] " if self.agent_config.app_name else ""
                    print(f"{app_prefix}[强制停止] 检测到'去凑单'场景，强制finish")
        
        # Check for privacy policy/login pages and trigger takeover
        if self.action_handler.takeover_callback:
            from phone_agent.utils.price_extractor import is_login_page, is_privacy_policy_page
            combined_text = f"{response.thinking or ''} {action.get('message', '')} {screen_info}"
            app_prefix = f"[{self.agent_config.app_name}] " if self.agent_config.verbose and self.agent_config.app_name else ""
            
            if "人机验证" in combined_text or "真人验证" in combined_text or "需要真人完成验证" in combined_text:
                action = do(action="Take_over", message="检测到人机验证页面，需要用户协助")
                if self.agent_config.verbose:
                    print(f"{app_prefix}[强制接管] 检测到人机验证页面，触发接管")
            elif is_privacy_policy_page(combined_text):
                action = do(action="Take_over", message="检测到隐私政策页面，需要用户协助")
                if self.agent_config.verbose:
                    print(f"{app_prefix}[强制接管] 检测到隐私政策页面，触发接管")
            elif is_login_page(combined_text):
                if action.get("_metadata") == "Type":
                    action = do(action="Take_over", message="检测到登录/验证码页面，禁止自动输入")
                    if self.agent_config.verbose:
                        print(f"{app_prefix}[强制接管] 登录页面禁止Type操作")
                # 移除finish时的强制接管：如果AI已决定finish，说明任务已完成，不应强制接管

        if self.agent_config.verbose:
            # Print thinking process
            app_prefix = f"[{self.agent_config.app_name}] " if self.agent_config.app_name else ""
            print("-" * 50)
            print(f"{app_prefix}🎯 {msgs['action']}:")
            print(json.dumps(action, ensure_ascii=False, indent=2))
            print("=" * 50 + "\n")

        # Remove image from context to save space
        self._context[-1] = MessageBuilder.remove_images_from_message(self._context[-1])

        # Execute action
        try:
            result = self.action_handler.execute(
                action, screenshot.width, screenshot.height
            )
        except Exception as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            result = self.action_handler.execute(
                finish(message=str(e)), screenshot.width, screenshot.height
            )
        
        # Invalidate cache after action execution (screen has changed)
        if self._screenshot_cache and action.get("_metadata") != "finish":
            self._screenshot_cache.invalidate()

        # Add assistant response to context
        self._context.append(
            MessageBuilder.create_assistant_message(
                f"<think>{response.thinking}</think><answer>{response.action}</answer>"
            )
        )

        # Check if finished
        finished = action.get("_metadata") == "finish" or result.should_finish

        if finished and self.agent_config.verbose:
            msgs = get_messages(self.agent_config.lang)
            app_prefix = f"[{self.agent_config.app_name}] " if self.agent_config.app_name else ""
            print("\n" + "🎉 " + "=" * 48)
            print(
                f"{app_prefix}✅ {msgs['task_completed']}: {result.message or action.get('message', msgs['done'])}"
            )
            print("=" * 50 + "\n")

        return StepResult(
            success=result.success,
            finished=finished,
            action=action,
            thinking=response.thinking,
            message=result.message or action.get("message"),
        )

    @property
    def context(self) -> list[dict[str, Any]]:
        """Get the current conversation context."""
        return self._context.copy()

    @property
    def step_count(self) -> int:
        """Get the current step count."""
        return self._step_count