from typing import List, Optional

from fastapi import FastAPI, Form, HTTPException, status, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, HTMLResponse
from linebot.exceptions import InvalidSignatureError
from line_integration import (
    APP_BASE_URL,
    LINE_DEFAULT_GROUP_ID,
    send_assignment_message,
    send_group_message,
    send_public_registration_link,
    send_volunteer_form_link,
    handle_webhook,
)
from logging_config import ERROR_CODES, logger, truncate_message
from schemas import DispatchRequest, DispatchResponse, DispatchSetupRequest, LineVolunteerRegistration, LineRegisterResponse, Location
from services import DispatchService, LineService

app = FastAPI(
    title="救災志工智慧分配 API Component",
    description="數位發展部 - 防災積木元件創新賽參賽作品",
    version="1.0.0"
)

# ---------------------------------------------------------------------------
# 1. 核心 API 運作端點 (派發任務)
# ---------------------------------------------------------------------------
@app.post("/api/v1/dispatch", response_model=DispatchResponse, status_code=status.HTTP_200_OK)
async def create_dispatch_plan(payload: DispatchRequest):
    try:
        result = DispatchService.process_dispatch(payload)
        assignment_summary = []
        for assignment in result['assignments']:
            if assignment.assigned_volunteers:
                volunteers_str = ','.join(assignment.assigned_volunteers)
                task_location = payload.tasks[[t.id for t in payload.tasks].index(assignment.task_id)].location
                task_address = LineService.reverse_geocode_location(task_location)
                assignment_summary.append(f"{assignment.task_id}: {volunteers_str} ({task_address})")
            else:
                task_location = payload.tasks[[t.id for t in payload.tasks].index(assignment.task_id)].location
                task_address = LineService.reverse_geocode_location(task_location)
                assignment_summary.append(f"{assignment.task_id}: 未指派 ({task_address})")
        
        summary_text = "派工完成！\n" + "\n".join(assignment_summary)
        try:
            send_group_message(LINE_DEFAULT_GROUP_ID, summary_text)
        except Exception as exc:
            logger.warning(truncate_message(f'無法發送派工摘要到群組: {exc}'))
        
        return JSONResponse(content=jsonable_encoder(result))
    except ValueError as val_err:
        logger.warning(truncate_message(str(val_err)))
        raise HTTPException(
            status_code=422,
            detail={
                'code': ERROR_CODES['VALIDATION_ERROR'],
                'message': '資料格式或運算參數異常，請確認輸入內容。'
            }
        )
    except Exception as e:
        logger.error(truncate_message(str(e)))
        raise HTTPException(
            status_code=500,
            detail={
                'code': ERROR_CODES['DISPATCH_SERVICE_FAILURE'],
                'message': '分派服務暫時無法使用，請稍後再試。'
            }
        )


# ---------------------------------------------------------------------------
# 2. LINE 志工註冊端點
# ---------------------------------------------------------------------------
@app.post("/api/v1/line/register", response_model=LineRegisterResponse, status_code=status.HTTP_200_OK)
async def register_line_volunteer(payload: LineVolunteerRegistration):
    try:
        record = LineService.register_volunteer(payload)
        try:
            send_volunteer_form_link(record['line_user_id'])
            logger.info(f'已發送報到表單連結給 LINE user {record["line_user_id"]}')
        except Exception as exc:
            logger.warning(truncate_message(f'無法發送報到表單: {exc}'))

        return JSONResponse(content=jsonable_encoder({
            'status': 'success',
            'line_user_id': record['line_user_id'],
            'group_id': record['group_id'],
            'message': 'LINE 志工已成功加入群組並登錄資料。'
        }))
    except Exception as e:
        logger.error(truncate_message(str(e)))
        raise HTTPException(
            status_code=500,
            detail={
                'code': ERROR_CODES['LINE_REGISTER_FAILURE'],
                'message': 'LINE 註冊失敗，請稍後重試。'
            }
        )


@app.post('/api/v1/dispatch/start', status_code=status.HTTP_200_OK)
async def start_dispatch_registration(payload: DispatchSetupRequest):
    try:
        LineService.clear_registration_submissions()
        LineService.set_pending_dispatch_payload(payload.dict())
        LineService.open_registration()
        send_public_registration_link(LINE_DEFAULT_GROUP_ID)
        return JSONResponse(content={
            'status': 'success',
            'message': '已啟動報名流程。請在 LINE 群組內發送「結束報名」進行派工。'
        })
    except Exception as exc:
        logger.error(truncate_message(str(exc)))
        raise HTTPException(status_code=500, detail={'code': ERROR_CODES['DISPATCH_SERVICE_FAILURE'], 'message': '啟動報名流程失敗。'})


@app.post('/api/v1/dispatch/setup', status_code=status.HTTP_200_OK)
async def setup_dispatch(payload: DispatchSetupRequest):
    try:
        LineService.set_pending_dispatch_payload(payload.dict())
        return JSONResponse(content={
            'status': 'success',
            'message': '已儲存派工設定。請在 LINE 群組內發送「結束報名」進行派工。'
        })
    except Exception as exc:
        logger.error(truncate_message(str(exc)))
        raise HTTPException(status_code=500, detail={'code': ERROR_CODES['DISPATCH_SERVICE_FAILURE'], 'message': '派工設定儲存失敗。'})


# ---------------------------------------------------------------------------
# 3. 健康檢查端點 (含 Ollama 連線狀態)
# ---------------------------------------------------------------------------
@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """
    系統健康檢查端點，同時確認本機 API 與後端 Ollama 服務的運作狀態。
    """
    # 呼叫 Service 內寫好的 Ollama 連線檢查方法
    ollama_healthy = DispatchService._verify_ollama_connection()
    
    status_msg = "healthy" if ollama_healthy else "degraded"
    
    # 即使 Ollama 斷線，因為系統有「本地演算法」作為降級備援(Fallback)，
    # 這裡可以選擇不噴 500 錯誤，而是回傳狀態讓監控系統知道。
    return {
        "status": status_msg,
        "components": {
            "api_server": "up",
            "ollama_service": "up" if ollama_healthy else "down"
        }
    }


@app.post('/webhook')
async def line_webhook(request: Request, x_line_signature: str = Header(None)):
    body_bytes = await request.body()
    body_text = body_bytes.decode('utf-8', errors='ignore')
    logger.info(f'LINE webhook received signature={x_line_signature} body={truncate_message(body_text, 1000)}')
    try:
        handle_webhook(body_text, x_line_signature)
        return JSONResponse(status_code=200, content={'status': 'success', 'message': 'Webhook received.'})
    except InvalidSignatureError as exc:
        logger.warning(truncate_message(f'LINE webhook 非法簽章: {exc}'))
        raise HTTPException(status_code=401, detail={'code': 'LINE_WEBHOOK_INVALID_SIGNATURE', 'message': 'LINE Webhook 簽章驗證失敗。'})
    except RuntimeError as exc:
        logger.warning(truncate_message(str(exc)))
        raise HTTPException(status_code=400, detail={'code': 'LINE_WEBHOOK_INVALID_REQUEST', 'message': str(exc)})
    except Exception as exc:
        logger.warning(truncate_message(str(exc)))
        raise HTTPException(status_code=400, detail={'code': 'LINE_WEBHOOK_FAILURE', 'message': truncate_message(str(exc))})


SKILL_OPTIONS = [
    ('first_aid', '急救'),
    ('rope_rescue', '繩索救援'),
    ('nursing', '護理'),
    ('logistics', '後勤/搬運'),
    ('communications', '通訊協調'),
    ('evacuation', '撤離協助'),
    ('search', '搜救'),
]


def _render_skill_options(selected_skills: Optional[List[str]] = None) -> str:
    selected = set(selected_skills or [])
    return ''.join(
        f'<label class="chip"><input type="checkbox" name="skills" value="{value}" {"checked" if value in selected else ""}> {label}</label>'
        for value, label in SKILL_OPTIONS
    )


def _render_volunteer_form_html(line_user_id: Optional[str] = None, selected_skills: Optional[List[str]] = None) -> str:
    hidden_input = f'<input type="hidden" name="line_user_id" value="{line_user_id}" />' if line_user_id else ''
    id_note = '' if line_user_id else '<p class="helper">若您是在 LINE 群組中報名，建議於表單中填寫您的 LINE User ID 以利後續通知。</p>'
    skill_options = _render_skill_options(selected_skills)
    return f'''
    <!DOCTYPE html>
    <html lang="zh-Hant">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>志工報到表單</title>
        <style>
          body {{ font-family: "Microsoft JhengHei", Arial, sans-serif; background: #f5f7fb; margin: 0; padding: 24px; color: #1f2937; }}
          .card {{ max-width: 760px; margin: 0 auto; background: white; border-radius: 16px; box-shadow: 0 8px 30px rgba(0,0,0,0.08); padding: 28px; }}
          h1 {{ margin-top: 0; color: #0f766e; }}
          .helper {{ color: #64748b; font-size: 0.95rem; }}
          label {{ display: block; margin-bottom: 12px; font-weight: 600; }}
          input[type="text"], input[type="number"], select {{ width: 100%; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 10px; box-sizing: border-box; margin-top: 6px; }}
          .chip {{ display: inline-block; padding: 8px 12px; margin: 6px 8px 6px 0; border: 1px solid #bae6fd; border-radius: 999px; background: #f0f9ff; font-weight: 500; }}
          .chip input {{ margin-right: 6px; }}
          .note {{ background: #f8fafc; border-left: 4px solid #14b8a6; padding: 12px; border-radius: 8px; margin: 12px 0; }}
          button {{ background: #0f766e; color: white; border: none; padding: 12px 18px; border-radius: 999px; cursor: pointer; font-size: 1rem; }}
          button:hover {{ background: #115e59; }}
        </style>
      </head>
      <body>
        <div class="card">
          <h1>志工報到表單</h1>
          {id_note}
          <form method="post" action="/volunteer/form/submit">
            {hidden_input}
            <label>姓名<br><input type="text" name="display_name" required></label>
            <label>LINE User ID (若有)<br><input type="text" name="line_user_id" placeholder="選填"></label>
            <label>地址 (可輸入中文或英文地址)<br><input type="text" name="address" placeholder="例如：台北市信義區松仁路1號"></label>
            <label>專長（可複選）<br><div class="skill-grid">{skill_options}</div></label>
            <div class="note">若無法填寫地址，可改為手動輸入經緯度。</div>
            <label>可服務緯度<br><input type="number" step="0.000001" name="lat"></label>
            <label>可服務經度<br><input type="number" step="0.000001" name="lng"></label>
            <label>是否可立即出勤<br>
              <select name="availability">
                <option value="true">是</option>
                <option value="false">否</option>
              </select>
            </label>
            <br><br>
            <button type="submit">送出報到資料</button>
          </form>
        </div>
      </body>
    </html>
    '''


@app.get('/volunteer/form/{line_user_id}', response_class=HTMLResponse)
def volunteer_form_with_user_id(line_user_id: str):
    return HTMLResponse(content=_render_volunteer_form_html(line_user_id=line_user_id))


@app.get('/webhook/volunteer/form/{line_user_id}', response_class=HTMLResponse)
def webhook_volunteer_form_with_user_id(line_user_id: str):
    return volunteer_form_with_user_id(line_user_id)


@app.get('/webhook/volunteer/form', response_class=HTMLResponse)
def webhook_volunteer_form():
    return volunteer_form()


@app.get('/volunteer/form', response_class=HTMLResponse)
def volunteer_form(line_user_id: Optional[str] = None):
    return HTMLResponse(content=_render_volunteer_form_html(line_user_id=line_user_id))


@app.post('/volunteer/form/submit', response_class=HTMLResponse)
async def volunteer_form_submit(
    display_name: str = Form(...),
    line_user_id: Optional[str] = Form(None),
    skills: Optional[List[str]] = Form(default=None),
    address: Optional[str] = Form(None),
    lat: Optional[float] = Form(None),
    lng: Optional[float] = Form(None),
    availability: str = Form('true'),
):
    if not LineService.is_registration_open():
        return HTMLResponse(content='<html><body><h1>目前尚未開放報名</h1><p>請等待管理員啟動報名流程。</p></body></html>', status_code=400)

    location = None
    if address:
        try:
            location = LineService.geocode_address(address.strip())
        except Exception as exc:
            return HTMLResponse(
                content=f'<html><body><h1>地址轉換失敗</h1><p>{truncate_message(str(exc))}</p></body></html>',
                status_code=400,
            )
    elif lat is not None and lng is not None:
        location = Location(lat=lat, lng=lng)
    else:
        return HTMLResponse(
            content='<html><body><h1>缺少位置資訊</h1><p>請輸入地址或手動填寫經緯度。</p></body></html>',
            status_code=400,
        )

    normalized_skills = [s.strip() for s in (skills or []) if s and s.strip()]
    submission = {
        'line_user_id': line_user_id,
        'display_name': display_name.strip(),
        'skills': normalized_skills,
        'address': address.strip() if address else None,
        'location': location,
        'availability': availability.lower() in ('true', 'yes', '1', 'on'),
    }
    LineService.add_registration_submission(submission)

    skills_text = ', '.join(submission['skills']) if submission['skills'] else '尚未選擇專長'
    html = f'''
    <!DOCTYPE html>
    <html lang="zh-Hant">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>報到完成</title>
        <style>
          body {{ font-family: "Microsoft JhengHei", Arial, sans-serif; background: #f5f7fb; margin: 0; padding: 24px; color: #1f2937; }}
          .card {{ max-width: 720px; margin: 0 auto; background: white; border-radius: 16px; box-shadow: 0 8px 30px rgba(0,0,0,0.08); padding: 28px; }}
          h1 {{ color: #0f766e; }}
          .pill {{ display: inline-block; background: #ecfeff; color: #0f766e; padding: 6px 10px; border-radius: 999px; margin-top: 8px; }}
        </style>
      </head>
      <body>
        <div class="card">
          <h1>報到完成</h1>
          <p>感謝 <strong>{submission['display_name']}</strong> 完成報到。</p>
          <p>系統已紀錄您的資訊，請等待派工通知。</p>
          <div class="pill">專長：{skills_text}</div>
        </div>
      </body>
    </html>
    '''
    return HTMLResponse(content=html)


@app.post('/api/v1/line/send-group-message', status_code=status.HTTP_200_OK)
async def api_send_group_message(payload: dict):
    try:
        group_id = payload.get('group_id') or LINE_DEFAULT_GROUP_ID
        text = payload.get('text', '')
        if not group_id or not text:
            raise ValueError('group_id 或 text 欄位缺失。')

        result = send_group_message(group_id, text)
        return JSONResponse(content=result)
    except ValueError as val_err:
        logger.warning(truncate_message(str(val_err)))
        raise HTTPException(status_code=422, detail={'code': 'LINE_MESSAGE_VALIDATION_ERROR', 'message': '群組訊息格式錯誤。'})
    except Exception as exc:
        logger.error(truncate_message(str(exc)))
        raise HTTPException(status_code=500, detail={'code': 'LINE_MESSAGE_SEND_FAILURE', 'message': 'LINE 群組訊息發送失敗。'})


# 測試用預留根路由
@app.get("/")
def read_root():
    return {"message": "Disaster Volunteer Dispatcher API is running."}