"""
Database utility functions for Song Search Arena
Handles all Supabase database operations
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import hashlib
import json

from supabase import Client

try:
    from . import constants, models
except ImportError:
    import constants, models

logger = logging.getLogger(__name__)


# ===== Helper Functions =====

def compute_hash(data: Dict[str, Any]) -> str:
    """Compute SHA-256 hash of dictionary (for config hashing)."""
    # Canonicalize JSON to ensure consistent hashing
    canonical_json = json.dumps(data, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical_json.encode()).hexdigest()


# ===== Query Operations =====

def insert_queries(supabase: Client, queries: List[models.EvalQuery], tracks: Dict[str, Any] = None) -> Tuple[int, List[str]]:
    """
    Insert queries into database.

    Args:
        supabase: Supabase client
        queries: List of queries to insert
        tracks: In-memory tracks dictionary (optional, for validation)

    Returns: (count_inserted, errors)
    """
    errors = []
    inserted = 0

    for query in queries:
        try:
            data = {
                'query_id': query.id,
                'task_type': query.type,
                'query_text': query.text,
                'seed_track_id': query.track_id,
                'intents': query.intents or [],
                'genres': query.genres or [],
                'era': query.era
            }

            # Check if seed track exists for song queries (use in-memory tracks if available)
            if query.type == constants.TASK_TYPE_SONG and query.track_id:
                if tracks is not None:
                    # Check in-memory tracks dictionary
                    if query.track_id not in tracks:
                        errors.append(f"Track {query.track_id} not found in tracks metadata for query {query.id}")
                        continue
                # If tracks dict not provided, skip validation (for backwards compatibility)

            # Upsert query
            supabase.table('queries').upsert(data).execute()
            inserted += 1
            logger.info(f"Inserted query {query.id}")

        except Exception as e:
            errors.append(f"Error inserting query {query.id}: {str(e)}")
            logger.error(f"Error inserting query {query.id}: {e}")

    return inserted, errors


# ===== System & Candidate Operations =====

def upsert_system(supabase: Client, system_id: str, config: Optional[Dict[str, Any]], dataset_id: str) -> None:
    """Upsert system into database."""
    config_hash = compute_hash(config) if config else None

    data = {
        'system_id': system_id,
        'config_json': config,
        'config_hash': config_hash,
        'dataset_id': dataset_id
    }

    supabase.table('systems').upsert(data).execute()
    logger.info(f"Upserted system {system_id}")


def insert_candidates(supabase: Client, responses: List[models.EvalResponse], tracks: Dict[str, Any]) -> Tuple[int, List[str]]:
    """
    Insert candidates from system responses.

    Args:
        supabase: Supabase client
        responses: List of EvalResponse objects
        tracks: Dictionary of track metadata (track_id -> track_data)

    Returns: (count_inserted, errors)
    """
    errors = []
    inserted = 0

    for response in responses:
        try:
            # Upsert system
            upsert_system(supabase, response.system_id, response.config, response.dataset_id)

            # Validate query exists
            query_result = supabase.table('queries').select('query_id').eq('query_id', response.query_id).execute()
            if not query_result.data:
                errors.append(f"Query {response.query_id} not found for system {response.system_id}")
                continue

            # Validate all tracks exist in the tracks dictionary
            track_ids = [c.track_id for c in response.candidates]
            missing_tracks = [tid for tid in track_ids if tid not in tracks]

            if missing_tracks:
                # Show first 5 missing tracks to avoid huge error messages
                errors.append(f"Tracks not found in system {response.system_id} query {response.query_id}: {', '.join(missing_tracks[:5])}")
                continue  # Skip this entire response

            # Insert candidates
            candidates_data = []
            for candidate in response.candidates:
                candidates_data.append({
                    'system_id': response.system_id,
                    'query_id': response.query_id,
                    'rank': candidate.rank,
                    'track_id': candidate.track_id,
                    'score': candidate.score,
                    'extras': candidate.extras
                })

            if candidates_data:
                supabase.table('candidates').upsert(candidates_data).execute()
                inserted += len(candidates_data)
                logger.info(f"Inserted {len(candidates_data)} candidates for {response.system_id}/{response.query_id}")

        except Exception as e:
            errors.append(f"Error inserting candidates for {response.system_id}/{response.query_id}: {str(e)}")
            logger.error(f"Error inserting candidates: {e}")

    return inserted, errors


# ===== Policy Operations =====

def set_active_policy(supabase: Client, policy: models.Policy) -> None:
    """Set active policy (deactivates all others)."""
    # Deactivate all existing policies
    supabase.table('policies').update({'active': False}).neq('policy_version', 'dummy').execute()

    # Insert/update new policy as active
    policy_hash = compute_hash(policy.to_dict())
    data = {
        'policy_version': policy.version,
        'policy_json': {**policy.to_dict(), 'hash': policy_hash},
        'active': True
    }

    supabase.table('policies').upsert(data).execute()
    logger.info(f"Set active policy: {policy.version}")


def get_active_policy(supabase: Client) -> Optional[Dict[str, Any]]:
    """Get active policy."""
    result = supabase.table('policies').select('*').eq('active', True).execute()
    if result.data:
        return result.data[0]
    return None


# ===== Track Operations =====

def get_track_by_id(supabase: Client, track_id: str) -> Optional[Dict[str, Any]]:
    """Get track metadata by ID."""
    result = supabase.table('tracks').select('*').eq('track_id', track_id).execute()
    if result.data:
        return result.data[0]
    return None


def get_tracks_by_ids(tracks: Dict[str, Any], track_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Get multiple tracks by IDs from in-memory tracks dictionary.

    Args:
        tracks: Dictionary of all track metadata (track_id -> track_data)
        track_ids: List of track IDs to retrieve

    Returns: dict mapping track_id -> metadata
    """
    return {tid: tracks[tid] for tid in track_ids if tid in tracks}


# ===== Task & Assignment Operations =====

def get_underfilled_task(supabase: Client, rater_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the most underfilled task for a rater.
    Returns None if no tasks available or rater has reached cap.
    """
    # Check rater caps
    rater_result = supabase.table('raters').select('soft_cap, total_cap').eq('rater_id', rater_id).execute()
    if not rater_result.data:
        return None

    rater = rater_result.data[0]
    soft_cap = rater.get('soft_cap', constants.DEFAULT_SOFT_CAP)
    total_cap = rater.get('total_cap')

    # Count rater's assignments
    assignments_result = supabase.table('task_assignments').select('task_id').eq('rater_id', rater_id).execute()
    rater_task_count = len(assignments_result.data)

    # Check caps
    if soft_cap and rater_task_count >= soft_cap:
        logger.info(f"Rater {rater_id} has reached soft cap ({soft_cap})")
        return None

    if total_cap and rater_task_count >= total_cap:
        logger.info(f"Rater {rater_id} has reached total cap ({total_cap})")
        return None

    # Get all tasks
    tasks_result = supabase.table('tasks').select('*').eq('done', False).execute()
    if not tasks_result.data:
        return None

    # Get rater's assignments
    assigned_task_ids = {a['task_id'] for a in assignments_result.data}

    # Find most underfilled task not assigned to this rater
    best_task = None
    min_fill_ratio = float('inf')

    for task in tasks_result.data:
        if task['task_id'] in assigned_task_ids:
            continue

        fill_ratio = task['collected_judgments'] / task['target_judgments']
        if fill_ratio < min_fill_ratio:
            min_fill_ratio = fill_ratio
            best_task = task

    return best_task


def create_task_assignment(supabase: Client, rater_id: str, task_id: str) -> None:
    """Create task assignment."""
    data = {
        'rater_id': rater_id,
        'task_id': task_id,
        'assigned_at': datetime.utcnow().isoformat(),
        'completed': False
    }
    supabase.table('task_assignments').insert(data).execute()
    logger.info(f"Assigned task {task_id} to rater {rater_id}")


def complete_task_assignment(supabase: Client, rater_id: str, task_id: str) -> None:
    """Mark task assignment as completed."""
    supabase.table('task_assignments').update({'completed': True}).eq('rater_id', rater_id).eq('task_id', task_id).execute()


def increment_task_judgments(supabase: Client, task_id: str) -> None:
    """Increment collected_judgments count and mark done if target reached."""
    # Get current task
    task_result = supabase.table('tasks').select('*').eq('task_id', task_id).execute()
    if not task_result.data:
        return

    task = task_result.data[0]
    new_count = task['collected_judgments'] + 1
    is_done = new_count >= task['target_judgments']

    supabase.table('tasks').update({
        'collected_judgments': new_count,
        'done': is_done
    }).eq('task_id', task_id).execute()

    logger.info(f"Task {task_id}: {new_count}/{task['target_judgments']} judgments")


# ===== Judgment Operations =====

def insert_judgment(supabase: Client, judgment_data: Dict[str, Any]) -> str:
    """Insert judgment and return judgment_id."""
    result = supabase.table('judgments').insert(judgment_data).execute()
    judgment_id = result.data[0]['judgment_id']
    logger.info(f"Inserted judgment {judgment_id}")
    return judgment_id


# ===== Stats & Admin Operations =====

def get_admin_stats(supabase: Client) -> models.AdminStats:
    """Get admin dashboard statistics."""
    queries_count = len(supabase.table('queries').select('query_id').execute().data)
    systems_count = len(supabase.table('systems').select('system_id').execute().data)
    pairs_count = len(supabase.table('pairs').select('pair_id').execute().data)
    tasks_result = supabase.table('tasks').select('*').execute()
    tasks_count = len(tasks_result.data)
    completed_tasks = sum(1 for t in tasks_result.data if t['done'])
    judgments_count = len(supabase.table('judgments').select('judgment_id').execute().data)
    raters_count = len(supabase.table('raters').select('rater_id').execute().data)

    active_policy = get_active_policy(supabase)

    return models.AdminStats(
        total_queries=queries_count,
        total_systems=systems_count,
        total_pairs=pairs_count,
        total_tasks=tasks_count,
        completed_tasks=completed_tasks,
        total_judgments=judgments_count,
        unique_raters=raters_count,
        active_policy=active_policy
    )


def get_progress_grid(supabase: Client) -> List[Dict[str, Any]]:
    """Get progress grid (query × pair) for admin dashboard."""
    # Get all tasks with their info
    tasks_result = supabase.table('tasks').select(
        'task_id, query_id, pair_id, target_judgments, collected_judgments, done'
    ).execute()

    # Group by (query_id, pair_id)
    grid = {}
    for task in tasks_result.data:
        key = (task['query_id'], task['pair_id'])
        if key not in grid:
            grid[key] = {
                'query_id': task['query_id'],
                'pair_id': task['pair_id'],
                'target': task['target_judgments'],
                'collected': task['collected_judgments'],
                'done': task['done']
            }

    return list(grid.values())
