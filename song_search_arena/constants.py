"""
Constants and configuration for Song Search Arena
"""
import os

# Default Policy Configuration
DEFAULT_RETRIEVAL_DEPTH_K = int(os.environ.get('RETRIEVAL_DEPTH_K', 50))
DEFAULT_FINAL_K = int(os.environ.get('FINAL_K', 5))
DEFAULT_MAX_PER_ARTIST = 1
DEFAULT_EXCLUDE_SEED_ARTIST = os.environ.get('EXCLUDE_SEED_ARTIST', 'true').lower() == 'true'
DEFAULT_POLICY_VERSION = 'discovery-v1'

# Task Types
TASK_TYPE_TEXT = 'text'
TASK_TYPE_SONG = 'song'
VALID_TASK_TYPES = [TASK_TYPE_TEXT, TASK_TYPE_SONG]

# Judgment Choices
CHOICE_LEFT = 'left'
CHOICE_RIGHT = 'right'
CHOICE_TIE = 'tie'
VALID_CHOICES = [CHOICE_LEFT, CHOICE_RIGHT, CHOICE_TIE]

# Confidence Levels
MIN_CONFIDENCE = 1
MAX_CONFIDENCE = 3

# Spotify Top Items
SPOTIFY_API_LIMIT_PER_CALL = 50  # Spotify API limit per request

# Spotify Top Items Collection Limits (configurable)
SPOTIFY_TOP_TRACKS_LONG_TERM = 1000
SPOTIFY_TOP_TRACKS_MEDIUM_TERM = 500
SPOTIFY_TOP_TRACKS_SHORT_TERM = 200
SPOTIFY_TOP_ARTISTS_LONG_TERM = 300
SPOTIFY_TOP_ARTISTS_MEDIUM_TERM = 200
SPOTIFY_TOP_ARTISTS_SHORT_TERM = 100

SPOTIFY_TIME_RANGES = ['short_term', 'medium_term', 'long_term']

# Map time ranges to limits for each kind
SPOTIFY_LIMITS = {
    'tracks': {
        'long_term': SPOTIFY_TOP_TRACKS_LONG_TERM,
        'medium_term': SPOTIFY_TOP_TRACKS_MEDIUM_TERM,
        'short_term': SPOTIFY_TOP_TRACKS_SHORT_TERM
    },
    'artists': {
        'long_term': SPOTIFY_TOP_ARTISTS_LONG_TERM,
        'medium_term': SPOTIFY_TOP_ARTISTS_MEDIUM_TERM,
        'short_term': SPOTIFY_TOP_ARTISTS_SHORT_TERM
    }
}

# Rater Caps
DEFAULT_SOFT_CAP = 1000  # Soft limit per rater (high default, overridden per rater)
DEFAULT_TOTAL_CAP = None  # Will be set dynamically based on # queries × C(S,2) pairs

# Target Judgments per Task
DEFAULT_TARGET_JUDGMENTS = 3

# Practice Items
NUM_PRACTICE_ITEMS_PER_BLOCK = 2

# Export
EXPORT_BUCKET_NAME = 'exports'
EXPORT_PATH_PREFIX = 'exports/'

# Session
SESSION_TIMEOUT_MINUTES = 60

# Error Messages
ERROR_INVALID_PASSWORD = 'Invalid password'
ERROR_NOT_AUTHENTICATED = 'Not authenticated with Spotify'
ERROR_INVALID_QUERY_TYPE = f'Invalid query type. Must be one of: {VALID_TASK_TYPES}'
ERROR_INVALID_CHOICE = f'Invalid choice. Must be one of: {VALID_CHOICES}'
ERROR_INVALID_CONFIDENCE = f'Confidence must be between {MIN_CONFIDENCE} and {MAX_CONFIDENCE}'
ERROR_MISSING_QUERY_ID = 'Missing query_id'
ERROR_MISSING_TRACK_ID = 'Missing track_id for song queries'
ERROR_INSUFFICIENT_CANDIDATES = f'Insufficient candidates. Need at least {DEFAULT_RETRIEVAL_DEPTH_K}'
ERROR_TRACK_NOT_FOUND = 'Track not found in database'
ERROR_QUERY_NOT_FOUND = 'Query not found in database'
ERROR_NO_ACTIVE_POLICY = 'No active policy found'
ERROR_NO_TASKS_AVAILABLE = 'No tasks available'
ERROR_TASK_ALREADY_COMPLETED = 'Task already completed by this rater'
ERROR_RATER_CAP_REACHED = 'Rater has reached judgment cap'

# Success Messages
SUCCESS_UPLOAD_QUERIES = 'Queries uploaded successfully'
SUCCESS_UPLOAD_CANDIDATES = 'Candidates uploaded successfully'
SUCCESS_SET_POLICY = 'Policy set successfully'
SUCCESS_MATERIALIZATION = 'Materialization completed successfully'
SUCCESS_JUDGMENT_SUBMITTED = 'Judgment submitted successfully'
