"""
Scheduler for Song Search Arena
DB-only task scheduling with randomization
"""
import logging
import random
import hashlib
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone

from supabase import Client

try:
    from . import constants, db_utils
except ImportError:
    import constants, db_utils

logger = logging.getLogger(__name__)


def get_next_task(supabase: Client, rater_id: str, tracks: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Get the next task for a rater using the scheduler algorithm.

    Algorithm:
    1. Group queries by how many times the rater has seen them
    2. Select from the group with minimum seen count
    3. Within that group, find the most underfilled task
    4. Break ties randomly
    5. Stop when rater has seen all queries (S-1) times, where S = number of systems

    Args:
        supabase: Supabase client
        rater_id: Rater ID
        tracks: Dictionary of track metadata

    Returns:
        Task dict with all necessary data for rendering, or None if no tasks available
    """
    # Get all queries
    queries_result = supabase.table('queries').select('query_id').execute()
    all_query_ids = {q['query_id'] for q in queries_result.data}

    if not all_query_ids:
        logger.info(f"No queries available")
        return None

    # Get rater's assignments grouped by query
    assignments_result = supabase.table('task_assignments').select(
        'task_id, completed'
    ).eq('rater_id', rater_id).execute()

    # Get task info for assignments to map task_id -> query_id
    if assignments_result.data:
        task_ids = [a['task_id'] for a in assignments_result.data]
        tasks_result = supabase.table('tasks').select('task_id, query_id').in_('task_id', task_ids).execute()
        task_to_query = {t['task_id']: t['query_id'] for t in tasks_result.data}
    else:
        task_to_query = {}

    # Count how many times each query has been seen (completed assignments only)
    query_seen_count = {}
    for assignment in assignments_result.data:
        if assignment['completed']:
            query_id = task_to_query.get(assignment['task_id'])
            if query_id:
                query_seen_count[query_id] = query_seen_count.get(query_id, 0) + 1

    # Determine minimum seen count across all queries
    min_seen = 0
    if query_seen_count:
        all_seen_counts = [query_seen_count.get(qid, 0) for qid in all_query_ids]
        min_seen = min(all_seen_counts)

    # Get number of systems to determine stopping condition
    systems_result = supabase.table('systems').select('system_id').execute()
    num_systems = len(systems_result.data)

    # Calculate pairs per query: C(S, 2) = S * (S-1) / 2
    pairs_per_query = num_systems * (num_systems - 1) // 2 if num_systems >= 2 else 0

    # Check stopping condition: if min_seen >= pairs_per_query, rater is done
    if min_seen >= pairs_per_query:
        logger.info(f"Rater {rater_id} has completed all queries {pairs_per_query} times (all pairs seen)")
        return None

    # Get queries that have been seen exactly min_seen times
    candidate_queries = [qid for qid in all_query_ids if query_seen_count.get(qid, 0) == min_seen]

    logger.info(f"Rater {rater_id}: min_seen={min_seen}, candidate_queries={len(candidate_queries)}")

    # Get all tasks for these queries
    all_tasks_result = supabase.table('tasks').select('*').in_('query_id', candidate_queries).execute()
    candidate_tasks = all_tasks_result.data

    # Filter out tasks already assigned to this rater
    assigned_task_ids = {a['task_id'] for a in assignments_result.data}
    available_tasks = [t for t in candidate_tasks if t['task_id'] not in assigned_task_ids]

    if not available_tasks:
        logger.info(f"No available tasks for rater {rater_id}")
        return None

    # Find most underfilled task among available tasks
    best_task = None
    min_fill_ratio = float('inf')

    for task in available_tasks:
        fill_ratio = task['collected_judgments'] / task['target_judgments']
        if fill_ratio < min_fill_ratio:
            min_fill_ratio = fill_ratio
            best_task = task

    if not best_task:
        logger.info(f"No best task found for rater {rater_id}")
        return None

    # Create assignment
    db_utils.create_task_assignment(supabase, rater_id, best_task['task_id'])

    # Build full task data with randomization
    task_data = build_task_data(supabase, best_task, rater_id, tracks)

    return task_data


def build_task_data(supabase: Client, task: Dict[str, Any], rater_id: str, tracks: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build complete task data with randomization for presentation.

    Randomization includes:
    1. Left/right system assignment (flip coin)
    2. Independent shuffling of left and right lists
    3. RNG seed generation for reproducibility

    Args:
        supabase: Supabase client
        task: Task dict from database
        rater_id: Rater ID
        tracks: Dictionary of track metadata
    """
    # Get query
    query_result = supabase.table('queries').select('*').eq('query_id', task['query_id']).execute()
    query = query_result.data[0]

    # Get pair
    pair_result = supabase.table('pairs').select('*').eq('pair_id', task['pair_id']).execute()
    pair = pair_result.data[0]

    # Get active policy
    policy = db_utils.get_active_policy(supabase)
    policy_version = policy['policy_version']

    # Get final lists for both systems
    left_list_result = supabase.table('final_lists').select('final_order').eq(
        'policy_version', policy_version
    ).eq('system_id', pair['left_system_id']).eq('query_id', task['query_id']).execute()

    right_list_result = supabase.table('final_lists').select('final_order').eq(
        'policy_version', policy_version
    ).eq('system_id', pair['right_system_id']).eq('query_id', task['query_id']).execute()

    if not left_list_result.data or not right_list_result.data:
        logger.error(f"Missing final lists for task {task['task_id']}")
        return None

    left_track_ids = left_list_result.data[0]['final_order']
    right_track_ids = right_list_result.data[0]['final_order']

    # Generate RNG seed (deterministic based on task + rater + timestamp)
    rng_seed = hashlib.sha256(
        f"{task['task_id']}:{rater_id}:{datetime.now(timezone.utc).isoformat()}".encode()
    ).hexdigest()[:16]

    # Initialize random with seed for reproducibility
    rng = random.Random(rng_seed)

    # Randomize left/right assignment (50/50 coin flip)
    flip = rng.random() < 0.5
    if flip:
        left_system_id = pair['right_system_id']
        right_system_id = pair['left_system_id']
        left_track_ids, right_track_ids = right_track_ids, left_track_ids
    else:
        left_system_id = pair['left_system_id']
        right_system_id = pair['right_system_id']

    # Shuffle left and right lists independently
    left_shuffled = left_track_ids.copy()
    right_shuffled = right_track_ids.copy()
    rng.shuffle(left_shuffled)
    rng.shuffle(right_shuffled)

    # Get track metadata from in-memory tracks dictionary
    all_track_ids = left_shuffled + right_shuffled
    if query['task_type'] == constants.TASK_TYPE_SONG and query['seed_track_id']:
        all_track_ids.append(query['seed_track_id'])

    track_data = db_utils.get_tracks_by_ids(tracks, all_track_ids)

    # Build left and right lists with metadata
    left_list = [track_data.get(tid) for tid in left_shuffled if track_data.get(tid)]
    right_list = [track_data.get(tid) for tid in right_shuffled if track_data.get(tid)]

    # Build seed track data for song queries
    seed_track = None
    if query['task_type'] == constants.TASK_TYPE_SONG and query['seed_track_id']:
        seed_track = track_data.get(query['seed_track_id'])

    # Build response
    task_data = {
        'task_id': task['task_id'],
        'query_id': query['query_id'],
        'task_type': query['task_type'],
        'query_text': query.get('query_text'),
        'seed_track': seed_track,
        'left_system_id': left_system_id,
        'right_system_id': right_system_id,
        'left_list': left_list,
        'right_list': right_list,
        'rng_seed': rng_seed,
        'is_practice': task.get('is_practice', False)
    }

    logger.info(f"Prepared task {task['task_id']} for rater {rater_id} (query: {query['query_id']}, pair: {task['pair_id']})")

    return task_data


def submit_judgment(
    supabase: Client,
    rater_id: str,
    session_id: str,
    task_id: str,
    choice: str,
    confidence: int,
    presented_at: str,
    task_data: Dict[str, Any]
) -> str:
    """
    Submit a judgment and update task status.

    Returns:
        judgment_id
    """
    # Validate choice and confidence
    if choice not in constants.VALID_CHOICES:
        raise ValueError(constants.ERROR_INVALID_CHOICE)

    if confidence < constants.MIN_CONFIDENCE or confidence > constants.MAX_CONFIDENCE:
        raise ValueError(constants.ERROR_INVALID_CONFIDENCE)

    # Get task to find pair and query info
    task_result = supabase.table('tasks').select('*').eq('task_id', task_id).execute()
    if not task_result.data:
        raise ValueError(f"Task {task_id} not found")

    task = task_result.data[0]

    # Get pair info
    pair_result = supabase.table('pairs').select('*').eq('pair_id', task['pair_id']).execute()
    pair = pair_result.data[0]

    # Build judgment data
    judgment_data = {
        'session_id': session_id,
        'rater_id': rater_id,
        'query_id': task['query_id'],
        'pair_id': task['pair_id'],
        'left_system_id': task_data['left_system_id'],
        'right_system_id': task_data['right_system_id'],
        'left_list': [t['id'] for t in task_data['left_list']],
        'right_list': [t['id'] for t in task_data['right_list']],
        'choice': choice,
        'confidence': confidence,
        'rng_seed': task_data['rng_seed'],
        'presented_at': presented_at,
        'submitted_at': datetime.now(timezone.utc).isoformat()
    }

    # Insert judgment
    judgment_id = db_utils.insert_judgment(supabase, judgment_data)

    # Mark assignment as completed
    db_utils.complete_task_assignment(supabase, rater_id, task_id)

    # Increment task judgment count
    db_utils.increment_task_judgments(supabase, task_id)

    logger.info(f"Judgment {judgment_id} submitted by rater {rater_id} for task {task_id}: {choice} (confidence: {confidence})")

    return judgment_id


def get_rater_progress(supabase: Client, rater_id: str) -> Dict[str, Any]:
    """
    Get progress statistics for a rater.

    Returns:
        Dict with total_tasks, completed_tasks, percentage
    """
    # Get total tasks available
    total_tasks_result = supabase.table('tasks').select('task_id').execute()
    total_tasks = len(total_tasks_result.data)

    # Get rater's completed assignments
    assignments_result = supabase.table('task_assignments').select('*').eq(
        'rater_id', rater_id
    ).eq('completed', True).execute()
    completed_tasks = len(assignments_result.data)

    # Get rater's total assignments (including in-progress)
    all_assignments_result = supabase.table('task_assignments').select('task_id').eq(
        'rater_id', rater_id
    ).execute()
    assigned_tasks = len(all_assignments_result.data)

    # Check caps
    rater_result = supabase.table('raters').select('soft_cap, total_cap').eq('rater_id', rater_id).execute()
    if rater_result.data:
        soft_cap = rater_result.data[0].get('soft_cap', constants.DEFAULT_SOFT_CAP)
        total_cap = rater_result.data[0].get('total_cap', total_tasks)
    else:
        soft_cap = constants.DEFAULT_SOFT_CAP
        total_cap = total_tasks

    percentage = (completed_tasks / total_cap * 100) if total_cap > 0 else 0

    return {
        'total_tasks': total_cap,
        'completed_tasks': completed_tasks,
        'assigned_tasks': assigned_tasks,
        'percentage': round(percentage, 1),
        'soft_cap': soft_cap,
        'can_continue': assigned_tasks < soft_cap and assigned_tasks < total_cap
    }
