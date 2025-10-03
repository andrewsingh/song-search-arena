#!/usr/bin/env python3
"""
Deployment entry point for the Song Search Arena app.
Uses the correct data files for production deployment on Railway.
"""
import os
import sys
from pathlib import Path

# Add the song_search_arena directory to Python path
sys.path.insert(0, str(Path(__file__).parent / 'song_search_arena'))

from app import app, load_tracks_from_json

RAILWAY_VOLUME_MOUNT_PATH = os.getenv('RAILWAY_VOLUME_MOUNT_PATH', '/data')
DATASET_NAME = os.getenv('DATASET_NAME', 'library_v3.1e')

def main():
    """Initialize the app with production data files and start the server."""

    # Get port from environment (Railway/Render/Heroku style)
    port = int(os.environ.get('PORT', 5000))

    # Convert to Path objects for proper path operations
    volume_path = Path(RAILWAY_VOLUME_MOUNT_PATH)
    dataset_path = volume_path / DATASET_NAME

    # Path to tracks metadata JSON
    tracks_file = dataset_path / f'{DATASET_NAME}_metadata.json'

    # Verify file exists before starting
    if not tracks_file.exists():
        print(f"Error: Tracks metadata file not found: {tracks_file}")
        print(f"Expected path: {tracks_file}")
        print(f"Volume path: {volume_path}")
        print(f"Dataset name: {DATASET_NAME}")
        sys.exit(1)

    print(f"Initializing Song Search Arena with:")
    print(f"  Tracks metadata: {tracks_file}")

    # Load tracks metadata into global TRACKS dictionary
    import song_search_arena.app as app_module
    app_module.TRACKS = load_tracks_from_json(str(tracks_file))

    print(f"Loaded {len(app_module.TRACKS)} track IDs")

    # Start the app
    print(f"Starting server on 0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == '__main__':
    main()
