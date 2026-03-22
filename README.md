# What's this?

ACPサーバとして起動した Github Copilot CLI を利用するACPクライアント

# How to use

1. GitHub Copilot CLI をACPサーバとして起動する。

```sh
copilot --acp --port 8100
```

- サンドボックス内で起動することで、安全性を向上できる。
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

2 . Discord設定を行い、ACPクライアントを起動する。

```sh
git clone https://github.com/Lunran/acp-client.git
cd acp-client
cp .env.example .env
.envファイルにDiscordの設定を記載する。
uv sync
uv run python main.py
```
