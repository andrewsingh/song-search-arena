// Spotify Player Module for Song Search Arena

class SpotifyPlayer {
    constructor(accessToken) {
        this.accessToken = accessToken;
        this.player = null;
        this.deviceId = null;
        this.isPlayerReady = false;

        // Callbacks
        this.onNowPlayingChange = null;
        this.onPlaybackStateChange = null;
    }

    async init() {
        if (!this.accessToken) {
            console.error('Cannot initialize player: no access token');
            throw new Error('No access token provided');
        }

        // Wait for Spotify SDK to be available
        await this.waitForSpotify();

        try {
            this.player = new window.Spotify.Player({
                name: 'Song Search Arena',
                getOAuthToken: cb => { cb(this.accessToken); },
                volume: 0.5
            });

            this.setupListeners();

            // Connect to the player
            const connected = await this.player.connect();
            if (connected) {
                console.log('Successfully connected to Spotify');
            } else {
                throw new Error('Failed to connect to Spotify');
            }
        } catch (error) {
            console.error('Error initializing Spotify player:', error);
            throw error;
        }
    }

    waitForSpotify() {
        return new Promise((resolve) => {
            if (window.Spotify) {
                resolve();
            } else {
                window.onSpotifyWebPlaybackSDKReady = () => {
                    resolve();
                };
            }
        });
    }

    setupListeners() {
        // Error handling
        this.player.addListener('initialization_error', ({ message }) => {
            console.error('Spotify initialization error:', message);
        });

        this.player.addListener('authentication_error', ({ message }) => {
            console.error('Spotify authentication error:', message);
        });

        this.player.addListener('account_error', ({ message }) => {
            console.error('Spotify account error:', message);
        });

        this.player.addListener('playback_error', ({ message }) => {
            console.error('Spotify playback error:', message);
        });

        // Player state changes
        this.player.addListener('player_state_changed', state => {
            if (!state) return;

            // Update now playing
            if (this.onNowPlayingChange && state.track_window.current_track) {
                this.onNowPlayingChange(state.track_window.current_track);
            }

            // Update playback state
            if (this.onPlaybackStateChange) {
                this.onPlaybackStateChange({
                    paused: state.paused,
                    position: state.position,
                    duration: state.duration
                });
            }
        });

        // Ready
        this.player.addListener('ready', ({ device_id }) => {
            console.log('Spotify Player Ready with Device ID', device_id);
            this.deviceId = device_id;
            this.isPlayerReady = true;
        });

        // Not Ready
        this.player.addListener('not_ready', ({ device_id }) => {
            console.log('Spotify Player went offline:', device_id);
            this.isPlayerReady = false;
        });
    }

    async playTrack(trackId) {
        if (!this.isPlayerReady || !this.deviceId) {
            console.log('Player not ready, opening in Spotify app');
            window.open(`https://open.spotify.com/track/${trackId}`, '_blank');
            return;
        }

        try {
            const response = await fetch(
                `https://api.spotify.com/v1/me/player/play?device_id=${this.deviceId}`,
                {
                    method: 'PUT',
                    headers: {
                        'Authorization': `Bearer ${this.accessToken}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        uris: [`spotify:track:${trackId}`]
                    })
                }
            );

            if (!response.ok) {
                throw new Error(`Spotify API error: ${response.status}`);
            }
        } catch (error) {
            console.error('Error playing track:', error);
            // Fallback to opening in Spotify
            window.open(`https://open.spotify.com/track/${trackId}`, '_blank');
        }
    }

    async togglePlayback() {
        if (!this.player || !this.isPlayerReady) {
            console.log('Player not ready');
            return;
        }

        try {
            await this.player.togglePlay();
        } catch (error) {
            console.error('Error toggling playback:', error);
        }
    }

    async previousTrack() {
        if (!this.player || !this.isPlayerReady) {
            console.log('Player not ready');
            return;
        }

        try {
            await this.player.previousTrack();
        } catch (error) {
            console.error('Error going to previous track:', error);
        }
    }

    async nextTrack() {
        if (!this.player || !this.isPlayerReady) {
            console.log('Player not ready');
            return;
        }

        try {
            await this.player.nextTrack();
        } catch (error) {
            console.error('Error going to next track:', error);
        }
    }

    async pause() {
        if (!this.player || !this.isPlayerReady) {
            console.log('Player not ready');
            return;
        }

        try {
            await this.player.pause();
        } catch (error) {
            console.error('Error pausing:', error);
        }
    }

    async resume() {
        if (!this.player || !this.isPlayerReady) {
            console.log('Player not ready');
            return;
        }

        try {
            await this.player.resume();
        } catch (error) {
            console.error('Error resuming:', error);
        }
    }

    async getCurrentState() {
        if (!this.player || !this.isPlayerReady) {
            return null;
        }

        try {
            return await this.player.getCurrentState();
        } catch (error) {
            console.error('Error getting current state:', error);
            return null;
        }
    }

    disconnect() {
        if (this.player) {
            this.player.disconnect();
            this.isPlayerReady = false;
            this.deviceId = null;
        }
    }
}

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SpotifyPlayer;
}
