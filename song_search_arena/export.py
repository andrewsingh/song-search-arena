#!/usr/bin/env python3
"""
Export utilities for Song Search Arena
Generates CSV and JSON exports from database and uploads to Supabase Storage.
"""
import csv
import json
import io
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from supabase import Client

try:
    from . import constants
except ImportError:
    import constants

logger = logging.getLogger(__name__)


def export_judgments_csv(supabase: Client) -> str:
    """
    Export all judgments to CSV format.

    Returns CSV string with columns:
    judgment_id, task_id, rater_id, session_id, choice, confidence,
    left_system_id, right_system_id, query_id, task_type,
    left_list, right_list, rng_seed, submitted_at
    """
    # Get all judgments with task details
    judgments_result = supabase.table('judgments').select(
        'judgment_id, task_id, rater_id, session_id, choice, confidence, '
        'left_system_id, right_system_id, left_list, right_list, '
        'rng_seed, submitted_at'
    ).execute()

    # Get task details to include query_id and task_type
    tasks_result = supabase.table('tasks').select('task_id, query_id').execute()
    task_to_query = {t['task_id']: t['query_id'] for t in tasks_result.data}

    queries_result = supabase.table('queries').select('query_id, task_type').execute()
    query_to_type = {q['query_id']: q['task_type'] for q in queries_result.data}

    # Create CSV in memory
    output = io.StringIO()
    fieldnames = [
        'judgment_id', 'task_id', 'rater_id', 'session_id', 'choice', 'confidence',
        'left_system_id', 'right_system_id', 'query_id', 'task_type',
        'left_list', 'right_list', 'rng_seed', 'submitted_at'
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for judgment in judgments_result.data:
        query_id = task_to_query.get(judgment['task_id'])
        task_type = query_to_type.get(query_id) if query_id else None

        row = {
            'judgment_id': judgment['judgment_id'],
            'task_id': judgment['task_id'],
            'rater_id': judgment['rater_id'],
            'session_id': judgment['session_id'],
            'choice': judgment['choice'],
            'confidence': judgment['confidence'],
            'left_system_id': judgment['left_system_id'],
            'right_system_id': judgment['right_system_id'],
            'query_id': query_id,
            'task_type': task_type,
            'left_list': json.dumps(judgment['left_list']),
            'right_list': json.dumps(judgment['right_list']),
            'rng_seed': judgment.get('rng_seed'),
            'submitted_at': judgment['submitted_at']
        }
        writer.writerow(row)

    return output.getvalue()


def export_judgments_json(supabase: Client) -> str:
    """
    Export all judgments to JSON format.

    Returns JSON array of judgment objects with full details.
    """
    # Get all judgments with task details
    judgments_result = supabase.table('judgments').select(
        'judgment_id, task_id, rater_id, session_id, choice, confidence, '
        'left_system_id, right_system_id, left_list, right_list, '
        'rng_seed, submitted_at'
    ).execute()

    # Get task details
    tasks_result = supabase.table('tasks').select('task_id, query_id, pair_id').execute()
    task_map = {t['task_id']: t for t in tasks_result.data}

    # Get queries
    queries_result = supabase.table('queries').select('*').execute()
    query_map = {q['query_id']: q for q in queries_result.data}

    # Enrich judgments with query and task details
    enriched_judgments = []
    for judgment in judgments_result.data:
        task = task_map.get(judgment['task_id'])
        query = query_map.get(task['query_id']) if task else None

        enriched = {
            **judgment,
            'query_id': task['query_id'] if task else None,
            'pair_id': task['pair_id'] if task else None,
            'task_type': query['task_type'] if query else None,
            'query_text': query.get('query_text') if query else None,
            'seed_track_id': query.get('seed_track_id') if query else None,
            'genres': query.get('genres') if query else None
        }
        enriched_judgments.append(enriched)

    return json.dumps(enriched_judgments, indent=2)


def export_final_lists_csv(supabase: Client, policy_version: Optional[str] = None) -> str:
    """
    Export final lists to CSV format.

    Args:
        policy_version: If specified, export only this policy version. Otherwise export active policy.

    Returns CSV string with columns:
    policy_version, system_id, query_id, position, track_id
    """
    # Get policy version
    if not policy_version:
        policy_result = supabase.table('policies').select('policy_version').eq('active', True).execute()
        if not policy_result.data:
            raise ValueError("No active policy found")
        policy_version = policy_result.data[0]['policy_version']

    # Get final lists for this policy
    final_lists_result = supabase.table('final_lists').select(
        'policy_version, system_id, query_id, final_order'
    ).eq('policy_version', policy_version).execute()

    # Create CSV in memory
    output = io.StringIO()
    fieldnames = ['policy_version', 'system_id', 'query_id', 'position', 'track_id']

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for final_list in final_lists_result.data:
        for position, track_id in enumerate(final_list['final_order'], start=1):
            row = {
                'policy_version': final_list['policy_version'],
                'system_id': final_list['system_id'],
                'query_id': final_list['query_id'],
                'position': position,
                'track_id': track_id
            }
            writer.writerow(row)

    return output.getvalue()


def export_final_lists_json(supabase: Client, policy_version: Optional[str] = None) -> str:
    """
    Export final lists to JSON format.

    Args:
        policy_version: If specified, export only this policy version. Otherwise export active policy.

    Returns JSON array of final list objects.
    """
    # Get policy version
    if not policy_version:
        policy_result = supabase.table('policies').select('policy_version').eq('active', True).execute()
        if not policy_result.data:
            raise ValueError("No active policy found")
        policy_version = policy_result.data[0]['policy_version']

    # Get final lists for this policy
    final_lists_result = supabase.table('final_lists').select(
        'policy_version, system_id, query_id, final_order, generated_at'
    ).eq('policy_version', policy_version).execute()

    return json.dumps(final_lists_result.data, indent=2)


def export_task_progress_csv(supabase: Client) -> str:
    """
    Export task progress to CSV format.

    Returns CSV string with columns:
    task_id, query_id, pair_id, left_system_id, right_system_id,
    target_judgments, completed_judgments, is_practice
    """
    # Get all tasks
    tasks_result = supabase.table('tasks').select(
        'task_id, query_id, pair_id, target_judgments, is_practice'
    ).execute()

    # Get pairs
    pairs_result = supabase.table('pairs').select('pair_id, left_system_id, right_system_id').execute()
    pair_map = {p['pair_id']: p for p in pairs_result.data}

    # Count completed judgments per task
    judgments_result = supabase.table('judgments').select('task_id').execute()
    judgment_counts = {}
    for j in judgments_result.data:
        task_id = j['task_id']
        judgment_counts[task_id] = judgment_counts.get(task_id, 0) + 1

    # Create CSV in memory
    output = io.StringIO()
    fieldnames = [
        'task_id', 'query_id', 'pair_id', 'left_system_id', 'right_system_id',
        'target_judgments', 'completed_judgments', 'is_practice'
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for task in tasks_result.data:
        pair = pair_map.get(task['pair_id'])

        row = {
            'task_id': task['task_id'],
            'query_id': task['query_id'],
            'pair_id': task['pair_id'],
            'left_system_id': pair['left_system_id'] if pair else None,
            'right_system_id': pair['right_system_id'] if pair else None,
            'target_judgments': task['target_judgments'],
            'completed_judgments': judgment_counts.get(task['task_id'], 0),
            'is_practice': task.get('is_practice', False)
        }
        writer.writerow(row)

    return output.getvalue()


def export_rater_stats_csv(supabase: Client) -> str:
    """
    Export per-rater statistics to CSV format.

    Returns CSV string with columns:
    rater_id, display_name, total_judgments, unique_queries_judged,
    avg_confidence, first_judgment_at, last_judgment_at
    """
    # Get all raters
    raters_result = supabase.table('raters').select('rater_id, display_name').execute()

    # Get all judgments
    judgments_result = supabase.table('judgments').select(
        'rater_id, task_id, confidence, submitted_at'
    ).execute()

    # Get task to query mapping
    tasks_result = supabase.table('tasks').select('task_id, query_id').execute()
    task_to_query = {t['task_id']: t['query_id'] for t in tasks_result.data}

    # Compute stats per rater
    rater_stats = {}
    for judgment in judgments_result.data:
        rater_id = judgment['rater_id']

        if rater_id not in rater_stats:
            rater_stats[rater_id] = {
                'total_judgments': 0,
                'unique_queries': set(),
                'confidences': [],
                'timestamps': []
            }

        rater_stats[rater_id]['total_judgments'] += 1
        rater_stats[rater_id]['confidences'].append(judgment['confidence'])
        rater_stats[rater_id]['timestamps'].append(judgment['submitted_at'])

        query_id = task_to_query.get(judgment['task_id'])
        if query_id:
            rater_stats[rater_id]['unique_queries'].add(query_id)

    # Create CSV in memory
    output = io.StringIO()
    fieldnames = [
        'rater_id', 'display_name', 'total_judgments', 'unique_queries_judged',
        'avg_confidence', 'first_judgment_at', 'last_judgment_at'
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    # Write rows for all raters (including those with zero judgments)
    for rater in raters_result.data:
        rater_id = rater['rater_id']
        stats = rater_stats.get(rater_id)

        if stats:
            avg_confidence = sum(stats['confidences']) / len(stats['confidences']) if stats['confidences'] else 0
            row = {
                'rater_id': rater_id,
                'display_name': rater.get('display_name'),
                'total_judgments': stats['total_judgments'],
                'unique_queries_judged': len(stats['unique_queries']),
                'avg_confidence': round(avg_confidence, 2),
                'first_judgment_at': min(stats['timestamps']) if stats['timestamps'] else None,
                'last_judgment_at': max(stats['timestamps']) if stats['timestamps'] else None
            }
        else:
            # Rater with no judgments
            row = {
                'rater_id': rater_id,
                'display_name': rater.get('display_name'),
                'total_judgments': 0,
                'unique_queries_judged': 0,
                'avg_confidence': 0,
                'first_judgment_at': None,
                'last_judgment_at': None
            }

        writer.writerow(row)

    return output.getvalue()


def upload_to_storage(supabase: Client, bucket_name: str, file_path: str, content: str, content_type: str = "text/plain") -> str:
    """
    Upload content to Supabase Storage.

    Args:
        supabase: Supabase client
        bucket_name: Storage bucket name
        file_path: Path within bucket (e.g., 'exports/judgments_2024-01-15.csv')
        content: File content as string
        content_type: MIME type for the file

    Returns:
        Public URL of uploaded file
    """
    try:
        # Upload to storage (upsert to handle existing files)
        supabase.storage.from_(bucket_name).upload(
            file_path,
            content.encode('utf-8'),
            file_options={"content-type": content_type, "upsert": "true"}
        )

        # Get public URL
        url = supabase.storage.from_(bucket_name).get_public_url(file_path)

        logger.info(f"Uploaded {file_path} to storage bucket {bucket_name}")
        return url

    except Exception as e:
        logger.error(f"Failed to upload to storage: {e}")
        raise


def generate_signed_url(supabase: Client, bucket_name: str, file_path: str, expires_in: int = 3600) -> str:
    """
    Generate a signed URL for downloading a file from storage.

    Args:
        supabase: Supabase client
        bucket_name: Storage bucket name
        file_path: Path within bucket
        expires_in: URL expiration time in seconds (default 1 hour)

    Returns:
        Signed URL
    """
    try:
        signed_url = supabase.storage.from_(bucket_name).create_signed_url(
            file_path,
            expires_in
        )
        return signed_url['signedURL']
    except Exception as e:
        logger.error(f"Failed to generate signed URL: {e}")
        raise


def export_and_upload(
    supabase: Client,
    export_type: str,
    format: str,
    bucket_name: str,
    policy_version: Optional[str] = None
) -> Dict[str, str]:
    """
    Export data and upload to storage.

    Args:
        supabase: Supabase client
        export_type: Type of export ('judgments', 'final_lists', 'task_progress', 'rater_stats')
        format: Export format ('csv' or 'json')
        bucket_name: Storage bucket name
        policy_version: Optional policy version (for final_lists export)

    Returns:
        Dict with 'file_path' and 'url' keys
    """
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d_%H-%M-%S')
    file_name = f"{export_type}_{timestamp}.{format}"
    file_path = f"{constants.EXPORT_PATH_PREFIX}{file_name}"

    # Determine content type
    content_type = "text/csv" if format == "csv" else "application/json"

    # Generate export content
    if export_type == 'judgments':
        if format == 'csv':
            content = export_judgments_csv(supabase)
        else:
            content = export_judgments_json(supabase)
    elif export_type == 'final_lists':
        if format == 'csv':
            content = export_final_lists_csv(supabase, policy_version)
        else:
            content = export_final_lists_json(supabase, policy_version)
    elif export_type == 'task_progress':
        if format == 'csv':
            content = export_task_progress_csv(supabase)
        else:
            raise ValueError("task_progress only supports CSV format")
    elif export_type == 'rater_stats':
        if format == 'csv':
            content = export_rater_stats_csv(supabase)
        else:
            raise ValueError("rater_stats only supports CSV format")
    else:
        raise ValueError(f"Unknown export type: {export_type}")

    # Check if content is empty
    if not content or (format == 'csv' and content.count('\n') <= 1):
        raise ValueError(f"No data available for export type: {export_type}")

    # Upload to storage
    url = upload_to_storage(supabase, bucket_name, file_path, content, content_type)

    return {
        'file_path': file_path,
        'url': url
    }
