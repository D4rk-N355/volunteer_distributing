"""
測試腳本：測試 DispatchService 的派發邏輯
包括本地演算法、降級與 ETA 計算場景
"""

import logging
from services import DispatchService
from schemas import (
    Volunteer, Task, DispatchRequest, Location, Metadata, WorkType
)

# 設定日誌顯示
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def test_scenario_1_deterministic_dispatch():
    """測試場景 1：確定性演算法正常運作"""
    logger.info('\n' + '=' * 60)

    vols = [
        Volunteer(
            id='vol_01',
            skills=['medical', 'firstaid'],
            location=Location(lat=23.654, lng=121.432),
            availability=True
        ),
        Volunteer(
            id='vol_02',
            skills=['logistics', 'heavylifting'],
            location=Location(lat=23.660, lng=121.440),
            availability=True
        ),
        Volunteer(
            id='vol_03',
            skills=['medical'],
            location=Location(lat=23.650, lng=121.435),
            availability=True
        ),
    ]

    tasks = [
        Task(
            id='task_101',
            type_id='medical',
            location=Location(lat=23.656, lng=121.435),
            urgency=5
        ),
        Task(
            id='task_102',
            type_id='logistics',
            location=Location(lat=23.665, lng=121.445),
            urgency=3
        ),
    ]

    metadata = Metadata(
        incident_id='test-001',
        priority_weighting='balanced'
    )

    work_types = [
        WorkType(type_id='medical', required_skills=['medical', 'firstaid']),
        WorkType(type_id='logistics', required_skills=['logistics']),
    ]

    request = DispatchRequest(
        metadata=metadata,
        work_types=work_types,
        volunteers=vols,
        tasks=tasks
    )

    result = DispatchService.process_dispatch(request)

    assert result['status'] == 'success'
    assert 'dispatch_id' in result
    assert isinstance(result['assignments'], list)

    logger.info(f'派發狀態: {result["status"]}')
    logger.info(f'派發 ID: {result["dispatch_id"]}')
    logger.info(f'模式: {result["mode"]}')

    for assignment in result['assignments']:
        logger.info(f'\n  任務 {assignment.task_id}:')
        logger.info(f'    指派志工: {assignment.assigned_volunteers}')
        logger.info(f'    預估時間: {assignment.eta_minutes} 分鐘')
        logger.info(f'    決策說明: {assignment.reasoning_summary[:80]}...')

    return result


def test_scenario_2_algorithm_fallback():
    """測試場景 2：本地演算法降級（模擬 AI 異常）"""
    logger.info('\n' + '=' * 60)
    logger.info('測試場景 2：本地演算法降級（模擬 AI 異常）')
    logger.info('=' * 60)

    vols = [
        Volunteer(
            id='vol_01',
            skills=['medical'],
            location=Location(lat=23.654, lng=121.432),
            availability=True
        ),
        Volunteer(
            id='vol_02',
            skills=['search', 'rescue'],
            location=Location(lat=23.670, lng=121.450),
            availability=True
        ),
    ]

    tasks = [
        Task(
            id='task_201',
            type_id='medical',
            location=Location(lat=23.656, lng=121.435),
            urgency=4
        ),
    ]

    metadata = Metadata(
        incident_id='test-002',
        priority_weighting='speed'
    )

    work_types = [
        WorkType(type_id='medical', required_skills=['medical']),
    ]

    request = DispatchRequest(
        metadata=metadata,
        work_types=work_types,
        volunteers=vols,
        tasks=tasks
    )

    original_verify = DispatchService._verify_ollama_connection
    try:
        DispatchService._verify_ollama_connection = classmethod(lambda cls: False)
        result = DispatchService.process_dispatch(request)
    finally:
        DispatchService._verify_ollama_connection = original_verify

    assert result['status'] == 'success'
    assert result['mode'] == 'algorithm_only'
    assert set(result['assignments'][0].assigned_volunteers) == {'vol_01', 'vol_02'}
    assert result['unassigned_tasks'] == []

    logger.info(f'派發狀態: {result["status"]}')
    logger.info(f'派發 ID: {result["dispatch_id"]}')
    logger.info(f'模式: {result["mode"]}')

    for assignment in result['assignments']:
        logger.info(f'\n  任務 {assignment.task_id}:')
        logger.info(f'    指派志工: {assignment.assigned_volunteers}')
        logger.info(f'    預估時間: {assignment.eta_minutes} 分鐘')
        logger.info(f'    決策說明: {assignment.reasoning_summary}')

    return result


def test_scenario_3_more_volunteers_than_tasks():
    """測試場景 3：任務數少於志工數，應該人盡其用"""
    logger.info('\n' + '=' * 60)
    logger.info('測試場景 3：任務數少於志工數，應該人盡其用')
    logger.info('=' * 60)

    vols = [
        Volunteer(
            id='vol_01',
            skills=['medical'],
            location=Location(lat=23.654, lng=121.432),
            availability=True
        ),
        Volunteer(
            id='vol_02',
            skills=['medical', 'firstaid'],
            location=Location(lat=23.658, lng=121.434),
            availability=True
        ),
        Volunteer(
            id='vol_03',
            skills=['logistics'],
            location=Location(lat=23.660, lng=121.438),
            availability=True
        ),
    ]

    tasks = [
        Task(
            id='task_201',
            type_id='medical',
            location=Location(lat=23.656, lng=121.435),
            urgency=5
        ),
    ]

    metadata = Metadata(
        incident_id='test-003',
        priority_weighting='balanced'
    )

    work_types = [
        WorkType(type_id='medical', required_skills=['medical', 'firstaid']),
    ]

    request = DispatchRequest(
        metadata=metadata,
        work_types=work_types,
        volunteers=vols,
        tasks=tasks
    )

    result = DispatchService.process_dispatch(request)
    assert result['status'] == 'success'
    assert len(result['assignments']) == 1
    assert len(result['assignments'][0].assigned_volunteers) == 3
    assert result['unassigned_tasks'] == []

    logger.info(f'派發狀態: {result["status"]}')
    logger.info(f'任務數: {len(result["assignments"])}')
    logger.info(f'指派志工: {result["assignments"][0].assigned_volunteers}')

    return result


def test_scenario_4_task_distribution_with_extra_volunteers():
    """測試場景 4：任務數少於志工數時，仍能平均分配任務"""
    logger.info('\n' + '=' * 60)
    logger.info('測試場景 4：任務數少於志工數時，仍能平均分配任務')
    logger.info('=' * 60)

    vols = [
        Volunteer(
            id='vol_01',
            skills=['medical'],
            location=Location(lat=23.654, lng=121.432),
            availability=True
        ),
        Volunteer(
            id='vol_02',
            skills=['medical', 'firstaid'],
            location=Location(lat=23.658, lng=121.434),
            availability=True
        ),
        Volunteer(
            id='vol_03',
            skills=['logistics'],
            location=Location(lat=23.660, lng=121.438),
            availability=True
        ),
    ]

    tasks = [
        Task(
            id='task_401',
            type_id='medical',
            location=Location(lat=23.656, lng=121.435),
            urgency=5
        ),
        Task(
            id='task_402',
            type_id='logistics',
            location=Location(lat=23.665, lng=121.445),
            urgency=4
        ),
    ]

    metadata = Metadata(
        incident_id='test-004',
        priority_weighting='balanced'
    )

    work_types = [
        WorkType(type_id='medical', required_skills=['medical', 'firstaid']),
        WorkType(type_id='logistics', required_skills=['logistics']),
    ]

    request = DispatchRequest(
        metadata=metadata,
        work_types=work_types,
        volunteers=vols,
        tasks=tasks
    )

    result = DispatchService.process_dispatch(request)
    assert result['status'] == 'success'
    assert len(result['assignments']) == 2
    assert all(len(a.assigned_volunteers) >= 1 for a in result['assignments'])
    assigned_ids = {vid for assignment in result['assignments'] for vid in assignment.assigned_volunteers}
    assert assigned_ids == {'vol_01', 'vol_02', 'vol_03'}
    assert result['unassigned_tasks'] == []

    logger.info(f'派發狀態: {result["status"]}')
    logger.info(f'總任務數: {len(result["assignments"])}')
    for assignment in result['assignments']:
        logger.info(f'  任務 {assignment.task_id}: {assignment.assigned_volunteers}')

    return result


def test_scenario_4_multiple_tasks():
    """測試場景 3：多個任務，驗證志工池管理"""
    logger.info('\n' + '=' * 60)
    logger.info('測試場景 3：多個任務，驗證志工池管理')
    logger.info('=' * 60)
    logger.info('\n' + '=' * 60)

    vols = [
        Volunteer(
            id='vol_01',
            skills=['medical'],
            location=Location(lat=23.654, lng=121.432),
            availability=True
        ),
        Volunteer(
            id='vol_02',
            skills=['logistics'],
            location=Location(lat=23.660, lng=121.440),
            availability=True
        ),
        Volunteer(
            id='vol_03',
            skills=['medical', 'logistics'],
            location=Location(lat=23.650, lng=121.430),
            availability=True
        ),
    ]

    tasks = [
        Task(
            id='task_301',
            type_id='medical',
            location=Location(lat=23.656, lng=121.435),
            urgency=5
        ),
        Task(
            id='task_302',
            type_id='logistics',
            location=Location(lat=23.665, lng=121.445),
            urgency=4
        ),
        Task(
            id='task_303',
            type_id='medical',
            location=Location(lat=23.648, lng=121.428),
            urgency=3
        ),
    ]

    metadata = Metadata(
        incident_id='test-003',
        priority_weighting='balanced'
    )

    work_types = [
        WorkType(type_id='medical', required_skills=['medical']),
        WorkType(type_id='logistics', required_skills=['logistics']),
    ]

    request = DispatchRequest(
        metadata=metadata,
        work_types=work_types,
        volunteers=vols,
        tasks=tasks
    )

    result = DispatchService.process_dispatch(request)
    assert result['status'] == 'success'
    assert len(result['assignments']) == 3

    assigned_vols = set()
    for assignment in result['assignments']:
        assigned_vols.update(assignment.assigned_volunteers)

    assert len(assigned_vols) >= 2

    logger.info(f'派發狀態: {result["status"]}')
    logger.info(f'總任務數: {len(result["assignments"])}')
    logger.info(f'指派的志工 ID: {assigned_vols}')

    return result


def test_scenario_4_check_eta_calculation():
    """測試場景 4：驗證 ETA 計算"""
    logger.info('\n' + '=' * 60)
    logger.info('測試場景 4：ETA 計算驗證')
    logger.info('=' * 60)

    vols = [
        Volunteer(
            id='vol_eta_test',
            skills=['test'],
            location=Location(lat=23.654, lng=121.432),
            availability=True
        ),
    ]

    tasks = [
        Task(
            id='task_eta',
            type_id='test',
            location=Location(lat=23.654 + 0.01, lng=121.432),
            urgency=1
        ),
    ]

    metadata = Metadata(
        incident_id='test-eta',
        priority_weighting='balanced'
    )

    work_types = [
        WorkType(type_id='test', required_skills=['test']),
    ]

    request = DispatchRequest(
        metadata=metadata,
        work_types=work_types,
        volunteers=vols,
        tasks=tasks
    )

    result = DispatchService.process_dispatch(request)
    assert result['status'] == 'success'

    for assignment in result['assignments']:
        eta = assignment.eta_minutes
        logger.info(f'\n  任務 {assignment.task_id}:')
        logger.info(f'    指派志工: {assignment.assigned_volunteers}')
        logger.info(f'    預估時間: {eta} 分鐘')
        assert 8 <= eta <= 10

    return result


if __name__ == '__main__':
    logger.info('\n🚀 開始測試 Dispatch Service')
    logger.info('共 4 個測試場景')

    try:
        test_scenario_1_deterministic_dispatch()
        test_scenario_2_algorithm_fallback()
        test_scenario_3_more_volunteers_than_tasks()
        test_scenario_4_multiple_tasks()
        test_scenario_4_check_eta_calculation()

        logger.info('\n' + '=' * 60)
        logger.info('✅ 所有測試完成')
        logger.info('=' * 60)
    except AssertionError as e:
        logger.error(f'❌ 測試斷言失敗: {e}')
    except Exception as e:
        logger.error(f'❌ 測試過程中發生錯誤: {e}', exc_info=True)
