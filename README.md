# What's this?

ACP client that uses GitHub Copilot CLI launched as an ACP server

# How to use

1. Start GitHub Copilot CLI as an ACP server.

```sh
copilot --acp --port 8100
```

- Running it inside a sandbox improves security.
    - ref. https://zenn.dev/lunran/scraps/5105de92cb9687

```sh
docker ps -a --format '{{.Names}}' | grep -q "^copilot-acp-container$" && \
docker start -ai copilot-acp-container || \
docker run -it \
      --name copilot-acp-container \
      -p 8100:8100 \
      -v $(pwd):/workspace \
      -v ./.copilot:/home/agent/.copilot \
      -e GITHUB_TOKEN=$GITHUB_TOKEN \
      copilot-sandbox \
      copilot --acp --port 8100 --autopilot --yolo --model gpt-5-mini
```

2. Configure Discord settings and start the ACP client.

```sh
git clone https://github.com/Lunran/acp-client.git
cd acp-client
cp .env.example .env
```

- Edit the .env file with Discord settings.

```sh
uv sync
uv run python main.py
```
