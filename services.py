import os
import math
import uuid
import requests
from typing import List, Dict, Optional
from dotenv import load_dotenv
from logging_config import logger, truncate_message, ERROR_CODES
from schemas import (
    DispatchRequest,
    Assignment,
    Volunteer,
    Task,
    WorkType,
    LineVolunteerRegistration,
    Location,
    ScoreBreakdown,
)

load_dotenv()
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY', '')


class LineService:
    registered_volunteers: List[Dict] = []
    registration_open: bool = False
    pending_dispatch_payload: Optional[Dict] = None
    registration_submissions: List[Dict] = []

    @classmethod
    def open_registration(cls) -> None:
        cls.registration_open = True
        logger.info('📣 開始志工報名流程。')

    @classmethod
    def close_registration(cls) -> None:
        cls.registration_open = False
        logger.info('🔒 結束志工報名流程。')

    @classmethod
    def is_registration_open(cls) -> bool:
        return cls.registration_open

    @classmethod
    def set_pending_dispatch_payload(cls, payload: Dict) -> None:
        cls.pending_dispatch_payload = payload
        logger.info('📌 已儲存派工設定。')

    @classmethod
    def get_pending_dispatch_payload(cls) -> Optional[Dict]:
        return cls.pending_dispatch_payload

    @classmethod
    def clear_pending_dispatch_payload(cls) -> None:
        cls.pending_dispatch_payload = None
        logger.info('🗑️ 已清除派工設定。')

    @classmethod
    def clear_registration_submissions(cls) -> None:
        cls.registration_submissions = []
        logger.info('🗑️ 已清空報名資料。')

    @classmethod
    def add_registration_submission(cls, submission: Dict) -> Dict:
        cls.registration_submissions.append(submission)
        logger.info(f'📥 收到志工報名資料: {submission.get("display_name") or submission.get("line_user_id") or "匿名"}')
        return submission

    @classmethod
    def get_registration_submissions(cls) -> List[Dict]:
        return cls.registration_submissions

    @classmethod
    def geocode_address(cls, address: str) -> Location:
        if not GOOGLE_MAPS_API_KEY:
            raise RuntimeError('未設定 GOOGLE_MAPS_API_KEY，無法進行地址轉換。')

        params = {
            'address': address,
            'key': GOOGLE_MAPS_API_KEY,
        }
        response = requests.get('https://maps.googleapis.com/maps/api/geocode/json', params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('status') != 'OK' or not data.get('results'):
            raise ValueError(f"Google 地理編碼失敗: {data.get('status')} {data.get('error_message','')}")

        location_data = data['results'][0]['geometry']['location']
        return Location(lat=location_data['lat'], lng=location_data['lng'])

    @classmethod
    def reverse_geocode_location(cls, location: Location) -> str:
        if not GOOGLE_MAPS_API_KEY:
            return f"{location.lat}, {location.lng}"

        params = {
            'latlng': f"{location.lat},{location.lng}",
            'key': GOOGLE_MAPS_API_KEY,
        }
        try:
            response = requests.get('https://maps.googleapis.com/maps/api/geocode/json', params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('status') == 'OK' and data.get('results'):
                return data['results'][0]['formatted_address']
            return f"{location.lat}, {location.lng}"
        except Exception as exc:
            logger.warning(truncate_message(f"反向地理編碼失敗: {exc}"))
            return f"{location.lat}, {location.lng}"

    @classmethod
    def get_volunteer_by_line_user_id(cls, line_user_id: str) -> Optional[Dict]:
        return next((v for v in cls.registered_volunteers if v.get('line_user_id') == line_user_id), None)

    @classmethod
    def get_line_user_id_by_name(cls, name: str) -> Optional[str]:
        volunteer = next(
            (
                v
                for v in cls.registered_volunteers
                if v.get('display_name') == name or v.get('line_user_id') == name
            ),
            None,
        )
        return volunteer.get('line_user_id') if volunteer else None

    @classmethod
    def get_registered_volunteer_models(cls) -> List[Volunteer]:
        volunteers: List[Volunteer] = []
        seen_ids = set()
        for v in cls.registered_volunteers + cls.registration_submissions:
            if not v.get('location'):
                continue
            id_value = v.get('line_user_id') or v.get('display_name') or str(uuid.uuid4())
            if id_value in seen_ids:
                continue
            seen_ids.add(id_value)
            volunteers.append(
                Volunteer(
                    id=id_value,
                    skills=v.get('skills') or [],
                    location=v['location'],
                    availability=v.get('availability', True),
                    age=v.get('age'),
                    line_user_id=v.get('line_user_id'),
                    special_skills=v.get('special_skills'),
                )
            )
        return volunteers

    @classmethod
    def register_volunteer(cls, registration: LineVolunteerRegistration) -> Dict:
        if not cls.registration_open:
            raise RuntimeError('目前不在報名期間，無法登記。')

        record = registration.dict()
        if not record.get('location') and record.get('address'):
            record['location'] = cls.geocode_address(record['address'])

        record['group_id'] = record.get('group_id') or str(uuid.uuid4())
        existing = cls.get_volunteer_by_line_user_id(record['line_user_id'])
        if existing:
            existing.update(record)
            logger.info(f"📥 更新 LINE 志工資料: {record['line_user_id']} ({record['display_name']})")
            return existing

        cls.registered_volunteers.append(record)
        logger.info(f"📥 LINE 註冊志工: {record['line_user_id']} ({record['display_name']})")
        return record


class DispatchService:
    BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    DEBUG_MODEL = os.getenv('OLLAMA_MODEL_DEBUG', 'neural-chat')
    GENERATE_ENDPOINT = f"{BASE_URL}/api/generate"
    AVERAGE_SPEED_KMH = 20.0

    @staticmethod
    def _verify_ollama_connection() -> bool:
        try:
            response = requests.get(f"{DispatchService.BASE_URL}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            logger.warning(truncate_message(f"⚠️ Ollama 連線檢查失敗: {e}"))
            return False

    @classmethod
    def _call_ollama(cls, model: str, prompt: str) -> str:
        payload = {"model": model, "prompt": prompt, "stream": False}
        response = requests.post(cls.GENERATE_ENDPOINT, json=payload, timeout=30)
        response.raise_for_status()
        return response.json().get('response', '')

    @staticmethod
    def calculate_haversine_distance(loc1, loc2) -> float:
        R = 6371.0
        lat1, lng1 = math.radians(loc1.lat), math.radians(loc1.lng)
        lat2, lng2 = math.radians(loc2.lat), math.radians(loc2.lng)
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    @staticmethod
    def calculate_route_distance(loc1, loc2) -> float:
        straight_km = DispatchService.calculate_haversine_distance(loc1, loc2)
        if straight_km <= 0:
            return 0.0

        avg_lat = math.radians((loc1.lat + loc2.lat) / 2)
        delta_lat_km = abs(loc2.lat - loc1.lat) * 110.574
        delta_lng_km = abs(loc2.lng - loc1.lng) * 111.320 * math.cos(avg_lat)
        grid_distance = delta_lat_km + delta_lng_km
        complexity_factor = 1.0 + min(0.6, abs(delta_lat_km - delta_lng_km) / max(0.1, straight_km))
        route_estimate = max(grid_distance, straight_km) * (1.1 + 0.2 * (complexity_factor - 1.0))
        return round(route_estimate, 3)

    @staticmethod
    def filter_available_volunteers(volunteers: List[Volunteer]) -> List[Volunteer]:
        return [v for v in volunteers if v.availability]

    @staticmethod
    def get_work_type(tasks_type_id: str, work_types: List[WorkType]) -> Optional[WorkType]:
        normalized = tasks_type_id.strip().lower()
        for item in work_types:
            if item.type_id.strip().lower() == normalized:
                return item
        return None

    @staticmethod
    def calculate_skill_score(vol: Volunteer, work_type: Optional[WorkType]) -> float:
        if not work_type:
            return 0.0
        required = {skill.strip().lower() for skill in work_type.required_skills}
        volunteer_skills = {skill.strip().lower() for skill in vol.skills}
        match_count = len(required.intersection(volunteer_skills))
        if match_count == 0:
            return 0.0
        raw_score = match_count / len(required)
        return round(min(raw_score * 0.8 + 0.2, 1.0), 2)

    @staticmethod
    def calculate_distance_score(route_km: float) -> float:
        score = 1.0 / (1.0 + route_km / 4.0)
        return round(max(0.0, min(score, 1.0)), 2)

    @staticmethod
    def calculate_urgency_score(urgency: int) -> float:
        return round(urgency / 5.0, 2)

    @classmethod
    def compose_final_score(cls, skill_score: float, distance_score: float, urgency_score: float, weighting: str) -> float:
        weights = {
            'balanced': {'skill': 0.45, 'distance': 0.35, 'urgency': 0.20},
            'speed': {'skill': 0.25, 'distance': 0.55, 'urgency': 0.20},
            'expertise': {'skill': 0.60, 'distance': 0.25, 'urgency': 0.15},
        }
        weight = weights.get(weighting, weights['balanced'])
        final = (
            skill_score * weight['skill']
            + distance_score * weight['distance']
            + urgency_score * weight['urgency']
        )
        return round(min(max(final, 0.0), 1.0), 2)

    @classmethod
    def score_candidate(cls, vol: Volunteer, task: Task, work_type: Optional[WorkType], weighting: str) -> Dict:
        route_km = cls.calculate_route_distance(vol.location, task.location)
        skill_score = cls.calculate_skill_score(vol, work_type)
        distance_score = cls.calculate_distance_score(route_km)
        urgency_score = cls.calculate_urgency_score(task.urgency)
        final_score = cls.compose_final_score(skill_score, distance_score, urgency_score, weighting)
        return {
            'volunteer': vol,
            'route_km': route_km,
            'skill_score': skill_score,
            'distance_score': distance_score,
            'urgency_score': urgency_score,
            'final_score': final_score,
        }

    @classmethod
    def validate_assignments_with_ai(cls, assignments: List[Assignment], request: DispatchRequest) -> List[str]:
        if not cls._verify_ollama_connection():
            logger.info('⚠️ AI 異常檢查未啟用，Ollama 連線不可用。')
            return []

        summary_lines = [
            f"任務 {assignment.task_id} 指派 {assignment.assigned_volunteers}，技能分 {assignment.score_breakdown.skill_score}，路徑分 {assignment.score_breakdown.distance_score}，緊急度 {assignment.score_breakdown.urgency_score}。"
            for assignment in assignments
        ]
        prompt = (
            '請檢查以下任務指派是否有離譜的分配或不合理的風險。'
            ' 若一切合理，回覆「正常」。'
            ' 若有疑慮，請列出簡短異常提示。'
            f"\n{chr(10).join(summary_lines)}"
        )
        try:
            logger.info('🔍 使用 AI 進行異常檢查（僅限驗證）')
            response = cls._call_ollama(cls.DEBUG_MODEL, prompt)
            lower_resp = response.strip().lower()
            if '正常' in lower_resp or 'ok' in lower_resp or 'no issue' in lower_resp:
                return []
            return [f'AI 異常檢查: {truncate_message(response.strip())}']
        except Exception as exc:
            logger.warning(truncate_message(f'⚠️ AI 異常檢查失敗: {exc}'))
            return []

    @classmethod
    def anomaly_warnings(cls, assignments: List[Assignment]) -> List[str]:
        warnings: List[str] = []
        if any(a.score_breakdown.distance_score < 0.25 for a in assignments):
            warnings.append('部分任務分配路程評分過低，請檢查路線規劃是否合理。')
        if any(a.score_breakdown.skill_score < 0.4 for a in assignments):
            warnings.append('部分任務指派的技能匹配度偏低，請確認任務類型與志工專長是否一致。')
        if not warnings:
            warnings.append('系統已完成演算法分配與本地異常檢查，未發現顯著異常。')
        return warnings

    @classmethod
    def run_assignment_algorithm(cls, available_vols: List[Volunteer], tasks: List[Task], work_types: List[WorkType], weighting: str) -> List[Assignment]:
        assignments: List[Assignment] = []
        remaining_vols = available_vols.copy()
        for task in sorted(tasks, key=lambda x: x.urgency, reverse=True):
            work_type = cls.get_work_type(task.type_id, work_types)
            candidates = [cls.score_candidate(vol, task, work_type, weighting) for vol in remaining_vols]
            if not candidates:
                assignments.append(Assignment(
                    task_id=task.id,
                    assigned_volunteers=[],
                    eta_minutes=0,
                    confidence=0.0,
                    score_breakdown=ScoreBreakdown(skill_score=0.0, distance_score=0.0, urgency_score=cls.calculate_urgency_score(task.urgency), final_score=0.0),
                    reasoning_summary=f'[演算法] 無可用志工可指派，任務 {task.id} 尚未指派。',
                ))
                continue

            candidates.sort(key=lambda item: item['final_score'], reverse=True)
            best = candidates[0]
            assigned = best['volunteer']
            eta_minutes = int((best['route_km'] / cls.AVERAGE_SPEED_KMH) * 60 + 5)
            breakdown = ScoreBreakdown(
                skill_score=best['skill_score'],
                distance_score=best['distance_score'],
                urgency_score=best['urgency_score'],
                final_score=best['final_score'],
            )
            reasoning = (
                f"{assigned.id} 具技能 {assigned.skills}，需求技能 {work_type.required_skills if work_type else '未知'}，"
                f"預估路徑長度 {best['route_km']:.2f} km，緊急度 {task.urgency}。"
            )
            if best['skill_score'] < 0.4:
                reasoning += ' 技能匹配度偏低，請留意。'

            assignments.append(Assignment(
                task_id=task.id,
                assigned_volunteers=[assigned.id],
                eta_minutes=eta_minutes,
                confidence=best['final_score'],
                score_breakdown=breakdown,
                reasoning_summary=reasoning,
            ))
            remaining_vols = [vol for vol in remaining_vols if vol.id != assigned.id]

        return assignments

    @classmethod
    def process_dispatch(cls, request: DispatchRequest):
        active_vols = cls.filter_available_volunteers(request.volunteers)
        assignments = cls.run_assignment_algorithm(
            available_vols=active_vols,
            tasks=request.tasks,
            work_types=request.work_types,
            weighting=request.metadata.priority_weighting,
        )
        warnings = cls.anomaly_warnings(assignments)
        ai_available = cls._verify_ollama_connection()
        if ai_available:
            warnings.extend(cls.validate_assignments_with_ai(assignments, request))

        return {
            'status': 'success',
            'dispatch_id': str(uuid.uuid4()),
            'incident_id': request.metadata.incident_id,
            'mode': 'algorithm_with_ai_anomaly_check' if ai_available else 'algorithm_only',
            'assignments': assignments,
            'unassigned_tasks': [a.task_id for a in assignments if not a.assigned_volunteers],
            'warnings': warnings,
        }


logger.info('🚀 Dispatch Service 初始化完成')
logger.info(f'📍 Ollama 伺服器: {DispatchService.BASE_URL}')
logger.info(f'🔍 偵錯模型: {DispatchService.DEBUG_MODEL}')
DispatchService._verify_ollama_connection()
