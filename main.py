import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

import discord
import dotenv
import schedule
from acp import (
    PROTOCOL_VERSION,
    Client,
    connect_to_agent,
    text_block,
)
from acp.schema import (
    AllowedOutcome,
    AgentMessageChunk,
    ClientCapabilities,
    DeniedOutcome,
    Implementation,
    PermissionOption,
    RequestPermissionResponse,
    TextContentBlock,
)
from session_models import (
    format_available_model_choices,
    get_model_config_option,
    list_available_model_ids,
    resolve_model,
)

logging.basicConfig(level=logging.INFO)
dotenv.load_dotenv()

HOST = "localhost"
PORT = 8100
SESSION_FILE = Path(__file__).parent / ".session_id"
MODEL_ID = "claude-haiku-4.5"
WORK_CWD = "/workspace" # Server cwd (container path in Docker environment)
SCHEDULE_TIMEZONE = "Asia/Tokyo"
SCHEDULE_JOBS = [
    ("07:15", "Fetch Misc feed using RSS skill"),
    ("12:00", "Fetch Blog feed using RSS skill"),
    ("18:00", "Check Gmail and Google Calendar"),
    ("21:30", "Fetch Focus feed using RSS skill"),
]

_DISCORD_CHUNK_SIZE = 1990  # Discord message split size with margin for 2000 character limit


def _split_message(text: str) -> list[str]:
    """Split message to fit within 2000 character limit"""
    parts = []
    while len(text) > _DISCORD_CHUNK_SIZE:
        parts.append(text[:_DISCORD_CHUNK_SIZE])
        text = text[_DISCORD_CHUNK_SIZE:]
    if text:
        parts.append(text)
    return parts


def _describe_available_models(session: object) -> str:
    available = format_available_model_choices(session)
    if not available:
        return "(agent did not report available models)"
    return ", ".join(available)


async def _ensure_session_model(conn: Any, session_id: str, session: object, model_id: str) -> None:
    _, current_model_id = resolve_model(session)
    if current_model_id == model_id:
        print(f"Session model already set: {model_id}", flush=True)
        return

    available_model_ids = list_available_model_ids(session)
    if available_model_ids and model_id not in available_model_ids:
        raise RuntimeError(
            f"Requested model {model_id!r} is unavailable. "
            f"Available choices: {_describe_available_models(session)}"
        )

    model_config = get_model_config_option(session)
    if model_config is not None:
        config_id = getattr(model_config, "id", None)
        if not isinstance(config_id, str) or not config_id:
            raise RuntimeError("ACP model config option is missing an id.")

        await conn.set_config_option(
            session_id=session_id,
            config_id=config_id,
            value=model_id,
        )
        print(f"Changed session model via config option: {current_model_id} -> {model_id}", flush=True)
        return

    print(f"Selecting session model via session model API: {model_id}", flush=True)
    await conn.set_session_model(session_id=session_id, model_id=model_id)


async def _send_scheduled_prompt(
    prompt_text: str,
    bot: discord.Client,
    discord_user_id: int,
    conn: Any,
    session_id: str,
    client_impl: "MyClient",
    lock: asyncio.Lock,
) -> None:
    """Send scheduled prompt to ACP and notify response via Discord DM"""
    print(f"[Schedule] Sending: {prompt_text!r}")
    async with lock:
        client_impl.clear_buffer()
        try:
            await conn.prompt(
                session_id=session_id,
                prompt=[text_block(prompt_text)],
            )
            await asyncio.sleep(0.2)
        except Exception as e:
            print(f"[Schedule] Error: {type(e).__name__}: {e}")
            return

        full_response = client_impl.get_buffered_response()
        print("\n")

        if not full_response:
            full_response = "(no response)"

    try:
        user = await bot.fetch_user(discord_user_id)
        for part in _split_message(full_response):
            await user.send(part)
    except Exception as e:
        print(f"[Schedule] Failed to send DM: {type(e).__name__}: {e}")


async def _run_schedule_loop() -> None:
    """Periodically run pending schedule jobs"""
    while True:
        schedule.run_pending()
        await asyncio.sleep(30)


class MyClient(Client):
    """Handler that displays notifications from server"""

    def __init__(self) -> None:
        super().__init__()
        self._response_buffer: list[str] = []

    def clear_buffer(self) -> None:
        self._response_buffer.clear()

    def get_buffered_response(self) -> str:
        return "".join(self._response_buffer)

    async def request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: Any,
        **kwargs: Any,
    ) -> RequestPermissionResponse:
        preferred_kinds = ("allow_once", "allow_always")
        selected = next((opt for opt in options if opt.kind in preferred_kinds), None)
        if selected is None and options:
            selected = options[0]

        if selected and selected.kind.startswith("allow"):
            return RequestPermissionResponse(
                outcome=AllowedOutcome(outcome="selected", optionId=selected.option_id),
            )

        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        if isinstance(update, AgentMessageChunk):
            content = update.content
            if isinstance(content, TextContentBlock):
                text = content.text
                if text:
                    self._response_buffer.append(text)
                    print(text, end="", flush=True)


async def main() -> int:
    args = sys.argv[1:]

    discord_bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    user_id = os.environ.get("DISCORD_USER_ID")

    if not discord_bot_token:
        print("Error: DISCORD_BOT_TOKEN environment variable is not set.", file=sys.stderr)
        return 1
    if not user_id:
        print("Error: DISCORD_USER_ID environment variable is not set.", file=sys.stderr)
        return 1
    try:
        discord_user_id = int(user_id)
    except ValueError:
        print("Error: DISCORD_USER_ID must be an integer.", file=sys.stderr)
        return 1

    print(f"Connecting to ACP server at {HOST}:{PORT}...")

    try:
        reader, writer = await asyncio.open_connection(HOST, PORT, limit=2**28)
    except Exception as e:
        print(f"Error connecting to ACP server: {type(e).__name__}: {e}")
        return 1

    client_impl = MyClient()
    conn = connect_to_agent(client_impl, writer, reader)
    lock = asyncio.Lock()

    print("Initializing ACP connection...")
    try:
        await conn.initialize(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=ClientCapabilities(),
            client_info=Implementation(
                name="my-custom-client",
                version="0.1.0",
            ),
        )
    except Exception as e:
        print(f"Error initializing ACP: {type(e).__name__}: {e}")
        writer.close()
        return 1

    # Load saved session ID if exists, otherwise create new one and save it
    saved_id = SESSION_FILE.read_text().strip() if SESSION_FILE.exists() else None
    should_persist_session_id = False
    if saved_id:
        try:
            print(f"Loading session: {saved_id}")
            session = await conn.load_session(
                session_id=saved_id,
                cwd=WORK_CWD,
                mcp_servers=[],
            )
            session_id = saved_id
        except Exception:
            print("Session expired, creating new session...")
            session = await conn.new_session(cwd=WORK_CWD, mcp_servers=[])
            session_id = session.session_id
            should_persist_session_id = True
            print(f"New session created: {session_id}")
    else:
        print("Creating new session...")
        session = await conn.new_session(cwd=WORK_CWD, mcp_servers=[])
        session_id = session.session_id
        should_persist_session_id = True
        print(f"New session created: {session_id}")

    try:
        await _ensure_session_model(conn, session_id, session, MODEL_ID)
    except Exception as e:
        print(f"Error selecting session model: {type(e).__name__}: {e}", file=sys.stderr)
        writer.close()
        return 1

    if should_persist_session_id:
        SESSION_FILE.write_text(session_id)

    # Discord Bot setup
    intents = discord.Intents.default()
    intents.message_content = True
    intents.dm_messages = True
    bot = discord.Client(intents=intents)

    @bot.event
    async def on_ready() -> None:
        print(f"Discord bot ready: {bot.user} (DM with user_id={discord_user_id})")

        loop = asyncio.get_event_loop()

        def make_job(prompt_text: str):
            def job() -> None:
                loop.create_task(
                    _send_scheduled_prompt(prompt_text, bot, discord_user_id, conn, session_id, client_impl, lock)
                )
            return job

        for scheduled_time, prompt_text in SCHEDULE_JOBS:
            schedule.every().day.at(scheduled_time, SCHEDULE_TIMEZONE).do(make_job(prompt_text))

        asyncio.create_task(_run_schedule_loop())
        registered_jobs = " / ".join(f"{scheduled_time} {prompt_text}" for scheduled_time, prompt_text in SCHEDULE_JOBS)
        print(f"[Schedule] Jobs registered: {registered_jobs} ({SCHEDULE_TIMEZONE})")

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if message.author == bot.user:
            return
        # Only process DM channels from DISCORD_USER_ID user
        if not isinstance(message.channel, discord.DMChannel):
            return
        if message.author.id != discord_user_id:
            return

        user_input = message.content.strip()
        if not user_input:
            return

        print(f"[Discord] {message.author}: {user_input}")

        async with lock:
            client_impl.clear_buffer()
            try:
                response = await conn.prompt(
                    session_id=session_id,
                    prompt=[text_block(user_input)],
                )
                await asyncio.sleep(0.2)
            except Exception as e:
                err_msg = f"Error: {type(e).__name__}: {e}"
                print(err_msg)
                await message.channel.send(err_msg)
                return

            full_response = client_impl.get_buffered_response()
            print("\n")

            if not full_response:
                full_response = "(no response)"

            for part in _split_message(full_response):
                await message.channel.send(part)

    try:
        await bot.start(discord_bot_token)
    except Exception as e:
        print(f"Discord bot error: {type(e).__name__}: {e}")
    finally:
        if not writer.is_closing():
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
