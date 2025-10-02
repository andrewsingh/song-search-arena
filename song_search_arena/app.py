#!/usr/bin/env python3
"""
Song Search Arena - A/B Testing Platform for Music Retrieval Systems
Blinded pairwise list-preference evaluations with centralized post-processing.
"""
import os
import json
import logging
import uuid
import threading
from datetime import datetime, timezone
from functools import wraps
from typing import Optional, Dict, List, Any

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_session import Session
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from supabase import create_client, Client

try:
    from . import constants, models, db_utils, post_processing, scheduler, export
except ImportError:
    import constants, models, db_utils, post_processing, scheduler, export

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_FILE_THRESHOLD'] = 500
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', str(uuid.uuid4()))
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB upload limit
Session(app)

# Environment variables
EVAL_PASSWORD = os.environ.get('EVAL_PASSWORD')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')

# Validate required environment variables
if not EVAL_PASSWORD or not ADMIN_PASSWORD:
    logger.warning("EVAL_PASSWORD or ADMIN_PASSWORD not set. Authentication will be disabled.")

if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    logger.error("Spotify credentials not provided. App cannot function.")
    raise ValueError("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET are required")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    logger.error("Supabase credentials not provided. App cannot function.")
    raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
logger.info("Supabase client initialized")

# Global tracks dictionary (loaded from JSON file)
TRACKS: Dict[str, Any] = {}


# ===== Helper Functions =====

def generate_csrf_token():
    """Generate CSRF token for the session."""
    if 'csrf_token' not in session:
        session['csrf_token'] = str(uuid.uuid4())
    return session['csrf_token']

def validate_csrf_token(token: str) -> bool:
    """Validate CSRF token."""
    return token and session.get('csrf_token') == token

# Make CSRF token available in all templates
@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf_token)

def get_spotify_oauth():
    """Get Spotify OAuth object with dynamic redirect URI."""
    host_without_port = request.host.split(':')[0]
    is_local = host_without_port in ['127.0.0.1', 'localhost']
    is_production = os.getenv('RAILWAY_ENVIRONMENT') or not is_local

    if is_production:
        redirect_uri = f"https://{request.host}/callback"
    else:
        redirect_uri = f"http://{request.host}/callback"

    logger.info(f"Using OAuth redirect URI: {redirect_uri}")

    scope = "user-read-email user-top-read streaming user-read-playback-state user-modify-playback-state"

    return SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=redirect_uri,
        scope=scope,
        show_dialog=False
    )


def get_spotify_client(token_info: dict) -> Optional[spotipy.Spotify]:
    """Get authenticated Spotify client from token info."""
    try:
        return spotipy.Spotify(auth=token_info['access_token'])
    except Exception as e:
        logger.error(f"Failed to create Spotify client: {e}")
        return None


def get_spotify_client_from_refresh_token(refresh_token: str) -> Optional[spotipy.Spotify]:
    """
    Create a Spotify client from a stored refresh token.
    This allows us to make API calls outside of the user's active session.
    """
    try:
        sp_oauth = SpotifyOAuth(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
            redirect_uri="http://localhost:5000/callback",  # Not used for refresh
            scope="user-read-email user-top-read streaming user-read-playback-state user-modify-playback-state"
        )

        # Get new access token using refresh token
        token_info = sp_oauth.refresh_access_token(refresh_token)

        return spotipy.Spotify(auth=token_info['access_token'])
    except Exception as e:
        logger.error(f"Failed to create Spotify client from refresh token: {e}")
        return None


# ===== Decorators =====

def eval_password_required(f):
    """Decorator to require eval password."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not EVAL_PASSWORD:
            # No password configured, allow access
            return f(*args, **kwargs)

        if session.get('eval_authenticated'):
            return f(*args, **kwargs)

        return redirect(url_for('eval_password_gate'))
    return decorated_function


def admin_password_required(f):
    """Decorator to require admin password."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not ADMIN_PASSWORD:
            # No password configured, allow access
            return f(*args, **kwargs)

        if session.get('admin_authenticated'):
            return f(*args, **kwargs)

        return redirect(url_for('admin_password_gate'))
    return decorated_function


def spotify_auth_required(f):
    """Decorator to require Spotify authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'token_info' not in session:
            return redirect(url_for('login'))

        # Check if token needs refresh
        token_info = session['token_info']
        sp_oauth = get_spotify_oauth()

        if sp_oauth.is_token_expired(token_info):
            try:
                token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
                session['token_info'] = token_info
            except Exception as e:
                logger.error(f"Token refresh failed: {e}")
                session.clear()
                return redirect(url_for('login'))

        return f(*args, **kwargs)
    return decorated_function


# ===== Password Gate Routes =====

@app.route('/eval/password', methods=['GET', 'POST'])
def eval_password_gate():
    """Eval password gate page."""
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == EVAL_PASSWORD:
            session['eval_authenticated'] = True
            return redirect(url_for('index'))
        else:
            return render_template('password_gate.html',
                                   error=constants.ERROR_INVALID_PASSWORD,
                                   gate_type='eval')

    return render_template('password_gate.html', gate_type='eval')


@app.route('/admin/password', methods=['GET', 'POST'])
def admin_password_gate():
    """Admin password gate page."""
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['admin_authenticated'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('password_gate.html',
                                   error=constants.ERROR_INVALID_PASSWORD,
                                   gate_type='admin')

    return render_template('password_gate.html', gate_type='admin')


# ===== Spotify OAuth Routes =====

@app.route('/login')
@eval_password_required
def login():
    """Spotify login."""
    sp_oauth = get_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)


@app.route('/callback')
def callback():
    """Spotify OAuth callback."""
    try:
        sp_oauth = get_spotify_oauth()
        code = request.args.get('code')
        token_info = sp_oauth.get_access_token(code)
        session['token_info'] = token_info

        # Get Spotify user profile
        sp = get_spotify_client(token_info)
        if not sp:
            raise Exception("Failed to create Spotify client")

        user_profile = sp.current_user()
        rater_id = user_profile['id']
        session['rater_id'] = rater_id

        # Check if rater exists in database
        result = supabase.table('raters').select('*').eq('rater_id', rater_id).execute()

        is_new_rater = not result.data

        if is_new_rater:
            # New rater - insert into database with refresh token
            rater_data = {
                'rater_id': rater_id,
                'display_name': user_profile.get('display_name'),
                'email': user_profile.get('email'),
                'country': user_profile.get('country'),
                'spotify_refresh_token': token_info.get('refresh_token')
            }
            supabase.table('raters').insert(rater_data).execute()
            logger.info(f"New rater registered: {rater_id}")

            # Spawn background thread to collect Spotify data (non-blocking)
            thread = threading.Thread(
                target=fetch_spotify_data_background,
                args=(rater_id,),
                daemon=True
            )
            thread.start()
            logger.info(f"Started background thread to collect Spotify data for {rater_id}")
        else:
            # Update existing rater's refresh token (in case it changed)
            supabase.table('raters').update({
                'spotify_refresh_token': token_info.get('refresh_token')
            }).eq('rater_id', rater_id).execute()
            logger.info(f"Existing rater logged in: {rater_id}")

        # Create new session
        session_data = {
            'rater_id': rater_id,
            'started_at': datetime.now(timezone.utc).isoformat(),
            'last_seen_at': datetime.now(timezone.utc).isoformat()
        }
        session_result = supabase.table('sessions').insert(session_data).execute()
        session['session_id'] = session_result.data[0]['session_id']

        return redirect(url_for('index'))

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return render_template('error.html', error=f"Authentication failed: {str(e)}"), 500


@app.route('/logout')
def logout():
    """Logout and clear session."""
    session.clear()
    return redirect(url_for('eval_password_gate'))


def clean_track_item(item: dict) -> dict:
    """
    Remove 'available_markets' from track items to reduce storage size.
    This field appears in both item['available_markets'] and item['album']['available_markets'].
    """
    item = item.copy()

    # Remove top-level available_markets
    item.pop('available_markets', None)

    # Remove album available_markets
    if 'album' in item and isinstance(item['album'], dict):
        item['album'].pop('available_markets', None)

    return item


def get_rater_top_items(rater_id: str, kind: str, time_range: str) -> list:
    """
    Retrieve and merge paginated Spotify top items for a rater.

    Args:
        rater_id: Rater ID
        kind: 'artists' or 'tracks'
        time_range: 'short_term', 'medium_term', or 'long_term'

    Returns:
        List of items merged from all paginated responses, sorted by batch_offset
    """
    try:
        result = supabase.table('rater_spotify_top').select('payload, batch_offset').eq(
            'rater_id', rater_id
        ).eq('kind', kind).eq('time_range', time_range).order('batch_offset').execute()

        if not result.data:
            return []

        # Merge all items from paginated responses
        all_items = []
        for row in result.data:
            payload = row.get('payload', {})
            items = payload.get('items', [])
            all_items.extend(items)

        return all_items

    except Exception as e:
        logger.error(f"Failed to retrieve {kind} for rater {rater_id} ({time_range}): {e}")
        return []


def fetch_and_store_spotify_top_items(sp: spotipy.Spotify, rater_id: str):
    """
    Fetch and store user's top artists and tracks for all time ranges.
    Makes paginated API calls to retrieve more than 50 items per time range.
    Collects all data in memory, then batch inserts to database at the end.
    """
    logger.info(f"Starting Spotify top items collection for rater {rater_id}")
    total_items_collected = {'artists': 0, 'tracks': 0}
    all_rows = []  # Collect all rows for batch insert
    captured_at = datetime.now(timezone.utc).isoformat()

    for time_range in constants.SPOTIFY_TIME_RANGES:
        # Fetch top artists
        kind = 'artists'
        target_limit = constants.SPOTIFY_LIMITS[kind][time_range]
        num_calls = (target_limit + constants.SPOTIFY_API_LIMIT_PER_CALL - 1) // constants.SPOTIFY_API_LIMIT_PER_CALL

        logger.info(f"Fetching top {kind} for {time_range}: target={target_limit}, calls={num_calls}")

        for call_num in range(num_calls):
            offset = call_num * constants.SPOTIFY_API_LIMIT_PER_CALL

            try:
                response = sp.current_user_top_artists(
                    limit=constants.SPOTIFY_API_LIMIT_PER_CALL,
                    offset=offset,
                    time_range=time_range
                )

                items_returned = len(response.get('items', []))

                if items_returned == 0:
                    logger.info(f"  No more {kind} available at offset {offset}, stopping pagination")
                    break

                # Add to batch for later insertion
                all_rows.append({
                    'rater_id': rater_id,
                    'kind': kind,
                    'time_range': time_range,
                    'batch_offset': offset,
                    'payload': response,
                    'captured_at': captured_at
                })

                total_items_collected[kind] += items_returned
                logger.info(f"  Fetched {items_returned} {kind} at offset {offset} (call {call_num + 1}/{num_calls})")

            except Exception as e:
                logger.error(f"  Failed to fetch {kind} at offset {offset} ({time_range}): {e}")
                # Continue with next batch despite failure

        # Fetch top tracks
        kind = 'tracks'
        target_limit = constants.SPOTIFY_LIMITS[kind][time_range]
        num_calls = (target_limit + constants.SPOTIFY_API_LIMIT_PER_CALL - 1) // constants.SPOTIFY_API_LIMIT_PER_CALL

        logger.info(f"Fetching top {kind} for {time_range}: target={target_limit}, calls={num_calls}")

        for call_num in range(num_calls):
            offset = call_num * constants.SPOTIFY_API_LIMIT_PER_CALL

            try:
                response = sp.current_user_top_tracks(
                    limit=constants.SPOTIFY_API_LIMIT_PER_CALL,
                    offset=offset,
                    time_range=time_range
                )

                items_returned = len(response.get('items', []))

                if items_returned == 0:
                    logger.info(f"  No more {kind} available at offset {offset}, stopping pagination")
                    break

                # Clean track items by removing available_markets
                if 'items' in response:
                    response['items'] = [clean_track_item(item) for item in response['items']]

                # Add to batch for later insertion
                all_rows.append({
                    'rater_id': rater_id,
                    'kind': kind,
                    'time_range': time_range,
                    'batch_offset': offset,
                    'payload': response,
                    'captured_at': captured_at
                })

                total_items_collected[kind] += items_returned
                logger.info(f"  Fetched {items_returned} {kind} at offset {offset} (call {call_num + 1}/{num_calls})")

            except Exception as e:
                logger.error(f"  Failed to fetch {kind} at offset {offset} ({time_range}): {e}")
                # Continue with next batch despite failure

    # Batch insert all rows at once
    if all_rows:
        logger.info(f"Inserting {len(all_rows)} rows to database in single batch...")
        try:
            supabase.table('rater_spotify_top').upsert(all_rows).execute()
            logger.info(f"Successfully stored all Spotify data for {rater_id}")
        except Exception as e:
            logger.error(f"Failed to batch insert Spotify data for {rater_id}: {e}")
            raise

    logger.info(f"Completed Spotify top items collection for {rater_id}: "
                f"artists={total_items_collected['artists']}, tracks={total_items_collected['tracks']}")


def fetch_spotify_data_background(rater_id: str):
    """
    Background thread function to collect Spotify top items data.
    Runs asynchronously to avoid blocking the user's page load.
    """
    logger.info(f"[Background] Starting Spotify data collection for rater {rater_id}")

    try:
        # Get rater's refresh token from database
        result = supabase.table('raters').select('spotify_refresh_token').eq('rater_id', rater_id).execute()

        if not result.data or not result.data[0].get('spotify_refresh_token'):
            logger.error(f"[Background] No refresh token found for rater {rater_id}")
            return

        refresh_token = result.data[0]['spotify_refresh_token']

        # Create Spotify client from refresh token
        sp = get_spotify_client_from_refresh_token(refresh_token)

        if not sp:
            logger.error(f"[Background] Failed to create Spotify client for rater {rater_id}")
            return

        # Fetch and store top items
        fetch_and_store_spotify_top_items(sp, rater_id)

        logger.info(f"[Background] Successfully completed Spotify data collection for rater {rater_id}")

    except Exception as e:
        logger.error(f"[Background] Error collecting Spotify data for rater {rater_id}: {e}")


# ===== Main Routes =====

@app.route('/')
@eval_password_required
@spotify_auth_required
def index():
    """Main evaluation page."""
    rater_id = session.get('rater_id')
    return render_template('eval.html', rater_id=rater_id)


@app.route('/admin')
@admin_password_required
def admin_dashboard():
    """Admin dashboard."""
    return render_template('admin.html')


# ===== API Routes =====

@app.route('/api/token', methods=['GET'])
@spotify_auth_required
def get_token():
    """Get Spotify access token for client-side player."""
    token_info = session.get('token_info')
    return jsonify({'access_token': token_info['access_token']})


@app.route('/api/get_task', methods=['GET'])
@eval_password_required
@spotify_auth_required
def get_task():
    """Get next task for rater."""
    try:
        rater_id = session.get('rater_id')
        if not rater_id:
            return jsonify({'error': constants.ERROR_NOT_AUTHENTICATED}), 401

        # Get next task from scheduler
        task_data = scheduler.get_next_task(supabase, rater_id, TRACKS)

        if not task_data:
            return jsonify({
                'task': None,
                'message': constants.ERROR_NO_TASKS_AVAILABLE
            }), 200

        # Store task data in session for judgment submission
        session['current_task'] = {
            'task_id': task_data['task_id'],
            'left_system_id': task_data['left_system_id'],
            'right_system_id': task_data['right_system_id'],
            'left_list': task_data['left_list'],
            'right_list': task_data['right_list'],
            'rng_seed': task_data['rng_seed'],
            'presented_at': datetime.now(timezone.utc).isoformat()
        }

        return jsonify({'task': task_data}), 200

    except Exception as e:
        logger.error(f"Error getting task: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/submit_judgment', methods=['POST'])
@eval_password_required
@spotify_auth_required
def submit_judgment_route():
    """Submit judgment for current task."""
    try:
        rater_id = session.get('rater_id')
        session_id = session.get('session_id')

        if not rater_id or not session_id:
            return jsonify({'error': constants.ERROR_NOT_AUTHENTICATED}), 401

        # Get current task from session
        current_task = session.get('current_task')
        if not current_task:
            return jsonify({'error': 'No active task'}), 400

        # Get judgment data from request
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No judgment data provided'}), 400

        # Validate CSRF token
        csrf_token = data.get('csrf_token')
        if not validate_csrf_token(csrf_token):
            return jsonify({'error': 'Invalid CSRF token'}), 403

        choice = data.get('choice')
        confidence = data.get('confidence')

        if not choice or confidence is None:
            return jsonify({'error': 'Missing choice or confidence'}), 400

        # Validate with Pydantic
        try:
            judgment = models.JudgmentSubmission(
                task_id=current_task['task_id'],
                choice=choice,
                confidence=confidence,
                presented_at=current_task['presented_at']
            )
        except Exception as e:
            return jsonify({'error': f'Invalid judgment data: {str(e)}'}), 400

        # Submit judgment
        judgment_id = scheduler.submit_judgment(
            supabase=supabase,
            rater_id=rater_id,
            session_id=session_id,
            task_id=judgment.task_id,
            choice=judgment.choice,
            confidence=judgment.confidence,
            presented_at=judgment.presented_at,
            task_data=current_task
        )

        # Clear current task from session
        session.pop('current_task', None)

        return jsonify({
            'success': True,
            'message': constants.SUCCESS_JUDGMENT_SUBMITTED,
            'judgment_id': judgment_id
        }), 200

    except Exception as e:
        logger.error(f"Error submitting judgment: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/progress', methods=['GET'])
@eval_password_required
@spotify_auth_required
def get_progress():
    """Get rater's progress."""
    try:
        rater_id = session.get('rater_id')
        if not rater_id:
            return jsonify({'error': constants.ERROR_NOT_AUTHENTICATED}), 401

        progress = scheduler.get_rater_progress(supabase, rater_id)
        return jsonify(progress), 200

    except Exception as e:
        logger.error(f"Error getting progress: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/admin/upload/queries', methods=['POST'])
@admin_password_required
def upload_queries():
    """Upload queries from JSON array."""
    try:
        data = request.get_json()

        if not data or not isinstance(data, list):
            return jsonify({'error': 'Expected JSON array of queries'}), 400

        # Validate with Pydantic
        queries = []
        validation_errors = []

        for i, item in enumerate(data):
            try:
                query = models.EvalQuery(**item)
                queries.append(query)
            except Exception as e:
                validation_errors.append(f"Query {i}: {str(e)}")

        if validation_errors:
            return jsonify({
                'success': False,
                'message': 'Validation errors',
                'errors': validation_errors
            }), 400

        # Insert queries
        count, errors = db_utils.insert_queries(supabase, queries)

        if errors:
            return jsonify({
                'success': True,
                'message': f'Uploaded {count} queries with {len(errors)} errors',
                'count': count,
                'errors': errors
            }), 200

        return jsonify({
            'success': True,
            'message': constants.SUCCESS_UPLOAD_QUERIES,
            'count': count
        }), 200

    except Exception as e:
        logger.error(f"Error uploading queries: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/admin/upload/responses', methods=['POST'])
@admin_password_required
def upload_responses():
    """Upload system responses (contains candidates)."""
    try:
        data = request.get_json()

        if not data or not isinstance(data, list):
            return jsonify({'error': 'Expected JSON array of responses'}), 400

        # Validate with Pydantic
        responses = []
        validation_errors = []

        for i, item in enumerate(data):
            try:
                response = models.EvalResponse(**item)
                responses.append(response)
            except Exception as e:
                validation_errors.append(f"Response {i} ({item.get('system_id', '?')}/{item.get('query_id', '?')}): {str(e)}")

        if validation_errors:
            return jsonify({
                'success': False,
                'message': 'Validation errors',
                'errors': validation_errors
            }), 400

        # Insert candidates (also upserts systems)
        count, errors = db_utils.insert_candidates(supabase, responses, TRACKS)

        if errors:
            return jsonify({
                'success': True,
                'message': f'Uploaded {count} candidates with {len(errors)} errors',
                'count': count,
                'errors': errors
            }), 200

        return jsonify({
            'success': True,
            'message': constants.SUCCESS_UPLOAD_CANDIDATES,
            'count': count
        }), 200

    except Exception as e:
        logger.error(f"Error uploading responses: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/admin/policy/set', methods=['POST'])
@admin_password_required
def set_policy():
    """Set active policy."""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Policy data required'}), 400

        # Validate with Pydantic
        try:
            policy = models.Policy(**data)
        except Exception as e:
            return jsonify({'error': f'Invalid policy: {str(e)}'}), 400

        # Set as active policy
        db_utils.set_active_policy(supabase, policy)

        return jsonify({
            'success': True,
            'message': constants.SUCCESS_SET_POLICY,
            'policy': policy.to_dict()
        }), 200

    except Exception as e:
        logger.error(f"Error setting policy: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/admin/materialize', methods=['POST'])
@admin_password_required
def materialize():
    """Materialize final lists, pairs, and tasks."""
    try:
        # Get request parameters
        data = request.get_json() or {}
        target_judgments = data.get('target_judgments', constants.DEFAULT_TARGET_JUDGMENTS)

        # Step 1: Materialize final lists
        logger.info("Materializing final lists...")
        lists_count, list_errors = post_processing.materialize_all_final_lists(supabase, TRACKS)

        # Step 2: Create pairs from all systems
        logger.info("Creating pairs...")
        systems_result = supabase.table('systems').select('system_id').execute()
        system_ids = [s['system_id'] for s in systems_result.data]

        if not system_ids:
            logger.warning("No systems found for pair creation")
            return jsonify({'error': 'No systems found. Upload system responses first.'}), 400

        if len(system_ids) < 2:
            logger.warning("Need at least 2 systems for pairwise comparison")
            return jsonify({'error': 'Need at least 2 systems for pairwise comparison.'}), 400

        pairs_count = post_processing.create_pairs_from_systems(supabase, system_ids)

        # Step 3: Create tasks
        logger.info("Creating tasks...")
        tasks_count = post_processing.create_tasks_from_pairs(supabase, target_judgments)

        # Update rater total_cap to total number of tasks
        total_tasks = len(supabase.table('tasks').select('task_id').execute().data)
        supabase.table('raters').update({'total_cap': total_tasks}).neq('rater_id', 'dummy').execute()

        all_errors = list_errors

        result = models.MaterializationResult(
            success=True,
            message=constants.SUCCESS_MATERIALIZATION,
            final_lists_created=lists_count,
            pairs_created=pairs_count,
            tasks_created=tasks_count,
            errors=all_errors if all_errors else None
        )

        return jsonify(result.model_dump()), 200

    except Exception as e:
        logger.error(f"Error during materialization: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/admin/stats', methods=['GET'])
@admin_password_required
def admin_stats():
    """Get admin statistics."""
    try:
        stats = db_utils.get_admin_stats(supabase)
        return jsonify(stats.model_dump()), 200
    except Exception as e:
        logger.error(f"Error getting admin stats: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/admin/progress', methods=['GET'])
@admin_password_required
def admin_progress():
    """Get progress grid for dashboard."""
    try:
        progress = db_utils.get_progress_grid(supabase)
        return jsonify({'progress': progress}), 200
    except Exception as e:
        logger.error(f"Error getting progress: {e}")
        return jsonify({'error': str(e)}), 500


# ===== Export Routes =====

@app.route('/admin/export/judgments', methods=['POST'])
@admin_password_required
def export_judgments():
    """Export judgments to CSV or JSON and upload to storage."""
    try:
        data = request.get_json() or {}
        format = data.get('format', 'csv')

        if format not in ['csv', 'json']:
            return jsonify({'error': 'Invalid format. Must be csv or json'}), 400

        result = export.export_and_upload(
            supabase,
            export_type='judgments',
            format=format,
            bucket_name=constants.EXPORT_BUCKET_NAME
        )

        logger.info(f"Exported judgments to {result['file_path']}")
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error exporting judgments: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/admin/export/final_lists', methods=['POST'])
@admin_password_required
def export_final_lists():
    """Export final lists to CSV or JSON and upload to storage."""
    try:
        data = request.get_json() or {}
        format = data.get('format', 'csv')
        policy_version = data.get('policy_version')

        if format not in ['csv', 'json']:
            return jsonify({'error': 'Invalid format. Must be csv or json'}), 400

        result = export.export_and_upload(
            supabase,
            export_type='final_lists',
            format=format,
            bucket_name=constants.EXPORT_BUCKET_NAME,
            policy_version=policy_version
        )

        logger.info(f"Exported final lists to {result['file_path']}")
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error exporting final lists: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/admin/export/task_progress', methods=['POST'])
@admin_password_required
def export_task_progress():
    """Export task progress to CSV and upload to storage."""
    try:
        result = export.export_and_upload(
            supabase,
            export_type='task_progress',
            format='csv',
            bucket_name=constants.EXPORT_BUCKET_NAME
        )

        logger.info(f"Exported task progress to {result['file_path']}")
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error exporting task progress: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/admin/export/rater_stats', methods=['POST'])
@admin_password_required
def export_rater_stats():
    """Export rater statistics to CSV and upload to storage."""
    try:
        result = export.export_and_upload(
            supabase,
            export_type='rater_stats',
            format='csv',
            bucket_name=constants.EXPORT_BUCKET_NAME
        )

        logger.info(f"Exported rater stats to {result['file_path']}")
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error exporting rater stats: {e}")
        return jsonify({'error': str(e)}), 500


def load_tracks_from_json(file_path: str) -> Dict[str, Any]:
    """
    Load track metadata from JSON file and build ID mapping.

    Expected format: List of track objects (Spotify track format)
    Builds a dict mapping track ID -> track object
    Handles both main track.id and track.linked_from.id as keys
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tracks_list = json.load(f)

        # Build mapping: track_id -> track_object
        tracks_map = {}
        for track in tracks_list:
            track_id = track.get('id')
            if not track_id:
                logger.warning(f"Track missing 'id' field: {track.get('name', 'unknown')}")
                continue

            # Add main ID
            tracks_map[track_id] = track

            # Add linked_from ID if it exists
            linked_from = track.get('linked_from', {})
            linked_id = linked_from.get('id')
            if linked_id and linked_id != track_id:
                tracks_map[linked_id] = track
                logger.debug(f"Added linked_from ID {linked_id} -> {track_id}")

        logger.info(f"Loaded {len(tracks_list)} tracks, built map with {len(tracks_map)} IDs from {file_path}")
        return tracks_map
    except Exception as e:
        logger.error(f"Failed to load tracks from {file_path}: {e}")
        raise


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Song Search Arena')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5000, help='Port to bind to')
    parser.add_argument('--tracks', required=True, help='Path to tracks JSON file')
    args = parser.parse_args()

    # Load tracks
    TRACKS = load_tracks_from_json(args.tracks)

    app.run(debug=args.debug, host=args.host, port=args.port)
