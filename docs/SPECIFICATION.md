# 救災志工指派服務規格

## 1. 概述

本服務以決定性演算法為主，透過技能匹配、路線距離與任務緊急度計算志工指派分數。
AI 僅作為「後置異常檢查」使用，並不做為主要指派決策。

## 2. 資料模型

### Location

- `lat`: float
- `lng`: float

### Metadata

- `incident_id`: string
- `priority_weighting`: `balanced` / `speed` / `expertise`

### WorkType

- `type_id`: string
- `required_skills`: string[]

### Volunteer

- `id`: string
- `skills`: string[]
- `location`: Location
- `availability`: boolean
- `age`: optional int
- `line_user_id`: optional string
- `special_skills`: optional string[]

### Task

- `id`: string
- `type_id`: string
- `location`: Location
- `urgency`: int (1-5)

### DispatchRequest

請求格式包含 `metadata`, `work_types`, `volunteers`, `tasks`。

### ScoreBreakdown

- `skill_score`: 0.0-1.0
- `distance_score`: 0.0-1.0
- `urgency_score`: 0.0-1.0
- `final_score`: 0.0-1.0

### Assignment

- `task_id`
- `assigned_volunteers`
- `eta_minutes`
- `confidence`
- `score_breakdown`
- `reasoning_summary`

### DispatchResponse

- `status`
- `dispatch_id`
- `incident_id`
- `mode`
- `assignments`
- `unassigned_tasks`
- `warnings`

### LineVolunteerRegistration

- `line_user_id`
- `display_name`
- `group_id` (optional)
- `skills` (optional)
- `location` (optional)

### LineRegisterResponse

- `status`
- `line_user_id`
- `group_id`
- `message`

## 3. API 端點

### POST /api/v1/dispatch

- 請求：`DispatchRequest`
- 回應：`DispatchResponse`
- 作用：根據可用志工、技能需求與距離進行指派。

### POST /api/v1/line/register

- 請求：`LineVolunteerRegistration`
- 回應：`LineRegisterResponse`
- 作用：登錄 LINE 志工資料。

### GET /health

- 作用：檢查 API 與 Ollama 連線狀態。

## 4. 指派演算法

1. 過濾 `availability=true` 的志工。
2. 依照任務 `urgency` 由高到低排序。
3. 針對每個任務，計算每位可用志工的：
   - 技能匹配分數
   - 路線距離分數
   - 緊急度分數
   - 最終合成分數
4. 選擇最高分志工，並從可用列表移除該志工。
5. 若沒有可用志工，回傳 `assigned_volunteers=[]` 並列入 `unassigned_tasks`。

### 4.1 路線距離估算

- 使用 Haversine 計算直線距離。
- 以緯度、經度差量估算道路網格距離。
- 套用複雜度修正係數以模擬實際行車路徑。

### 4.2 分數計算

- `skill_score`: 依據志工與任務類型所需技能交集比例。
- `distance_score`: 路線距離越短分數越高。
- `urgency_score`: `urgency / 5`。
- `final_score`: 根據 `priority_weighting` 使用以下權重：
  - `balanced`: skill 45%, distance 35%, urgency 20%
  - `speed`: skill 25%, distance 55%, urgency 20%
  - `expertise`: skill 60%, distance 25%, urgency 15%

## 5. AI 異常檢查

- 服務在本地演算法完成後，會嘗試使用 Ollama 進行一次異常檢查。
- 若 Ollama 不可用，系統仍然回傳分派結果，並將 `mode` 設為 `algorithm_only`。
- 若 Ollama 可用，`mode` 會回傳 `algorithm_with_ai_anomaly_check`。

## 6. 回傳欄位說明

- `mode`
  - `algorithm_only`: 系統只使用本地確定性演算法。
  - `algorithm_with_ai_anomaly_check`: 系統使用本地演算法並執行 AI 異常檢查。
- `unassigned_tasks`
  - 沒有可用志工時，該任務 ID 會列在此。
- `warnings`
  - 包含技能、距離或 AI 驗證相關異常提醒。

## 7. 範例

### 範例請求

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

### 範例回應

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
