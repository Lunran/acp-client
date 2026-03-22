import asyncio
import sys
from pathlib import Path

from acp import PROTOCOL_VERSION, Client, connect_to_agent
from acp.schema import ClientCapabilities, Implementation
from session_models import resolve_model

HOST = "localhost"
PORT = 8100
SESSION_FILE = Path(__file__).parent / ".session_id"
WORK_CWD = "/workspace"


class CheckInfoClient(Client):
	async def session_update(self, session_id: str, update: object, **kwargs: object) -> None:
		return None

async def _load_or_create_session(conn: object) -> object:
	saved_id = SESSION_FILE.read_text().strip() if SESSION_FILE.exists() else None
	if saved_id:
		try:
			return await conn.load_session(
				session_id=saved_id,
				cwd=WORK_CWD,
				mcp_servers=[],
			)
		except Exception:
			pass

	session = await conn.new_session(cwd=WORK_CWD, mcp_servers=[])
	SESSION_FILE.write_text(session.session_id)
	return session


async def main() -> int:
	try:
		reader, writer = await asyncio.open_connection(HOST, PORT, limit=2**28)
	except Exception as exc:
		print(f"Error connecting to ACP server: {type(exc).__name__}: {exc}", file=sys.stderr)
		return 1

	client = CheckInfoClient()
	conn = connect_to_agent(client, writer, reader)

	try:
		await conn.initialize(
			protocol_version=PROTOCOL_VERSION,
			client_capabilities=ClientCapabilities(),
			client_info=Implementation(
				name="check-info-client",
				version="0.1.0",
			),
		)

		session = await _load_or_create_session(conn)
		print(session)
		model_name, model_id = resolve_model(session)
		if not model_id:
			print("Current model: unavailable")
			return 1

		if model_name and model_name != model_id:
			print(f"Current model: {model_name} ({model_id})")
		else:
			print(f"Current model: {model_id}")
		return 0
	except Exception as exc:
		print(f"Error retrieving model info: {type(exc).__name__}: {exc}", file=sys.stderr)
		return 1
	finally:
		writer.close()
		try:
			await writer.wait_closed()
		except ConnectionError:
			pass


if __name__ == "__main__":
	raise SystemExit(asyncio.run(main()))
