# 災害志工派工 API

這是一個以 FastAPI 建置的災害志工派工服務。系統可接收事件任務、工作類型與志工資料，依技能、距離與任務急迫度產生派工結果，並可透過 LINE 發送報名連結與派工摘要。

目前支援兩種主要操作路徑：

1. 整合表單團報：主辦端先建立事件與任務，系統開放公開報名表，志工填表後由系統整批派工。
2. 志工個人報名：志工透過 LINE 個人連結或 API 登記個人資料，再納入後續派工。

詳細操作請見 [操作模式文件](docs/OPERATION_MODES.md)，完整 endpoint 與資料模型請見 [技術規格文件](docs/SPECIFICATION.md)。

## 功能摘要

- 依技能、距離、急迫度進行 deterministic volunteer assignment。
- 支援三種派工權重：`balanced`、`speed`、`expertise`。
- 可選用 Ollama 做 AI 異常檢查；Ollama 不可用時會自動退回純演算法模式。
- 支援 LINE 群組公告、個人報名連結、公開報名表與 LINE webhook。
- 支援地址轉座標，需設定 `GOOGLE_MAPS_API_KEY`。

## 快速啟動

```bash
python -m pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

健康檢查：

```bash
curl http://127.0.0.1:8000/health
```

直接派工測試：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/dispatch \
  -H "Content-Type: application/json" \
  -d @sample_payloads.json
```

## 環境變數

| 變數 | 說明 |
| --- | --- |
| `LINE_CHANNEL_SECRET` | LINE Messaging API channel secret，啟用 webhook 與訊息推送時必填。 |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API access token，啟用訊息推送時必填。 |
| `LINE_GROUP_ID` | 預設發送公告的 LINE 群組 ID。 |
| `APP_BASE_URL` | 對外可存取的服務網址，用於產生報名表連結。 |
| `GOOGLE_MAPS_API_KEY` | 地址轉座標使用。若未設定，填地址的報名會失敗；可改填經緯度。 |
| `OLLAMA_BASE_URL` | Ollama 服務網址，預設 `http://localhost:11434`。 |
| `OLLAMA_MODEL_DEBUG` | AI 異常檢查模型，預設 `neural-chat`。 |

## LINE / ngrok 設定

1. 啟動 API：

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

2. 用 ngrok 暴露本機服務：

```bash
ngrok http 8000
```

3. 將 ngrok 網址設定為 `APP_BASE_URL`：

```bash
APP_BASE_URL=https://xxxxxx.ngrok-free.dev
```

4. 在 LINE Developer Console 設定 webhook URL：

```text
https://<your-ngrok-domain>.ngrok-free.dev/webhook
```

## 主要文件

- [技術規格文件](docs/SPECIFICATION.md)：每個 endpoint 的功能、request、response 與注意事項。
- [操作模式文件](docs/OPERATION_MODES.md)：整合表單團報與志工個人報名的操作流程。

## 測試

```bash
python test_dispatch.py
```
