# 操作模式文件

本系統目前有兩條主要操作路徑：

1. 整合表單團報。
2. 志工個人報名。

兩條路徑最後都會把志工資料轉成派工用的 `Volunteer`，再搭配同一份事件任務設定執行派工。

## 模式一：整合表單團報

### 適用情境

主辦單位已經建立災害事件與任務清單，希望把同一份公開報名表丟到 LINE 群組、社群或其他公告管道，讓多位志工集中填寫。

### 操作流程

1. 主辦端準備事件設定。

   使用 `DispatchSetupRequest`，內容包含 `metadata`、`work_types`、`tasks`，不需要包含志工。

2. 呼叫開放報名 API。

   ```bash
   curl -X POST http://127.0.0.1:8000/api/v1/dispatch/start \
     -H "Content-Type: application/json" \
     -d @test_cases/event_declaration_example.json
   ```

   系統會：

   - 清空上一輪表單投稿。
   - 儲存本次事件與任務。
   - 將報名狀態設為開放。
   - 嘗試推送公開報名表 `/volunteer/form` 到預設 LINE 群組。

3. 志工填寫公開表單。

   表單網址：

   ```text
   {APP_BASE_URL}/volunteer/form
   ```

   志工需填寫姓名、技能、位置與是否可出勤。位置可填地址，或直接填經緯度。

4. 主辦端結束報名並派工。

   ```bash
   curl -X POST http://127.0.0.1:8000/api/v1/dispatch/finish
   ```

   系統會：

   - 關閉報名。
   - 整合公開表單投稿與已登記 LINE 志工。
   - 執行派工。
   - 嘗試推送派工摘要到 LINE 群組。
   - 清除本輪待派工設定與表單投稿。

### 路徑特性

- 優點：最適合大量志工臨時報名，不要求每個志工都先完成 LINE user ID 綁定。
- 限制：若沒有 `line_user_id`，派工結果只能用填寫姓名識別志工，無法精準推送個人訊息。
- 注意：若表單使用地址欄位，必須設定 `GOOGLE_MAPS_API_KEY`。

### 建議使用時機

- 大型活動、災害現場臨時動員。
- 群組內快速收集人力。
- 志工來源分散，無法預先建立名冊。

## 模式二：志工個人報名

### 適用情境

志工已透過 LINE bot 或外部系統取得個人身分，主辦端希望保留個別 LINE user ID，方便後續追蹤、更新資料或推送個人表單。

### 操作流程 A：透過 API 登記個人資料

1. 先開放報名。

   可使用整合表單團報的 `/api/v1/dispatch/start`，或用 `/api/v1/dispatch/setup` 先放入事件設定，再由 LINE 互動流程開啟報名。

2. 登記單一志工。

   ```bash
   curl -X POST http://127.0.0.1:8000/api/v1/line/register \
     -H "Content-Type: application/json" \
     -d '{
       "line_user_id": "U1234567890abcdef",
       "display_name": "王小明",
       "skills": ["first_aid", "logistics"],
       "location": {"lat": 25.033964, "lng": 121.564468},
       "availability": true
     }'
   ```

   系統會登記或更新該志工，並嘗試推送個人表單連結：

   ```text
   {APP_BASE_URL}/volunteer/form/{line_user_id}
   ```

3. 如需批次匯入，使用 `/api/v1/line/register/bulk`。

4. 報名完成後，呼叫 `/api/v1/dispatch/finish` 產生派工。

### 操作流程 B：透過個人表單補資料

1. 系統或 LINE bot 產生個人表單連結。

   ```text
   {APP_BASE_URL}/volunteer/form/{line_user_id}
   ```

2. 志工打開表單並補齊姓名、技能與位置。

3. 表單送出至 `/volunteer/form/submit`，系統會把資料寫入本輪報名投稿。

4. 主辦端呼叫 `/api/v1/dispatch/finish` 執行派工。

### 路徑特性

- 優點：每筆志工資料可保留 LINE user ID，適合後續個人通知與資料更新。
- 限制：目前 `/api/v1/line/register` 需要在報名開放期間才能成功登記。
- 注意：若同一個 `line_user_id` 重複登記，系統會更新既有資料。

### 建議使用時機

- 已有固定志工隊或 LINE bot 好友名單。
- 需要追蹤個別志工狀態。
- 需要把個人表單連結推送給特定志工。

## 兩種模式的比較

| 項目 | 整合表單團報 | 志工個人報名 |
| --- | --- | --- |
| 主要入口 | `/api/v1/dispatch/start` + `/volunteer/form` | `/api/v1/line/register` 或 `/volunteer/form/{line_user_id}` |
| 是否需要 LINE user ID | 不一定 | 建議需要 |
| 適合人數 | 多人集中報名 | 單人或既有名冊 |
| 身分識別 | 姓名或 LINE user ID | LINE user ID |
| 後續個人通知 | 較弱 | 較完整 |
| 派工收斂點 | `/api/v1/dispatch/finish` | `/api/v1/dispatch/finish` |

## 完整建議流程

### 一般團報

1. 管理者準備 `event_declaration_example.json`。
2. 呼叫 `/api/v1/dispatch/start`。
3. 志工填 `/volunteer/form`。
4. 管理者確認報名截止。
5. 呼叫 `/api/v1/dispatch/finish`。
6. 於 LINE 群組檢查派工摘要。

### 個人報名

1. 管理者建立事件設定。
2. 開放報名。
3. 透過 `/api/v1/line/register`、`/api/v1/line/register/bulk` 或個人表單收志工資料。
4. 呼叫 `/api/v1/dispatch/finish`。
5. 依派工結果進行群組或個別通知。

## 操作注意事項

- 本服務目前使用記憶體保存待派工設定與報名資料，服務重啟後資料會消失。
- 表單送出前必須先開放報名，否則 `/volunteer/form/submit` 會拒絕。
- 地址轉座標依賴 Google Maps API；未設定 key 時，請讓志工直接填經緯度。
- LINE 推播依賴 LINE channel 設定；未設定時，派工 API 仍可運作，但不會成功推播 LINE 訊息。
- Ollama 只負責異常檢查，不參與核心派工決策；Ollama 不可用時會自動改用 `algorithm_only`。
