# 救災志工智慧分配 API

本專案提供「確定性演算法」的災害任務志工指派服務，並以「路線距離估算」、「技能匹配」與「任務緊急度」作為核心權重。
AI 僅用於「異常檢查」與驗證提示，非主要分派決策。

## 核心功能

- deterministic volunteer assignment（不依賴 AI 作指派）
- route-based distance estimation for ETA and scoring
- skill matching and urgency-aware scoring
- priority weighting: `balanced`, `speed`, `expertise`
- optional AI anomaly check via Ollama
- LINE volunteer registration endpoint
- built-in fallback: 即使 AI 不可用也能正常分派

## API 端點

### POST /api/v1/dispatch

- 輸入：`DispatchRequest`
- 輸出：`DispatchResponse`
- 功能：根據 volunteer 可用性、任務緊急度、技能匹配與路徑距離進行任務指派。

### POST /api/v1/line/register

- 輸入：`LineVolunteerRegistration`
- 輸出：`LineRegisterResponse`
- 功能：註冊 LINE 志工資料並支援群組管理。

### GET /health

- 功能：回傳 API 健康狀態與 Ollama 連線狀態。

### GET /

- 功能：基本服務存活檢查。

## 資料模型

### DispatchRequest

- `metadata`
  - `incident_id`: 事件識別碼
  - `priority_weighting`: `balanced` / `speed` / `expertise`
- `work_types`
  - `type_id`, `required_skills`
- `volunteers`
  - `id`, `skills`, `location`, `availability`
- `tasks`
  - `id`, `type_id`, `location`, `urgency`

### DispatchResponse

- `status`: `success`
- `dispatch_id`: UUID
- `incident_id`
- `mode`: `algorithm_only` 或 `algorithm_with_ai_anomaly_check`
- `assignments`: 任務分派結果
- `unassigned_tasks`: 未指派任務清單
- `warnings`: 異常或狀態提醒

### Assignment

- `task_id`
- `assigned_volunteers`
- `eta_minutes`
- `confidence`
- `score_breakdown`
- `reasoning_summary`

### ScoreBreakdown

- `skill_score`
- `distance_score`
- `urgency_score`
- `final_score`

## 範例請求

```json
{
  "metadata": {"incident_id": "incident-2026-001", "priority_weighting": "balanced"},
  "work_types": [
    {"type_id": "medical", "required_skills": ["medical", "firstaid"]}
  ],
  "volunteers": [
    {
      "id": "vol_01",
      "skills": ["medical", "firstaid"],
      "location": {"lat": 23.654, "lng": 121.432},
      "availability": true
    }
  ],
  "tasks": [
    {
      "id": "task_101",
      "type_id": "medical",
      "location": {"lat": 23.656, "lng": 121.435},
      "urgency": 5
    }
  ]
}
```

## 範例回應

```json
{
  "status": "success",
  "dispatch_id": "uuid-xxx",
  "incident_id": "incident-2026-001",
  "mode": "algorithm_with_ai_anomaly_check",
  "assignments": [
    {
      "task_id": "task_101",
      "assigned_volunteers": ["vol_01"],
      "eta_minutes": 6,
      "confidence": 0.88,
      "score_breakdown": {
        "skill_score": 1.0,
        "distance_score": 0.9,
        "urgency_score": 1.0,
        "final_score": 0.88
      },
      "reasoning_summary": "已依據技能、距離與緊急度進行指派。"
    }
  ],
  "unassigned_tasks": [],
  "warnings": ["系統已完成演算法分配與本地異常檢查，未發現顯著異常。"]
}
```

## 安裝與啟動

```bash
python -m pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
## 本地運作測試（使用 ngrok）

1. 啟動本地服務：

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

2. 啟動 ngrok 並建立公開網址：

```bash
ngrok http 8000
```

3. 將 ngrok 生成的 `https://...` 公開網址，設定到 `.env` 中的 `APP_BASE_URL`：

```bash
APP_BASE_URL=https://xxxxxx.ngrok-free.dev
```

4. 若要測試 LINE webhook，請在 LINE Developer Console 或 LINE Messaging API webhook 設定中，將 Webhook URL 設為：

```text
https://<your-ngrok-domain>.ngrok-free.dev/webhook
```

5. 本地測試時你也可以直接呼叫健康檢查與 dispatch API：

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/v1/dispatch -H "Content-Type: application/json" -d @sample_payloads.json
```

> 注意：本服務的派工邏輯主要由本地確定性演算法負責；若 Ollama 無法連線，仍會回傳 `algorithm_only` 結果。
## AI 異常檢查

系統會在本地演算法分派完成後，嘗試使用 Ollama 進行額外異常檢查；若無法連線，仍然會回傳分派結果，並將 `mode` 設為 `algorithm_only`。

## LINE 志工註冊

`POST /api/v1/line/register` 可登錄 LINE 志工資料，回傳 `group_id`。

## 測試

```bash
python test_dispatch.py
```
