import os
from typing import Optional
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from logging_config import logger, truncate_message
from schemas import DispatchRequest, Location
from services import DispatchService, LineService

load_dotenv()

LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET', '')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', '')
LINE_DEFAULT_GROUP_ID = os.getenv('LINE_GROUP_ID', '')
APP_BASE_URL = os.getenv('APP_BASE_URL', 'http://localhost:8000')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN) if LINE_CHANNEL_ACCESS_TOKEN else None
handler = WebhookHandler(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else None

last_group_id: Optional[str] = None


def _assert_line_configured() -> None:
    if not LINE_CHANNEL_SECRET or not LINE_CHANNEL_ACCESS_TOKEN:
        raise RuntimeError('LINE channel secret or access token is not configured.')


def _build_form_url(line_user_id: str) -> str:
    return f"{APP_BASE_URL.rstrip('/')}/volunteer/form/{line_user_id}"


def send_text_message(recipient_id: str, text: str) -> dict:
    _assert_line_configured()
    if not line_bot_api:
        raise RuntimeError('LINE bot client is not initialized.')

    message = TextSendMessage(text=text)
    try:
        line_bot_api.push_message(recipient_id, message)
        logger.info(f'LINE 訊息已發送到 {recipient_id}')
        return {'status': 'success', 'recipient_id': recipient_id, 'message': truncate_message(text)}
    except LineBotApiError as exc:
        logger.error(truncate_message(f'LINE 訊息發送失敗: {exc}'))
        raise


def send_volunteer_form_link(line_user_id: str) -> dict:
    url = _build_form_url(line_user_id)
    text = (
        '您好，感謝您加入志工團隊！請先完成以下報到表單，系統將依資料安排任務：\n'
        f'{url}'
    )
    return send_text_message(line_user_id, text)


def send_public_registration_link(group_id: str) -> dict:
    url = f"{APP_BASE_URL.rstrip('/')}/volunteer/form"
    text = (
        '救災報名已開放！請點擊以下連結進行報到：\n'
        f'{url}\n'
        '若您是從 LINE 群組進行報名，請在表單中填寫您的 LINE User ID。'
    )
    if group_id:
        return send_group_message(group_id, text)
    if last_group_id:
        return send_group_message(last_group_id, text)
    raise RuntimeError('無法取得 LINE 群組 ID，無法發送報名連結。')


def send_assignment_message(line_user_id: str, message: str) -> dict:
    return send_text_message(line_user_id, message)


def send_group_message(group_id: str, text: str) -> dict:
    _assert_line_configured()
    if not line_bot_api:
        raise RuntimeError('LINE bot client is not initialized.')

    message = TextSendMessage(text=text)
    try:
        line_bot_api.push_message(group_id, message)
        logger.info(f'LINE 群組訊息已發送到 {group_id}')
        return {'status': 'success', 'group_id': group_id, 'message': truncate_message(text)}
    except LineBotApiError as exc:
        logger.error(truncate_message(f'LINE 推播失敗: {exc}'))
        raise


def handle_webhook(body: str, signature: str):
    if not handler:
        raise RuntimeError('LINE webhook handler is not configured.')
    if not signature:
        raise RuntimeError('Missing x-line-signature header.')

    try:
        handler.handle(body, signature)
    except InvalidSignatureError as exc:
        logger.warning(truncate_message(f'LINE webhook 簽章驗證失敗: {exc}'))
        raise
    except Exception as exc:
        logger.error(truncate_message(f'LINE webhook 處理失敗: {exc}'))
        raise


def handle_message_event(event: MessageEvent):
    source_type = event.source.type
    user_id = getattr(event.source, 'user_id', None)
    group_id = getattr(event.source, 'group_id', LINE_DEFAULT_GROUP_ID)
    message_text = (event.message.text or '').strip().lower()

    global last_group_id
    if source_type == 'group' and group_id:
        last_group_id = group_id

    logger.info(f'LINE message event source={source_type} group_id={group_id} user_id={user_id} text={truncate_message(message_text, 200)}')

    try:
        if source_type == 'group':
            if message_text in ['開始建立救災行動', '開始報名', '開啟報名']:
                LineService.clear_registration_submissions()
                LineService.open_registration()
                send_group_message(
                    group_id,
                    '救災報名已開放！\n請有意願的志工私訊本 Bot 並輸入「報名」以取得個人報到表單。'
                )
                return

            if message_text in ['結束報名', '結束報名並派工', '關閉報名']:
                LineService.close_registration()
                payload = LineService.get_pending_dispatch_payload()
                if not payload:
                    send_group_message(group_id, '目前尚未設定派工資料，請先建立救災行動設定。')
                    return

                volunteers = LineService.get_registered_volunteer_models()
                if not volunteers:
                    send_group_message(group_id, '目前尚無有效報名志工，無法執行派工。')
                    return

                dispatch_request = DispatchRequest(
                    metadata=payload['metadata'],
                    work_types=payload['work_types'],
                    volunteers=volunteers,
                    tasks=payload['tasks'],
                )
                result = DispatchService.process_dispatch(dispatch_request)
                assignment_summary = []
                for assignment in result['assignments']:
                    if assignment.assigned_volunteers:
                        volunteers_str = ','.join(assignment.assigned_volunteers)
                        payload_obj = LineService.get_pending_dispatch_payload()
                        task_obj = next((t for t in payload_obj['tasks'] if t['id'] == assignment.task_id), None)
                        task_address = '未知位置'
                        if task_obj and task_obj.get('location'):
                            loc = task_obj['location']
                            location_obj = Location(lat=loc['lat'], lng=loc['lng']) if isinstance(loc, dict) else loc
                            task_address = LineService.reverse_geocode_location(location_obj)
                        assignment_summary.append(f"{assignment.task_id}: {volunteers_str} ({task_address})")
                    else:
                        payload_obj = LineService.get_pending_dispatch_payload()
                        task_obj = next((t for t in payload_obj['tasks'] if t['id'] == assignment.task_id), None)
                        task_address = '未知位置'
                        if task_obj and task_obj.get('location'):
                            loc = task_obj['location']
                            location_obj = Location(lat=loc['lat'], lng=loc['lng']) if isinstance(loc, dict) else loc
                            task_address = LineService.reverse_geocode_location(location_obj)
                        assignment_summary.append(f"{assignment.task_id}: 未指派 ({task_address})")
                
                summary_text = "派工完成！\n" + "\n".join(assignment_summary)
                send_group_message(group_id, summary_text)

                LineService.clear_pending_dispatch_payload()
                LineService.clear_registration_submissions()
                return

        if source_type == 'user':
            if message_text in ['報名', '我要報名']:
                if not LineService.is_registration_open():
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text='目前尚未開放報名，請稍後再試。'))
                    return
                if user_id:
                    send_volunteer_form_link(user_id)
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text='已傳送您的個人報到表單，請前往填寫。'))
                    return
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text='無法取得您的 LINE ID，請改用此 bot 的 Web 介面報名。'))
                return

        if line_bot_api:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='已收到訊息，感謝您的回覆。'))
            logger.info(f'LINE 回覆已送出。來源類型: {source_type}')
    except LineBotApiError as exc:
        logger.error(truncate_message(f'LINE 回覆失敗: {exc}'))


if handler is not None:
    handler.add(MessageEvent, message=TextMessage)(handle_message_event)
