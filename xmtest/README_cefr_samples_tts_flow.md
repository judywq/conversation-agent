# Conversation 页面「Generate CEFR samples」→ TTS 调用链说明

本文说明：在本地前端（例如 `http://localhost:5173/app/conversation`）的 **Topic** 中输入话题后，点击 **Generate CEFR samples** 时，**TTS 模型是如何被调用的**（不包含 LLM 生成英文文本的细节，只补充一句流程位置）。

---

## 1. 你在页面上的操作

1. 在 **Topic** 文本框输入内容（例如 `xxxx` 或任意讨论主题）。
2. 点击 **Generate CEFR samples**。

前置条件（由前端控制）：需要已登录，且用户资料 `profile_completed` 为已完成；同时需要已连接 WebSocket（`connected`），且当前**没有**进行中的会话（`sessionId` 为空），否则会禁用该按钮。

相关代码：`vue_frontend/src/views/ConversationView.vue`（函数 `generateCefrSamples` 及按钮 `disabled` 条件）。

---

## 2. 前端发什么请求

`ConversationView.vue` 调用：

```ts
ConversationService.generateCefrSamples(trimmedTopic)
```

`ConversationService` 实现（`vue_frontend/src/services/conversationService.ts`）：

- **方法**：`POST`
- **路径**：`/conversation/cefr-samples/`
- **Body**：`{ "topic": "<你输入的 Topic 文本>" }`
- **超时**：180000 ms（3 分钟），因为后端要跑 LLM + 6 段 TTS。

实际请求 URL 为：`VITE_API_BASE_URL` + 上述路径（例如本地后端 `http://127.0.0.1:8000` 时，常为 `http://127.0.0.1:8000/conversation/cefr-samples/`）。需携带登录 Cookie / CSRF（`api.ts` 已配置 `withCredentials` 与 `X-CSRFToken`）。

---

## 3. 后端入口

- URL 配置：`backend/conversation/api_urls.py` → `path("cefr-samples/", CefrTopicSamplesView, ...)`
- 视图：`backend/conversation/api_views.py` 中的 `CefrTopicSamplesView.post`

视图在校验 `topic` 后调用：

```python
samples = generate_cefr_topic_samples(topic=topic)
```

若用户存在 `userprofile`，会把返回的 `samples` 写入 `userprofile.cefr_sample_choices` 并保存。

---

## 4. TTS 在何处、怎样被调用（核心）

全部逻辑在：`backend/conversation/services/profile_audio.py` → `generate_cefr_topic_samples()`。

### 4.1 在调用 TTS 之前（简述）

1. 加载提示词模板 `cefr_topic_samples.txt`，把 **Topic** 填入模板。
2. 用 **默认聊天 LLM**（`get_default_chat_llm()`）生成一段 JSON，解析出 A1–C2 六个等级对应的英文短句文本。

### 4.2 TTS 调用方式

对每个 CEFR 等级（`A1, A2, B1, B2, C1, C2`），在 `synthesize_level` 内调用：

```python
audio_url = synthesize_speech(text=text, voice=voice)
```

其中 `voice` 来自函数参数默认值 **`"alloy"`**（`generate_cefr_topic_samples(..., voice="alloy")`），API 视图没有传入自定义 `voice`，因此始终为 **alloy**（在 Fish 分支下的含义见下文）。

并发：使用 `ThreadPoolExecutor`，`max_workers` 由 `_cefr_tts_max_workers()` 决定：

- 若 `CEFR_TTS_MAX_WORKERS > 0`：取 `min(配置值, 6)`。
- 若未配置（0）且 `TTS_PROVIDER == "fish"`：**串行**（`max_workers=1`），减轻 Fish API 限流。
- 否则 **OpenAI TTS**：默认 **`max_workers=6`**（六个等级并行）。

### 4.3 真正「选用哪个 TTS 模型」

实现位于：`backend/conversation/services/tts.py` → `synthesize_speech()`。

根据 Django 设置 **`TTS_PROVIDER`** 分支：

| `TTS_PROVIDER` | 使用的模型环境变量 | 默认模型名 | 说明 |
|----------------|-------------------|------------|------|
| **`openai`**（未设置时的代码默认） | `OPENAI_TTS_MODEL` | `gpt-4o-mini-tts` | 使用 OpenAI Python SDK：`client.audio.speech.create(model=..., voice=..., ...)`。API Key 来自 Admin 里配置的 **OpenAI 类型** `APIKey`。 |
| **`fish`** | `FISH_TTS_MODEL` | `s2-pro` | 使用 HTTP `POST https://api.fish.audio/v1/tts`，请求头里带 **`model: <FISH_TTS_MODEL>`**，Bearer 为 `FISH_API_KEY`。 |

音色 / 参考音：

- **OpenAI**：`voice` 使用 `OPENAI_TTS_VOICE`（默认 `alloy`），可被调用方传入的 `voice` 覆盖。
- **Fish**：`voice` 若不是内置 OpenAI 音色名，则视为 **`reference_id`**；若仍是 `alloy` 等内置名且未设自定义 ID，则使用 **`FISH_TTS_REFERENCE_ID`**（可空）。

因此：在 **`TTS_PROVIDER=fish`** 且 **`FISH_TTS_REFERENCE_ID` 为空** 时，CEFR 仍传 `voice="alloy"`，最终 **不会**把 `alloy` 当作 Fish 的 `reference_id`，`reference_id` 可能为空（具体是否由 Fish 使用默认音色，以 Fish API 行为为准）。

### 4.4 配置来源（与本仓库常见本地文件）

默认值在 `config/settings/base.py`：

- `TTS_PROVIDER`（默认 `openai`）
- `OPENAI_TTS_MODEL`（默认 `gpt-4o-mini-tts`）
- `OPENAI_TTS_VOICE`（默认 `alloy`）
- `FISH_TTS_MODEL`（默认 `s2-pro`）
- `FISH_TTS_FORMAT`、`FISH_TTS_REFERENCE_ID`、`CEFR_TTS_MAX_WORKERS` 等

本地可覆盖：例如 `.envs/.local/.secrets` 中的 `TTS_PROVIDER`、`FISH_TTS_MODEL` 等（以你实际加载的环境为准）。

---

## 5. 响应里你能看到什么

后端返回 JSON 形状大致为：

```json
{
  "topic": "...",
  "samples": [
    { "level": "A1", "text": "...", "audio_url": "http://<DOMAIN><MEDIA_URL>audio/<uuid>.<format>" },
    ...
  ]
}
```

`audio_url` 由 `synthesize_speech` 把音频写入默认存储（通常 `MEDIA_ROOT` 下 `audio/`）后，用 `DOMAIN_NAME` + `MEDIA_URL` 拼出的可访问 URL。前端列表里可用该 URL 播放试听。

---

## 6. 相关文件一览

| 环节 | 文件 |
|------|------|
| 页面与按钮 | `vue_frontend/src/views/ConversationView.vue` |
| HTTP 客户端 | `vue_frontend/src/services/conversationService.ts`、`vue_frontend/src/services/api.ts` |
| API 视图 | `backend/conversation/api_views.py`（`CefrTopicSamplesView`） |
| CEFR 流水线（LLM + TTS 池） | `backend/conversation/services/profile_audio.py` |
| TTS 提供商与模型 | `backend/conversation/services/tts.py`、`config/settings/base.py` |

---

## 7. 小结

- **Generate CEFR samples** 会请求 **`POST /conversation/cefr-samples/`**，后端用 LLM 生成 6 段文本后，对每段调用 **`synthesize_speech`**。
- **实际 TTS 模型**由 **`TTS_PROVIDER`** 决定：OpenAI 默认 **`gpt-4o-mini-tts`**，Fish 默认 **`s2-pro`**（见环境变量覆盖）。
- Fish 模式下 CEFR 一般为 **单线程依次合成 6 段**，以降低限流风险。
