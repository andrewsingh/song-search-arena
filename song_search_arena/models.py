"""
Pydantic models for Song Search Arena data validation
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional

try:
    from . import constants
except ImportError:
    import constants


# ===== Upload Schemas =====

class EvalQuery(BaseModel):
    """Query for evaluation (text or song)."""
    id: str = Field(..., description="Query ID (hash for text, track_id for song)")
    type: str = Field(..., description="Query type: 'text' or 'song'")
    text: Optional[str] = Field(None, description="Query text for text-to-song")
    track_id: Optional[str] = Field(None, description="Seed track ID for song-to-song")
    intents: Optional[List[str]] = Field(default_factory=list, description="Query intents")
    genres: Optional[List[str]] = Field(default_factory=list, description="Query genres")
    era: Optional[str] = Field(None, description="Musical era")
    extras: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

    @field_validator('type')
    @classmethod
    def validate_type(cls, v):
        if v not in constants.VALID_TASK_TYPES:
            raise ValueError(constants.ERROR_INVALID_QUERY_TYPE)
        return v

    @field_validator('text')
    @classmethod
    def validate_text_query(cls, v, info):
        if info.data.get('type') == constants.TASK_TYPE_TEXT and not v:
            raise ValueError("text is required for text queries")
        return v

    @field_validator('track_id')
    @classmethod
    def validate_song_query(cls, v, info):
        if info.data.get('type') == constants.TASK_TYPE_SONG and not v:
            raise ValueError(constants.ERROR_MISSING_TRACK_ID)
        return v


class Candidate(BaseModel):
    """Single candidate result from a system."""
    track_id: str = Field(..., description="Spotify track ID")
    score: float = Field(..., description="Similarity score from system")
    rank: int = Field(..., description="Rank in system's output (1-based)")
    extras: Optional[Dict[str, Any]] = Field(None, description="Per-candidate metadata")

    @field_validator('rank')
    @classmethod
    def validate_rank(cls, v):
        if v < 1:
            raise ValueError("rank must be >= 1")
        return v


class EvalResponse(BaseModel):
    """System response for a single query."""
    system_id: str = Field(..., description="System identifier")
    config: Optional[Dict[str, Any]] = Field(None, description="System configuration")
    query_id: str = Field(..., description="Query identifier")
    dataset_id: str = Field(..., description="Dataset/batch identifier")
    extras: Optional[Dict[str, Any]] = Field(None, description="Run-level metadata")
    candidates: List[Candidate] = Field(..., description="Ranked candidate list")

    @field_validator('candidates')
    @classmethod
    def validate_candidates_length(cls, v):
        if len(v) < constants.DEFAULT_RETRIEVAL_DEPTH_K:
            raise ValueError(constants.ERROR_INSUFFICIENT_CANDIDATES)
        return v


class Policy(BaseModel):
    """Post-processing policy configuration."""
    version: str = Field(..., description="Policy version identifier")
    retrieval_depth_k: int = Field(
        constants.DEFAULT_RETRIEVAL_DEPTH_K,
        description="Depth to scan in raw results"
    )
    final_k: int = Field(
        constants.DEFAULT_FINAL_K,
        description="Final list size after filtering"
    )
    max_per_artist: int = Field(
        constants.DEFAULT_MAX_PER_ARTIST,
        description="Maximum tracks per artist"
    )
    exclude_seed_artist: bool = Field(
        constants.DEFAULT_EXCLUDE_SEED_ARTIST,
        description="Exclude seed artist in song-to-song"
    )
    task_block_size: int = Field(
        constants.DEFAULT_TASK_BLOCK_SIZE,
        description="Number of tasks per block before switching task type"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return {
            'version': self.version,
            'retrieval_depth_k': self.retrieval_depth_k,
            'final_k': self.final_k,
            'max_per_artist': self.max_per_artist,
            'exclude_seed_artist': self.exclude_seed_artist,
            'task_block_size': self.task_block_size
        }


# ===== Judgment Schemas =====

class JudgmentSubmission(BaseModel):
    """Judgment submission from rater."""
    task_id: str = Field(..., description="Task UUID")
    choice: str = Field(..., description="Rater's choice: left, right, or tie")
    confidence: int = Field(..., description="Confidence level 1-3")
    presented_at: str = Field(..., description="ISO timestamp when task was presented")

    @field_validator('choice')
    @classmethod
    def validate_choice(cls, v):
        if v not in constants.VALID_CHOICES:
            raise ValueError(constants.ERROR_INVALID_CHOICE)
        return v

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v):
        if v < constants.MIN_CONFIDENCE or v > constants.MAX_CONFIDENCE:
            raise ValueError(constants.ERROR_INVALID_CONFIDENCE)
        return v


# ===== Task/Response Schemas =====

class TaskResponse(BaseModel):
    """Task data sent to rater."""
    task_id: str
    query_id: str
    task_type: str  # 'text' or 'song'
    query_text: Optional[str] = None
    seed_track: Optional[Dict[str, Any]] = None  # Track metadata for song queries
    left_system_id: str
    right_system_id: str
    left_list: List[Dict[str, Any]]  # List of track metadata
    right_list: List[Dict[str, Any]]  # List of track metadata
    rng_seed: str
    block_type: str  # 'text' or 'song' for UI display
    is_practice: bool = False


class ProgressStats(BaseModel):
    """Progress statistics for rater."""
    total_tasks: int
    completed_tasks: int
    text_tasks_completed: int
    song_tasks_completed: int
    text_tasks_total: int
    song_tasks_total: int


# ===== Admin Schemas =====

class UploadResult(BaseModel):
    """Result of upload operation."""
    success: bool
    message: str
    count: Optional[int] = None
    errors: Optional[List[str]] = None


class MaterializationResult(BaseModel):
    """Result of materialization operation."""
    success: bool
    message: str
    final_lists_created: int = 0
    pairs_created: int = 0
    tasks_created: int = 0
    errors: Optional[List[str]] = None


class AdminStats(BaseModel):
    """Admin dashboard statistics."""
    total_queries: int
    total_systems: int
    total_pairs: int
    total_tasks: int
    completed_tasks: int
    total_judgments: int
    unique_raters: int
    active_policy: Optional[Dict[str, Any]] = None
