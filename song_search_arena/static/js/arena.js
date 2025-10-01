// Song Search Arena - Main JavaScript

class ArenaApp {
    constructor() {
        this.currentTask = null;
        this.selectedChoice = null;
        this.selectedConfidence = null;
        this.accessToken = null;
        this.spotifyPlayer = null;

        // DOM elements
        this.elements = {
            loadingState: document.getElementById('loading-state'),
            completionState: document.getElementById('completion-state'),
            taskContainer: document.getElementById('task-container'),
            queryTextDisplay: document.getElementById('query-text-display'),
            querySongDisplay: document.getElementById('query-song-display'),
            queryText: document.getElementById('query-text'),
            seedTrack: document.getElementById('seed-track'),
            leftList: document.getElementById('left-list'),
            rightList: document.getElementById('right-list'),
            confidenceSection: document.getElementById('confidence-section'),
            submitBtn: document.getElementById('submit-btn'),
            progressText: document.getElementById('progress-text'),
            nowPlaying: document.getElementById('now-playing'),
            playerPrev: document.getElementById('player-prev'),
            playerPlayPause: document.getElementById('player-play-pause'),
            playerNext: document.getElementById('player-next')
        };

        this.init();
    }

    async init() {
        // Set up event listeners
        this.setupEventListeners();

        // Get Spotify token
        await this.getSpotifyToken();

        // Initialize Spotify player (async - will complete in background)
        this.initPlayer();

        // Load progress
        await this.loadProgress();

        // Load first task
        await this.loadNextTask();
    }

    setupEventListeners() {
        // Choice buttons
        document.querySelectorAll('.choice-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleChoiceClick(e));
        });

        // Confidence buttons
        document.querySelectorAll('.confidence-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleConfidenceClick(e));
        });

        // Submit button
        this.elements.submitBtn.addEventListener('click', () => this.submitJudgment());

        // Player controls
        if (this.elements.playerPlayPause) {
            this.elements.playerPlayPause.addEventListener('click', () => this.togglePlayback());
        }
        if (this.elements.playerPrev) {
            this.elements.playerPrev.addEventListener('click', () => this.previousTrack());
        }
        if (this.elements.playerNext) {
            this.elements.playerNext.addEventListener('click', () => this.nextTrack());
        }
    }

    async getSpotifyToken() {
        try {
            const response = await fetch('/api/token');
            if (!response.ok) {
                throw new Error(`Failed to get token: ${response.status}`);
            }
            const data = await response.json();
            if (!data.access_token) {
                throw new Error('No access token in response');
            }
            this.accessToken = data.access_token;
        } catch (error) {
            console.error('Error getting Spotify token:', error);
            this.showError('Failed to authenticate with Spotify. Please refresh the page.');
        }
    }

    async initPlayer() {
        if (!this.accessToken) {
            console.error('Cannot initialize player: no access token');
            return;
        }

        try {
            // Create Spotify player instance
            this.spotifyPlayer = new SpotifyPlayer(this.accessToken);

            // Set up callbacks
            this.spotifyPlayer.onNowPlayingChange = (track) => {
                this.updateNowPlaying(track);
            };

            this.spotifyPlayer.onPlaybackStateChange = (state) => {
                this.updatePlayButton(state.paused);
            };

            // Initialize player (async - will complete in background)
            await this.spotifyPlayer.init();
        } catch (error) {
            console.error('Error initializing Spotify player:', error);
        }
    }

    updateNowPlaying(track) {
        if (track) {
            this.elements.nowPlaying.textContent = `${track.name} - ${track.artists.map(a => a.name).join(', ')}`;
        } else {
            this.elements.nowPlaying.textContent = 'No track playing';
        }
    }

    updatePlayButton(isPaused) {
        if (this.elements.playerPlayPause) {
            this.elements.playerPlayPause.textContent = isPaused ? '▶' : '⏸';
        }
    }

    async togglePlayback() {
        if (this.spotifyPlayer) {
            await this.spotifyPlayer.togglePlayback();
        }
    }

    async previousTrack() {
        if (this.spotifyPlayer) {
            await this.spotifyPlayer.previousTrack();
        }
    }

    async nextTrack() {
        if (this.spotifyPlayer) {
            await this.spotifyPlayer.nextTrack();
        }
    }

    async loadProgress() {
        try {
            const response = await fetch('/api/progress');
            const data = await response.json();

            if (response.ok) {
                this.elements.progressText.textContent =
                    `Progress: ${data.completed_tasks}/${data.total_tasks} (${data.percentage}%)`;
            }
        } catch (error) {
            console.error('Error loading progress:', error);
        }
    }

    async loadNextTask() {
        this.showLoading();

        try {
            const response = await fetch('/api/get_task');

            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                throw new Error(data.error || `Failed to load task: ${response.status}`);
            }

            const data = await response.json();

            if (data.task) {
                this.currentTask = data.task;
                this.renderTask();
                this.hideLoading();
            } else {
                // No tasks available - show completion
                this.showCompletion();
            }
        } catch (error) {
            console.error('Error loading task:', error);
            this.hideLoading();
            this.showError('Error loading task: ' + error.message);
        }
    }

    renderTask() {
        const task = this.currentTask;

        if (!task) {
            console.error('No current task to render');
            return;
        }

        // Render query
        if (task.task_type === 'text') {
            this.elements.queryText.textContent = task.query_text || '';
            this.elements.queryTextDisplay.style.display = 'block';
            this.elements.querySongDisplay.style.display = 'none';
        } else {
            // Song query
            if (task.seed_track) {
                this.elements.seedTrack.innerHTML = this.renderTrackCard(task.seed_track, true);
            }
            this.elements.querySongDisplay.style.display = 'block';
            this.elements.queryTextDisplay.style.display = 'none';
        }

        // Render left and right lists with null checks
        if (Array.isArray(task.left_list)) {
            this.elements.leftList.innerHTML = task.left_list.map(t => this.renderTrackCard(t)).join('');
        } else {
            console.error('Invalid left_list:', task.left_list);
            this.elements.leftList.innerHTML = '';
        }

        if (Array.isArray(task.right_list)) {
            this.elements.rightList.innerHTML = task.right_list.map(t => this.renderTrackCard(t)).join('');
        } else {
            console.error('Invalid right_list:', task.right_list);
            this.elements.rightList.innerHTML = '';
        }

        // Reset judgment state
        this.resetJudgmentState();
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    renderTrackCard(track, isSeed = false) {
        if (!track || !track.id) {
            console.error('Invalid track data:', track);
            return '';
        }

        // Spotify format: artists is array of objects with 'name' field
        const artists = Array.isArray(track.artists)
            ? track.artists.map(a => a.name).join(', ')
            : 'Unknown Artist';
        const songName = track.name || 'Unknown Song';

        // Create elements safely to avoid XSS
        const div = document.createElement('div');
        div.className = `track-card ${isSeed ? 'seed-card' : ''}`;
        div.dataset.trackId = track.id;

        const trackInfo = document.createElement('div');
        trackInfo.className = 'track-info';

        const trackName = document.createElement('div');
        trackName.className = 'track-name';
        trackName.textContent = songName;

        const trackArtist = document.createElement('div');
        trackArtist.className = 'track-artist';
        trackArtist.textContent = artists;

        trackInfo.appendChild(trackName);
        trackInfo.appendChild(trackArtist);

        const playBtn = document.createElement('button');
        playBtn.className = 'play-btn';
        playBtn.textContent = '▶';
        playBtn.addEventListener('click', () => this.playTrack(track.id));

        div.appendChild(trackInfo);
        div.appendChild(playBtn);

        return div.outerHTML;
    }

    async playTrack(trackId) {
        if (this.spotifyPlayer) {
            await this.spotifyPlayer.playTrack(trackId);
        } else {
            // Fallback to opening in Spotify
            window.open(`https://open.spotify.com/track/${trackId}`, '_blank');
        }
    }

    handleChoiceClick(e) {
        const btn = e.currentTarget;
        this.selectedChoice = btn.dataset.choice;

        // Update UI
        document.querySelectorAll('.choice-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');

        // Show confidence section
        this.elements.confidenceSection.style.display = 'block';
        this.selectedConfidence = null;
        document.querySelectorAll('.confidence-btn').forEach(b => b.classList.remove('selected'));
        this.elements.submitBtn.style.display = 'none';
    }

    handleConfidenceClick(e) {
        const btn = e.currentTarget;
        this.selectedConfidence = parseInt(btn.dataset.confidence);

        // Update UI
        document.querySelectorAll('.confidence-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');

        // Show submit button
        this.elements.submitBtn.style.display = 'block';
    }

    async submitJudgment() {
        if (!this.selectedChoice || !this.selectedConfidence) {
            this.showError('Please select a choice and confidence level');
            return;
        }

        this.elements.submitBtn.disabled = true;
        this.elements.submitBtn.textContent = 'Submitting...';

        try {
            const response = await fetch('/api/submit_judgment', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    choice: this.selectedChoice,
                    confidence: this.selectedConfidence,
                    csrf_token: window.CSRF_TOKEN
                })
            });

            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                throw new Error(data.error || `Failed to submit judgment: ${response.status}`);
            }

            const data = await response.json();

            // Load progress
            await this.loadProgress();

            // Load next task
            await this.loadNextTask();
        } catch (error) {
            console.error('Error submitting judgment:', error);
            this.showError('Error submitting judgment: ' + error.message);
            this.elements.submitBtn.disabled = false;
            this.elements.submitBtn.textContent = 'Submit & Next';
        }
    }

    resetJudgmentState() {
        this.selectedChoice = null;
        this.selectedConfidence = null;
        document.querySelectorAll('.choice-btn').forEach(b => b.classList.remove('selected'));
        document.querySelectorAll('.confidence-btn').forEach(b => b.classList.remove('selected'));
        this.elements.confidenceSection.style.display = 'none';
        this.elements.submitBtn.style.display = 'none';
        this.elements.submitBtn.disabled = false;
        this.elements.submitBtn.textContent = 'Submit & Next';
    }

    showLoading() {
        this.elements.loadingState.style.display = 'flex';
        this.elements.taskContainer.style.display = 'none';
        this.elements.completionState.style.display = 'none';
    }

    hideLoading() {
        this.elements.loadingState.style.display = 'none';
        this.elements.taskContainer.style.display = 'block';
    }

    showCompletion() {
        this.elements.loadingState.style.display = 'none';
        this.elements.taskContainer.style.display = 'none';
        this.elements.completionState.style.display = 'flex';
    }

    showError(message) {
        alert(message);
    }
}

// Initialize app
let arena;
document.addEventListener('DOMContentLoaded', () => {
    arena = new ArenaApp();
});
