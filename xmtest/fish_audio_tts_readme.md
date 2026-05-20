# Fish Audio TTS Migration README

## 1. 现在项目用的 TTS 是什么

当前 TTS 入口是：

```text
backend/conversation/services/tts.py
```

原来的默认实现是 OpenAI TTS：

```text
model: gpt-4o-mini-tts
voice: alloy
format: mp3
```

调用方主要有两个：

```text
backend/conversation/consumers.py
backend/conversation/services/profile_audio.py
```

前端不需要改。后端生成音频后仍然保存到 Django storage，并把 `audio_url` 返回给前端播放。

## 2. 本次已经修改了哪些文件

```text
config/settings/base.py
backend/conversation/services/tts.py
backend/conversation/tests/test_tts.py
docs/fish_audio_tts_readme.md
README.md
```

修改内容：

- `config/settings/base.py` 增加 TTS/Fish Audio 环境变量。
- `backend/conversation/services/tts.py` 增加 `TTS_PROVIDER=fish` 分支，调用 `https://api.fish.audio/v1/tts`。
- `backend/conversation/tests/test_tts.py` 增加 Fish Audio 请求参数测试。
- 本 README 记录切换、测试和排错步骤。

## 3. Fish Audio API 选择

官方参考：

```text
https://docs.fish.audio/api-reference/endpoint/openapi-v1/text-to-speech
https://docs.fish.audio/developer-guide/core-features/text-to-speech
https://docs.fish.audio/developer-guide/models-pricing/models-overview#s2-natural-language-control
```

推荐模型：

```text
s2-pro
```

Fish 官方文档说明 `s2-pro` 是推荐的新项目模型，支持 `[bracket]` 自然语言情绪控制，例如：

```text
[excited] I just won the lottery! [sad] But then I lost the ticket.
```

接口：

```text
POST https://api.fish.audio/v1/tts
Authorization: Bearer $FISH_API_KEY
Content-Type: application/json
model: s2-pro
```

常用声音 ID：

```sh
# 女声
export FISH_TTS_REFERENCE_ID="8ef4a238714b45718ce04243307c57a7"

# 男声
export FISH_TTS_REFERENCE_ID="802e3bc2b27e49c2995d23ef70e6ac89"
```

注意：`reference_id` 必须是当前 Fish API key 有权限访问的声音。若 Fish 返回 `{"message":"Reference not found","status":400}`，先把 `FISH_TTS_REFERENCE_ID` 留空，确认默认声音可以生成；之后再换成你 Fish 控制台里可用的 voice/reference ID。

## 4. 本地切换步骤

### Step 1: 配置环境变量

如果你直接在本机跑 Django：

```sh
export TTS_PROVIDER="fish"
export FISH_API_KEY="xxxxx"
export FISH_TTS_MODEL="s2-pro"
export FISH_TTS_FORMAT="mp3"
export FISH_TTS_REFERENCE_ID="8ef4a238714b45718ce04243307c57a7"
```

如果你用 Docker，本地 secrets/env 文件里加同样的变量。项目 README 里原本使用：

```sh
cp ./envs/.local/.secrets.example ./envs/.local/.secrets
```

所以优先检查你实际存在并被 Docker Compose 读取的本地 env/secrets 文件，把下面内容加进去：

```text
TTS_PROVIDER=fish
FISH_API_KEY=xxxxx
FISH_TTS_MODEL=s2-pro
FISH_TTS_FORMAT=mp3
FISH_TTS_REFERENCE_ID=
CEFR_TTS_MAX_WORKERS=0
```

### Step 2: 重启后端

Docker：

```sh
docker compose -f docker-compose.local.yml up
```

本机：

```sh
python manage.py runserver
```

### Step 3: 先用 curl 单独验证 Fish Audio

```sh
export FISH_API_KEY="xxxxx"

curl -X POST https://api.fish.audio/v1/tts \
  -H "Authorization: Bearer $FISH_API_KEY" \
  -H "Content-Type: application/json" \
  -H "model: s2-pro" \
  -d '{
    "text": "[excited] I just won the lottery! [sad] But then I lost the ticket. [laughing] Just kidding, I found it!",
    "format": "mp3"
  }' \
  --output fish_test.mp3
```

带指定声音：

```sh
export REFERENCE_ID="802e3bc2b27e49c2995d23ef70e6ac89"

curl -X POST https://api.fish.audio/v1/tts \
  -H "Authorization: Bearer $FISH_API_KEY" \
  -H "Content-Type: application/json" \
  -H "model: s2-pro" \
  -d '{
    "text": "This is a custom voice from Fish Audio.",
    "reference_id": "'"$REFERENCE_ID"'",
    "format": "mp3"
  }' \
  --output fish_custom_voice.mp3
```

### Step 4: 用 Django shell 验证项目内 TTS

Docker：

```sh
docker compose -f docker-compose.local.yml run --rm django python manage.py shell
```

如果容器已经在运行，也可以显式经过 entrypoint；本项目的 `DATABASE_URL` 是 entrypoint 动态生成的：

```sh
docker compose -f docker-compose.local.yml exec django /entrypoint python manage.py shell
```

本机：

```sh
python manage.py shell
```

进入 shell 后执行：

```py
from backend.conversation.services.tts import synthesize_speech

url = synthesize_speech(text="[excited] Hello from Fish Audio!")
print(url)
```

看到 `/media/audio/...mp3` URL 就说明项目内生成和保存都成功。

### Step 5: 跑自动化测试

先确认你在项目依赖环境里，而不是 Anaconda `base` 环境。这个项目需要 `pytest-django` 和 `celery` 等依赖；如果缺少 `pytest-django`，会出现 `unrecognized arguments: --ds=config.settings.test` 或 `settings are not configured`。

Docker 推荐：

```sh
docker compose -f docker-compose.local.yml run --rm django pytest backend/conversation/tests/test_tts.py
```

如果用 `exec` 进入已经运行的 `django` 容器，命令前要加 `/entrypoint`，否则会缺少 entrypoint 动态生成的 `DATABASE_URL`：

```sh
docker compose -f docker-compose.local.yml exec django /entrypoint pytest backend/conversation/tests/test_tts.py
```

本机虚拟环境：

```sh
python -m pip install -r requirements/local.txt
python -m pip install -r requirements/base.txt
```

然后运行：

```sh
pytest backend/conversation/tests/test_tts.py
```

如果想顺手验证 CEFR sample 的 TTS 调用链：

```sh
pytest backend/conversation/tests/test_profile_audio.py backend/conversation/tests/test_tts.py
```

## 5. 可配置项

```text
TTS_PROVIDER=openai | fish
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=alloy
FISH_API_KEY=xxxxx
FISH_TTS_MODEL=s2-pro
FISH_TTS_REFERENCE_ID=8ef4a238714b45718ce04243307c57a7
FISH_TTS_FORMAT=mp3
FISH_TTS_TIMEOUT_SEC=60
CEFR_TTS_MAX_WORKERS=0
```

说明：

- `TTS_PROVIDER=fish` 才会启用 Fish Audio。
- `FISH_TTS_REFERENCE_ID` 为空时，Fish 会使用默认声音。
- `CEFR_TTS_MAX_WORKERS=0` 表示自动模式；Fish TTS 下默认串行生成 CEFR 音频，避免 6 条 sample 同时请求触发 429 限流。确认账号额度足够后可以改成 `2` 或更高。
- 如果 `AgentProfile.voice` 写的是 Fish voice/model ID，代码会优先用它作为 `reference_id`。
- 如果 `AgentProfile.voice` 还是 `alloy`、`nova` 等 OpenAI 声音名，Fish 分支会忽略它，改用 `FISH_TTS_REFERENCE_ID`。

## 6. 常见问题

### 生成后没有声音

检查后端日志是否出现 Fish API 的 401/403/429/5xx。最常见原因是：

- `FISH_API_KEY` 没配或配错。
- Docker 容器没有读取到新的 env/secrets，需要重启。
- Fish 账户余额、权限或限流问题。

### 情绪控制没有效果

`s2-pro` 推荐使用 `[bracket]` 风格：

```text
[excited] Great news! [whisper] I have a secret.
```

`s1` 更偏向旧的 `(parenthesis)` 风格。新项目优先使用 `s2-pro`。

### 想给不同 agent 不同声音

在 Django admin 里把对应 `AgentProfile.voice` 填成 Fish 的 voice/model ID，例如：

```text
802e3bc2b27e49c2995d23ef70e6ac89
```

这样该 agent 的 TTS 会使用自己的 `reference_id`。没有单独配置时，会回退到 `FISH_TTS_REFERENCE_ID`。
