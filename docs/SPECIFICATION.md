# 技術規格文件

## 1. 系統概覽

本服務提供災害事件志工派工 API。核心流程是接收事件任務、工作類型與志工資料，篩選可出勤志工後，依技能符合度、路徑距離與任務急迫度計算分數並產生派工結果。

派工結果會包含：

- 每個任務的指派志工。
- 預估抵達時間 `eta_minutes`。
- 信心分數與分數拆解。
- 未成功指派的任務。
- 本地與 AI 異常檢查警示。

## 2. Endpoint 總覽

| Method | Endpoint | 功能 |
| --- | --- | --- |
| `GET` | `/` | API 根路徑狀態確認。 |
| `GET` | `/health` | 檢查 API 與 Ollama 狀態。 |
| `POST` | `/api/v1/dispatch` | 直接送入完整事件、志工與任務資料並立即派工。 |
| `POST` | `/api/v1/dispatch/setup` | 儲存待派工事件設定，但不開放報名。 |
| `POST` | `/api/v1/dispatch/start` | 儲存事件設定、清空舊報名、開放公開表單團報並推送報名連結。 |
| `POST` | `/api/v1/dispatch/finish` | 關閉報名，整合已登記志工並執行派工。 |
| `POST` | `/api/v1/line/register` | 登記或更新單一 LINE 志工資料。 |
| `POST` | `/api/v1/line/register/bulk` | 批次登記或更新多位 LINE 志工資料。 |
| `POST` | `/api/v1/line/send-group-message` | 向 LINE 群組推送測試或公告訊息。 |
| `POST` | `/webhook` | LINE Messaging API webhook 入口。 |
| `GET` | `/volunteer/form` | 公開志工報名表。 |
| `GET` | `/volunteer/form/{line_user_id}` | 帶 LINE User ID 的個人志工報名表。 |
| `GET` | `/webhook/volunteer/form` | 公開表單別名，供 webhook 相關路徑使用。 |
| `GET` | `/webhook/volunteer/form/{line_user_id}` | 個人表單別名，供 webhook 相關路徑使用。 |
| `POST` | `/volunteer/form/submit` | 接收 HTML 報名表送出的志工資料。 |

## 3. Endpoint 詳細說明

### GET `/`

功能：確認 API server 已啟動。

Response：

```json
{
  "message": "Disaster Volunteer Dispatcher API is running."
}
```

### GET `/health`

功能：檢查 API server 與 Ollama 服務狀態。Ollama 不可用時不會讓 API 失效，派工會退回 `algorithm_only`。

Response：

```json
{
  "status": "healthy",
  "components": {
    "api_server": "up",
    "ollama_service": "up"
  }
}
```

### POST `/api/v1/dispatch`

功能：直接派工。呼叫端需一次提供事件 metadata、工作類型、志工清單與任務清單。系統會立即計算派工結果，並嘗試將派工摘要送到預設 LINE 群組。

適用情境：呼叫端已經有完整志工資料，例如外部系統整合、後台匯入或測試。

Request body：`DispatchRequest`

Response body：`DispatchResponse`

主要錯誤：

- `422 VALIDATION_ERROR`：資料格式或派工資料不合法。
- `500 DISPATCH_SERVICE_FAILURE`：派工流程發生未預期錯誤。

### POST `/api/v1/dispatch/setup`

功能：只儲存事件設定，不開放報名、不清空既有表單投稿、不立即派工。

適用情境：先由管理端建立事件任務，稍後再透過 LINE 指令或其他流程開放/結束報名。

Request body：`DispatchSetupRequest`

Response：

```json
{
  "status": "success",
  "message": "已儲存派工設定。"
}
```

### POST `/api/v1/dispatch/start`

功能：啟動整合表單團報流程。系統會清空前一輪表單投稿、儲存事件設定、開放報名，並嘗試向預設 LINE 群組發送公開報名表連結。

適用情境：主辦端要讓同一事件的志工透過公開表單集中報名。

Request body：`DispatchSetupRequest`

Response：

```json
{
  "status": "success",
  "message": "已開放報名並儲存派工設定。",
  "warnings": []
}
```

注意事項：

- 需要 `APP_BASE_URL` 才能產生正確表單網址。
- 若要自動推播 LINE 群組，需設定 `LINE_CHANNEL_ACCESS_TOKEN`、`LINE_CHANNEL_SECRET` 與 `LINE_GROUP_ID`。

### POST `/api/v1/dispatch/finish`

功能：結束報名，將已透過 LINE API 登記與 HTML 表單送出的志工資料合併，建立 `DispatchRequest` 後執行派工。完成後會清除待派工設定與本輪表單投稿。

Request body：無。

Response body：`DispatchResponse`

主要錯誤：

- `400 VALIDATION_ERROR`：尚未設定事件任務，或沒有可用志工資料。
- `500 DISPATCH_SERVICE_FAILURE`：派工流程發生未預期錯誤。

### POST `/api/v1/line/register`

功能：登記或更新單一 LINE 志工資料。若提供 `address` 且未提供 `location`，系統會使用 Google Maps geocoding 轉成座標。登記成功後，系統會嘗試推送個人報名表連結給該 LINE user。

適用情境：志工個人報名、LINE bot 已取得 user ID、或由外部系統替單一志工補登資料。

Request body：`LineVolunteerRegistration`

Response body：`LineRegisterResponse`

限制：

- 目前必須在報名開放期間才能登記，否則會回傳錯誤。
- 使用地址轉座標時需設定 `GOOGLE_MAPS_API_KEY`。

### POST `/api/v1/line/register/bulk`

功能：批次登記或更新多位 LINE 志工資料。

適用情境：已有志工名冊或外部表單資料，要批次匯入本服務。

Request body：`LineVolunteerRegistration[]`

Response body：`LineRegisterResponse[]`

注意事項：

- 與單筆登記相同，目前需在報名開放期間才能登記。
- 批次流程不會逐一推送個人表單連結。

### POST `/api/v1/line/send-group-message`

功能：向指定 LINE 群組或預設 LINE 群組推送文字訊息。主要用於測試 LINE 設定或人工公告。

Request body：

```json
{
  "group_id": "Cxxxxxxxx",
  "text": "測試訊息"
}
```

欄位說明：

- `group_id`：選填。未提供時使用 `LINE_GROUP_ID`。
- `text`：必填，訊息文字。

### POST `/webhook`

功能：LINE Messaging API webhook 入口。系統會驗證 `x-line-signature`，並處理群組或個人文字訊息。

Header：

- `x-line-signature`：LINE 簽章，必填。

目前支援的互動方向：

- 群組訊息：可觸發開放報名、結束報名並派工等流程。
- 個人訊息：可在報名開放期間取得個人報名表連結。

### GET `/volunteer/form`

功能：公開志工報名表。表單會要求填寫姓名、地址或經緯度、技能與可出勤狀態。

適用情境：整合表單團報，志工不一定有 LINE user ID。

### GET `/volunteer/form/{line_user_id}`

功能：個人志工報名表。系統會將 `line_user_id` 寫入隱藏欄位，志工送出後可保留 LINE 身分對應。

適用情境：LINE bot 推送給個別志工的報名連結。

### GET `/webhook/volunteer/form`

功能：公開報名表的別名路徑，行為等同 `/volunteer/form`。

### GET `/webhook/volunteer/form/{line_user_id}`

功能：個人報名表的別名路徑，行為等同 `/volunteer/form/{line_user_id}`。

### POST `/volunteer/form/submit`

功能：接收 HTML 表單送出的志工報名資料，寫入本輪 `registration_submissions`。若表單填地址，系統會用 Google Maps geocoding 轉座標；若未填地址則需提供 `lat` 與 `lng`。

Content-Type：`application/x-www-form-urlencoded`

表單欄位：

| 欄位 | 必填 | 說明 |
| --- | --- | --- |
| `display_name` | 是 | 志工顯示名稱。 |
| `line_user_id` | 否 | LINE User ID。個人連結會自動帶入。 |
| `skills` | 否 | 可複選技能。 |
| `address` | 否 | 地址；若填寫會優先用來轉座標。 |
| `lat` | 條件式 | 未提供地址時需提供。 |
| `lng` | 條件式 | 未提供地址時需提供。 |
| `availability` | 否 | 是否可出勤，預設 `true`。 |

主要錯誤：

- 報名尚未開放。
- 未提供地址或完整經緯度。
- 地址轉座標失敗。

## 4. 資料模型

### Location

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `lat` | float | 緯度。 |
| `lng` | float | 經度。 |

### Metadata

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `incident_id` | string | 事件 ID。 |
| `priority_weighting` | enum | 派工權重：`balanced`、`speed`、`expertise`。 |

### WorkType

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `type_id` | string | 工作類型 ID，需與 task 的 `type_id` 對應。 |
| `required_skills` | string[] | 此工作類型需要的技能。 |

### Volunteer

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | string | 志工 ID。 |
| `skills` | string[] | 技能清單。 |
| `location` | Location | 志工位置。 |
| `availability` | boolean | 是否可出勤。 |
| `age` | int | 選填，年齡。 |
| `line_user_id` | string | 選填，LINE user ID。 |
| `special_skills` | string[] | 選填，特殊技能。 |

### Task

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | string | 任務 ID。 |
| `type_id` | string | 工作類型 ID。 |
| `location` | Location | 任務位置。 |
| `urgency` | int | 急迫度，範圍 1-5。 |
| `destination` | string | 選填，目的地文字。 |
| `job_description` | string | 選填，工作描述。 |

### DispatchRequest

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `metadata` | Metadata | 事件資訊。 |
| `work_types` | WorkType[] | 工作類型定義。 |
| `volunteers` | Volunteer[] | 志工清單。 |
| `tasks` | Task[] | 任務清單。 |

### DispatchSetupRequest

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `metadata` | Metadata | 事件資訊。 |
| `work_types` | WorkType[] | 工作類型定義。 |
| `tasks` | Task[] | 任務清單。 |

### LineVolunteerRegistration

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `line_user_id` | string | LINE user ID。 |
| `display_name` | string | 志工顯示名稱。 |
| `group_id` | string | 選填，LINE 群組 ID。 |
| `skills` | string[] | 選填，技能清單。 |
| `address` | string | 選填，地址。 |
| `location` | Location | 選填，位置。 |
| `availability` | boolean | 是否可出勤，預設 `true`。 |

### DispatchResponse

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `status` | string | 執行狀態。 |
| `dispatch_id` | string | 本次派工 ID。 |
| `incident_id` | string | 事件 ID。 |
| `mode` | enum | `algorithm_only` 或 `algorithm_with_ai_anomaly_check`。 |
| `assignments` | Assignment[] | 任務指派結果。 |
| `unassigned_tasks` | string[] | 未成功指派的任務 ID。 |
| `warnings` | string[] | 警示訊息。 |

### Assignment

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `task_id` | string | 任務 ID。 |
| `assigned_volunteers` | string[] | 被指派的志工 ID。 |
| `eta_minutes` | int | 預估抵達分鐘數。 |
| `confidence` | float | 信心分數。 |
| `score_breakdown` | ScoreBreakdown | 分數拆解。 |
| `reasoning_summary` | string | 指派原因摘要。 |

### ScoreBreakdown

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `skill_score` | float | 技能符合度。 |
| `distance_score` | float | 距離分數。 |
| `urgency_score` | float | 急迫度分數。 |
| `final_score` | float | 加權後總分。 |

## 5. 派工規則

1. 只納入 `availability=true` 的志工。
2. 任務依 `urgency` 由高到低處理。
3. 每個任務先嘗試指派一名最高分志工。
4. 剩餘志工再依最佳匹配補入任務。
5. 沒有志工可用的任務會出現在 `unassigned_tasks`。

加權公式：

| 模式 | 技能 | 距離 | 急迫度 |
| --- | ---: | ---: | ---: |
| `balanced` | 45% | 35% | 20% |
| `speed` | 25% | 55% | 20% |
| `expertise` | 60% | 25% | 15% |

## 6. 範例

### 直接派工 Request

```json
{
  "metadata": {
    "incident_id": "incident-2026-001",
    "priority_weighting": "balanced"
  },
  "work_types": [
    {
      "type_id": "medical",
      "required_skills": ["medical", "firstaid"]
    }
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

### 派工 Response

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
      "reasoning_summary": "任務 task_101 已指派 1 名志工：vol_01。"
    }
  ],
  "unassigned_tasks": [],
  "warnings": ["系統已完成演算法分配與本地異常檢查，未發現顯著異常。"]
}
```
