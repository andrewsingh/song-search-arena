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
            leftResultList: document.getElementById('left-result-list'),
            rightResultList: document.getElementById('right-result-list'),
            confidenceSection: document.getElementById('confidence-section'),
            submitBtn: document.getElementById('submit-btn'),
            progressText: document.getElementById('progress-text'),
            spotifyStatus: document.getElementById('spotify-status'),
            playerCover: document.getElementById('player-cover'),
            playerTitle: document.getElementById('player-title'),
            playerArtist: document.getElementById('player-artist'),
            playerPrev: document.getElementById('player-prev'),
            playerPlayPause: document.getElementById('player-play-pause'),
            playerNext: document.getElementById('player-next'),
            currentTime: document.getElementById('current-time'),
            totalTime: document.getElementById('total-time'),
            progressFilled: document.getElementById('progress-filled'),
            progressBarContainer: document.getElementById('progress-bar-container')
        };

        // Track the currently playing track ID and store track metadata
        this.currentPlayingTrackId = null;
        this.currentTracks = {}; // Store all tracks from current task by ID

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

            // Add hover listeners for list highlighting
            btn.addEventListener('mouseenter', (e) => {
                // Only highlight on hover if button is not already selected
                if (!btn.classList.contains('selected')) {
                    const choice = btn.dataset.choice;
                    this.updateListHighlights(choice, false);
                }
            });

            btn.addEventListener('mouseleave', (e) => {
                // Remove hover highlights, but keep selected highlights
                if (!btn.classList.contains('selected')) {
                    this.clearListHighlights();
                    // Re-apply highlights if another button is selected
                    const selectedBtn = document.querySelector('.choice-btn.selected');
                    if (selectedBtn) {
                        this.updateListHighlights(selectedBtn.dataset.choice, true);
                    }
                }
            });
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

        // Progress bar seeking
        if (this.elements.progressBarContainer) {
            this.elements.progressBarContainer.addEventListener('click', (e) => this.seekToPosition(e));
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
            this.updateSpotifyStatus('error', 'Failed to authenticate');
            return;
        }

        try {
            this.updateSpotifyStatus('connecting', 'Connecting to Spotify...');

            // Create Spotify player instance
            this.spotifyPlayer = new SpotifyPlayer(this.accessToken);

            // Set up callbacks
            this.spotifyPlayer.onPlaybackStateChange = (state) => {
                this.updatePlayButton(state.paused);
                if (state.position !== undefined && state.duration !== undefined) {
                    this.updateProgress(state.position, state.duration);
                }
            };

            this.spotifyPlayer.onPlayerReady = () => {
                this.updateSpotifyStatus('connected', 'Connected to Spotify');
            };

            this.spotifyPlayer.onPlayerError = () => {
                this.updateSpotifyStatus('error', 'Spotify connection error');
            };

            // Initialize player (async - will complete in background)
            await this.spotifyPlayer.init();
        } catch (error) {
            console.error('Error initializing Spotify player:', error);
            this.updateSpotifyStatus('error', 'Failed to connect');
        }
    }

    updateSpotifyStatus(status, text) {
        if (!this.elements.spotifyStatus) return;

        this.elements.spotifyStatus.className = `spotify-status ${status}`;
        const statusText = this.elements.spotifyStatus.querySelector('.status-text');
        if (statusText) {
            statusText.textContent = text;
        }
    }

    updatePlayButton(isPaused) {
        if (this.elements.playerPlayPause) {
            this.elements.playerPlayPause.textContent = isPaused ? '▶' : '⏸';
        }
    }

    updateProgress(position, duration) {
        if (this.elements.progressFilled && duration > 0) {
            const percentage = (position / duration) * 100;
            this.elements.progressFilled.style.width = `${percentage}%`;
        }

        if (this.elements.currentTime) {
            this.elements.currentTime.textContent = this.formatTime(position);
        }

        if (this.elements.totalTime) {
            this.elements.totalTime.textContent = this.formatTime(duration);
        }
    }

    formatTime(ms) {
        if (!ms || ms < 0) return '0:00';
        const minutes = Math.floor(ms / 60000);
        const seconds = Math.floor((ms % 60000) / 1000);
        return `${minutes}:${seconds.toString().padStart(2, '0')}`;
    }

    async seekToPosition(event) {
        if (!this.spotifyPlayer || !this.spotifyPlayer.isPlayerReady) {
            console.log('🎧 Player not ready for seeking');
            return;
        }

        try {
            const progressBar = event.currentTarget;
            const rect = progressBar.getBoundingClientRect();
            const percentage = (event.clientX - rect.left) / rect.width;

            // Get current state to determine duration
            const state = await this.spotifyPlayer.getCurrentState();
            if (state && state.duration) {
                const newPosition = Math.floor(percentage * state.duration);
                await this.spotifyPlayer.seek(newPosition);
                console.log(`🎧 Seeked to position: ${this.formatTime(newPosition)}`);
            }
        } catch (error) {
            console.error('❌ Error seeking:', error);
        }
    }

    async togglePlayback() {
        if (this.spotifyPlayer) {
            await this.spotifyPlayer.togglePlayback();
        }
    }

    async previousTrack() {
        if (!this.currentPlayingTrackId) {
            console.log('No track currently playing');
            return;
        }

        // Find which list contains the current track and get previous track
        const prevTrack = this.getAdjacentTrack(-1);
        if (prevTrack) {
            await this.playTrack(prevTrack.id);
        } else {
            console.log('Already at first track in list');
        }
    }

    async nextTrack() {
        if (!this.currentPlayingTrackId) {
            console.log('No track currently playing');
            return;
        }

        // Find which list contains the current track and get next track
        const nextTrack = this.getAdjacentTrack(1);
        if (nextTrack) {
            await this.playTrack(nextTrack.id);
        } else {
            console.log('Already at last track in list');
        }
    }

    getAdjacentTrack(direction) {
        // direction: -1 for previous, 1 for next
        // Check both left and right lists
        const leftCards = Array.from(this.elements.leftList.querySelectorAll('.track-card'));
        const rightCards = Array.from(this.elements.rightList.querySelectorAll('.track-card'));

        // Find current track in left list
        const leftIndex = leftCards.findIndex(card => card.dataset.trackId === this.currentPlayingTrackId);
        if (leftIndex !== -1) {
            const newIndex = leftIndex + direction;
            if (newIndex >= 0 && newIndex < leftCards.length) {
                const trackId = leftCards[newIndex].dataset.trackId;
                return this.currentTracks[trackId];
            }
            return null;
        }

        // Find current track in right list
        const rightIndex = rightCards.findIndex(card => card.dataset.trackId === this.currentPlayingTrackId);
        if (rightIndex !== -1) {
            const newIndex = rightIndex + direction;
            if (newIndex >= 0 && newIndex < rightCards.length) {
                const trackId = rightCards[newIndex].dataset.trackId;
                return this.currentTracks[trackId];
            }
            return null;
        }

        return null;
    }

    async loadProgress() {
        try {
            const response = await fetch('/api/progress');
            const data = await response.json();

            if (response.ok) {
                this.elements.progressText.textContent =
                    `Progress: ${data.completed_tasks}/${data.total_tasks} (${data.percentage}%)`;
            } else {
                console.error('Progress API error:', data);
                this.elements.progressText.textContent = 'Progress: N/A';
            }
        } catch (error) {
            console.error('Error loading progress:', error);
            this.elements.progressText.textContent = 'Progress: Error';
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
                this.attachPlayButtonListeners(this.elements.seedTrack);
            }
            this.elements.querySongDisplay.style.display = 'block';
            this.elements.queryTextDisplay.style.display = 'none';
        }

        // Store track metadata and render lists
        this.currentTracks = {};

        // Store tracks from all lists
        const allTracks = [
            ...(Array.isArray(task.left_list) ? task.left_list : []),
            ...(Array.isArray(task.right_list) ? task.right_list : [])
        ];
        if (task.seed_track) {
            allTracks.push(task.seed_track);
        }
        allTracks.forEach(track => {
            if (track && track.id) {
                this.currentTracks[track.id] = track;
            }
        });

        // Render left and right lists with null checks
        if (Array.isArray(task.left_list)) {
            this.elements.leftList.innerHTML = task.left_list.map(t => this.renderTrackCard(t)).join('');
            this.attachPlayButtonListeners(this.elements.leftList);
        } else {
            console.error('Invalid left_list:', task.left_list);
            this.elements.leftList.innerHTML = '';
        }

        if (Array.isArray(task.right_list)) {
            this.elements.rightList.innerHTML = task.right_list.map(t => this.renderTrackCard(t)).join('');
            this.attachPlayButtonListeners(this.elements.rightList);
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

        // Extract metadata from Spotify format
        const artists = Array.isArray(track.artists)
            ? track.artists.map(a => a.name).join(', ')
            : 'Unknown Artist';
        const songName = track.name || 'Unknown Song';
        const albumName = track.album?.name || '';

        // Get album art (prefer medium size, 300x300)
        const albumArt = track.album?.images?.[1]?.url || track.album?.images?.[0]?.url || '';

        // Build HTML string (event listeners will be attached separately)
        let html = `<div class="track-card ${isSeed ? 'seed-card' : ''}" data-track-id="${track.id}">`;

        if (albumArt) {
            html += `<img class="track-album-art" src="${this.escapeHtml(albumArt)}" alt="${this.escapeHtml(albumName)} cover">`;
        }

        html += `<div class="track-info">`;
        html += `<div class="track-name">${this.escapeHtml(songName)}</div>`;
        html += `<div class="track-artist">${this.escapeHtml(artists)}</div>`;

        html += `</div>`;
        html += `<button class="play-btn" data-track-id="${track.id}">▶</button>`;
        html += `</div>`;

        return html;
    }

    attachPlayButtonListeners(container) {
        // Find all track cards in the container and make them clickable
        const trackCards = container.querySelectorAll('.track-card');
        trackCards.forEach(card => {
            const trackId = card.dataset.trackId;
            if (trackId) {
                // Make entire card clickable
                card.addEventListener('click', (e) => {
                    console.log(`🎵 Track card clicked for track: ${trackId}`);
                    this.playTrack(trackId);
                });

                // Also handle play button (but let it bubble to card click)
                const playBtn = card.querySelector('.play-btn');
                if (playBtn) {
                    playBtn.addEventListener('click', (e) => {
                        // Don't stop propagation - let it bubble to card click
                        console.log(`🎵 Play button clicked for track: ${trackId}`);
                    });
                }
            }
        });
    }

    async playTrack(trackId) {
        console.log(`🎵 playTrack called for: ${trackId}`);

        // Get track metadata
        const track = this.currentTracks[trackId];
        if (!track) {
            console.error(`Track ${trackId} not found in current tracks`);
            return;
        }

        // Update player UI immediately
        this.updatePlayerDisplay(track);

        // Update playing state on cards
        this.updatePlayingCards(trackId);

        // Play the track
        if (this.spotifyPlayer) {
            await this.spotifyPlayer.playTrack(trackId);
        } else {
            // Fallback to opening in Spotify
            window.open(`https://open.spotify.com/track/${trackId}`, '_blank');
        }
    }

    updatePlayerDisplay(track) {
        // Update cover art
        const albumArt = track.album?.images?.[1]?.url || track.album?.images?.[0]?.url || '';
        if (this.elements.playerCover && albumArt) {
            this.elements.playerCover.src = albumArt;
            this.elements.playerCover.alt = `${track.album?.name || 'Album'} cover`;
        }

        // Update title and artist
        if (this.elements.playerTitle) {
            this.elements.playerTitle.textContent = track.name || 'Unknown Song';
        }

        if (this.elements.playerArtist) {
            const artists = Array.isArray(track.artists)
                ? track.artists.map(a => a.name).join(', ')
                : 'Unknown Artist';
            this.elements.playerArtist.textContent = artists;
        }
    }

    updatePlayingCards(trackId) {
        // Remove 'playing' class from all cards
        document.querySelectorAll('.track-card').forEach(card => {
            card.classList.remove('playing');
        });

        // Add 'playing' class to the current track card
        const playingCard = document.querySelector(`.track-card[data-track-id="${trackId}"]`);
        if (playingCard) {
            playingCard.classList.add('playing');
        }

        this.currentPlayingTrackId = trackId;
    }

    updateListHighlights(choice, persist = false) {
        // Clear all highlights first
        this.clearListHighlights();

        // Apply highlights based on choice
        if (choice === 'left') {
            this.elements.leftResultList.classList.add('highlighted');
        } else if (choice === 'right') {
            this.elements.rightResultList.classList.add('highlighted');
        } else if (choice === 'tie') {
            this.elements.leftResultList.classList.add('highlighted');
            this.elements.rightResultList.classList.add('highlighted');
        }
    }

    clearListHighlights() {
        if (this.elements.leftResultList) {
            this.elements.leftResultList.classList.remove('highlighted');
        }
        if (this.elements.rightResultList) {
            this.elements.rightResultList.classList.remove('highlighted');
        }
    }

    handleChoiceClick(e) {
        const btn = e.currentTarget;
        this.selectedChoice = btn.dataset.choice;

        // Update UI
        document.querySelectorAll('.choice-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');

        // Persist list highlights for selected choice
        this.updateListHighlights(this.selectedChoice, true);

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

        // Clear list highlights
        this.clearListHighlights();
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
