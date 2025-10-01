"""
Post-processing logic for Song Search Arena
Implements Arena-owned filtering: 1-per-artist, seed exclusion, deduplication, backfill
"""
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Set

from supabase import Client

try:
    from . import constants, db_utils
except ImportError:
    import constants, db_utils

logger = logging.getLogger(__name__)


class PostProcessor:
    """Arena post-processing engine."""

    def __init__(self, supabase: Client, policy: Dict[str, Any], tracks: Dict[str, Any]):
        """
        Initialize post-processor with policy.

        Args:
            supabase: Supabase client
            policy: Policy configuration dict
            tracks: Dictionary of track metadata
        """
        self.supabase = supabase
        self.tracks = tracks
        self.policy_json = policy['policy_json']
        self.retrieval_depth_k = self.policy_json['retrieval_depth_k']
        self.final_k = self.policy_json['final_k']
        self.max_per_artist = self.policy_json['max_per_artist']
        self.exclude_seed_artist = self.policy_json['exclude_seed_artist']
        self.policy_version = policy['policy_version']

    def process_query_system(
        self,
        query_id: str,
        system_id: str
    ) -> Tuple[List[str], Dict[str, int], int]:
        """
        Process a (query, system) pair to produce final list.

        Returns:
            (final_order, filter_counts, depth_scanned)
            - final_order: List of track_ids in final order
            - filter_counts: Dict of filter statistics
            - depth_scanned: How many candidates were examined
        """
        # Get query info
        query_result = self.supabase.table('queries').select('*').eq('query_id', query_id).execute()
        if not query_result.data:
            raise ValueError(f"Query {query_id} not found")
        query = query_result.data[0]

        # Get candidates for this (system, query) sorted by rank
        candidates_result = self.supabase.table('candidates').select(
            'track_id, rank, score'
        ).eq('system_id', system_id).eq('query_id', query_id).order('rank').execute()

        if not candidates_result.data:
            logger.warning(f"No candidates found for {system_id}/{query_id}")
            return [], {'no_candidates': 1}, 0

        candidates = candidates_result.data

        # Get track metadata for all candidates from in-memory tracks dictionary
        track_ids = [c['track_id'] for c in candidates]
        track_metadata = db_utils.get_tracks_by_ids(self.tracks, track_ids)

        # Initialize filter tracking
        filter_counts = {
            'seed_track_excluded': 0,
            'seed_artist_excluded': 0,
            'duplicate_track_skipped': 0,
            'duplicate_artist_skipped': 0,
            'insufficient_results': 0
        }

        # Get seed artist for song queries
        seed_artist = None
        if query['task_type'] == constants.TASK_TYPE_SONG and self.exclude_seed_artist:
            seed_track = track_metadata.get(query['seed_track_id'])
            if seed_track and seed_track.get('artists'):
                # Use first artist name as seed artist (Spotify format: list of artist objects)
                seed_artist = seed_track['artists'][0]['name']
                logger.debug(f"Seed artist for exclusion: {seed_artist}")

        # Apply filters
        final_list = []
        seen_track_ids: Set[str] = set()
        artist_counts: Dict[str, int] = {}
        depth_scanned = 0

        for candidate in candidates:
            track_id = candidate['track_id']
            depth_scanned += 1

            # Check if we've reached final_k
            if len(final_list) >= self.final_k:
                break

            # Get track metadata
            track = track_metadata.get(track_id)
            if not track:
                logger.warning(f"Track {track_id} not found in database")
                continue

            # Filter 1: Exclude query song itself (always)
            if track_id == query.get('seed_track_id'):
                filter_counts['seed_track_excluded'] += 1
                logger.debug(f"Excluded seed track: {track_id}")
                continue

            # Filter 2: Exclude seed artist (song queries only, if enabled)
            if seed_artist and track.get('artists'):
                # Check if any artist matches seed artist (Spotify format: list of artist objects)
                artist_names = [artist['name'] for artist in track['artists']]
                if seed_artist in artist_names:
                    filter_counts['seed_artist_excluded'] += 1
                    logger.debug(f"Excluded seed artist track: {track_id} by {artist_names}")
                    continue

            # Filter 3: Deduplicate by track_id
            if track_id in seen_track_ids:
                filter_counts['duplicate_track_skipped'] += 1
                continue

            # Filter 4: 1-per-artist cap
            if track.get('artists'):
                # Use first artist name (Spotify format: list of artist objects)
                primary_artist = track['artists'][0]['name']
                artist_count = artist_counts.get(primary_artist, 0)

                if artist_count >= self.max_per_artist:
                    filter_counts['duplicate_artist_skipped'] += 1
                    logger.debug(f"Skipped {track_id} - artist {primary_artist} cap reached")
                    continue

                # Accept this track
                artist_counts[primary_artist] = artist_count + 1

            # Add to final list
            final_list.append(track_id)
            seen_track_ids.add(track_id)

        # Check if we got enough results
        if len(final_list) < self.final_k:
            filter_counts['insufficient_results'] = self.final_k - len(final_list)
            logger.warning(
                f"Only got {len(final_list)}/{self.final_k} results for {system_id}/{query_id}"
            )

        logger.info(
            f"Processed {system_id}/{query_id}: {len(final_list)} tracks from {depth_scanned} scanned"
        )

        return final_list, filter_counts, depth_scanned

    def materialize_final_list(
        self,
        query_id: str,
        system_id: str
    ) -> None:
        """Process and insert final list into database."""
        final_order, filter_counts, depth_scanned = self.process_query_system(
            query_id, system_id
        )

        # Insert into final_lists table
        data = {
            'policy_version': self.policy_version,
            'system_id': system_id,
            'query_id': query_id,
            'final_order': final_order,
            'filter_counts': filter_counts,
            'depth_scanned': depth_scanned,
            'generated_at': datetime.now(timezone.utc).isoformat()
        }

        self.supabase.table('final_lists').upsert(data).execute()
        logger.info(f"Materialized final list for {system_id}/{query_id}")


def materialize_all_final_lists(supabase: Client, tracks: Dict[str, Any]) -> Tuple[int, List[str]]:
    """
    Materialize final lists for all (query, system) combinations under active policy.

    Args:
        supabase: Supabase client
        tracks: Dictionary of track metadata

    Returns:
        (count_materialized, errors)
    """
    # Get active policy
    policy = db_utils.get_active_policy(supabase)
    if not policy:
        return 0, [constants.ERROR_NO_ACTIVE_POLICY]

    # Get all queries and systems
    queries_result = supabase.table('queries').select('query_id').execute()
    systems_result = supabase.table('systems').select('system_id').execute()

    query_ids = [q['query_id'] for q in queries_result.data]
    system_ids = [s['system_id'] for s in systems_result.data]

    logger.info(f"Materializing final lists for {len(query_ids)} queries × {len(system_ids)} systems")

    # Create post-processor
    processor = PostProcessor(supabase, policy, tracks)

    # Materialize all combinations
    count = 0
    errors = []

    for query_id in query_ids:
        for system_id in system_ids:
            try:
                processor.materialize_final_list(query_id, system_id)
                count += 1
            except Exception as e:
                error_msg = f"Error materializing {system_id}/{query_id}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)

    return count, errors


def create_pairs_from_systems(supabase: Client, system_ids: List[str]) -> int:
    """
    Create all pairwise comparisons (round-robin) from system IDs.

    Returns:
        Number of pairs created
    """
    pairs_created = 0

    for i, system_a in enumerate(system_ids):
        for system_b in system_ids[i + 1:]:
            pair_id = f"{system_a}_vs_{system_b}"
            data = {
                'pair_id': pair_id,
                'left_system_id': system_a,
                'right_system_id': system_b
            }

            try:
                supabase.table('pairs').upsert(data).execute()
                pairs_created += 1
                logger.info(f"Created pair: {pair_id}")
            except Exception as e:
                logger.error(f"Error creating pair {pair_id}: {e}")

    return pairs_created


def create_tasks_from_pairs(
    supabase: Client,
    target_judgments: int = constants.DEFAULT_TARGET_JUDGMENTS
) -> int:
    """
    Create tasks for all (query, pair) combinations.

    Returns:
        Number of tasks created
    """
    # Get all queries and pairs
    queries_result = supabase.table('queries').select('query_id, task_type').execute()
    pairs_result = supabase.table('pairs').select('pair_id').execute()

    tasks_created = 0

    for query in queries_result.data:
        for pair in pairs_result.data:
            data = {
                'query_id': query['query_id'],
                'pair_id': pair['pair_id'],
                'target_judgments': target_judgments,
                'is_practice': False  # Can be updated separately for practice items
            }

            try:
                # Use upsert to handle re-materialization without errors
                supabase.table('tasks').upsert(data).execute()
                tasks_created += 1
            except Exception as e:
                logger.error(f"Error creating task for {query['query_id']}/{pair['pair_id']}: {e}")

    logger.info(f"Created {tasks_created} tasks")
    return tasks_created
