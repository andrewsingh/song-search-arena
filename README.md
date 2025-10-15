# Song Search Arena

A lightweight web application for conducting blinded pairwise evaluations of music retrieval systems. The tool is **model-agnostic** and can be used to evaluate any type of music retrieval approach (embeddings, symbolic features, hybrid models, collaborative filtering, etc.).

---

## Overview

Song Search Arena enables you to objectively compare music retrieval systems through human preference judgments. Raters compare recommendation lists side-by-side in a blinded interface with integrated Spotify playback, while the arena handles randomization, task scheduling, and data collection.

### How It Works

You provide two simple inputs:

**1. Queries** (`EvalQuery`): What you're searching for
```json
{
  "id": "5b227d8a11f528cd6230f86f03e69fcc",
  "type": "text",  // or "song" for song-based retrieval
  "text": "reflective late-night electronic",
  "genres": ["edm"],
  "seed_track_id": null
}
```

**2. Retrieval Results** (`EvalResponse`): Each system's top-K candidates per query
```json
{
  "system_id": "songmatch_prod_v1",
  "query_id": "5b227d8a11f528cd6230f86f03e69fcc",
  "candidates": [
    {"track_id": "74tsW...", "score": 0.549, "rank": 1},
    {"track_id": "2GQEM...", "score": 0.548, "rank": 2}
    // ... top K results (K ≥ 50 recommended)
  ]
}
```

The arena handles the rest:
- Applies uniform post-processing policies (artist diversity, discovery mode, etc.)
- Generates all pairwise system comparisons
- Serves randomized, blinded tasks to raters with integrated Spotify playback
- Collects judgments with confidence ratings
- Exports data for statistical analysis

---

## Key Features

- **Blinded Comparisons** – Systems anonymized with randomized left/right positioning
- **Integrated Spotify Playback** – Stream tracks directly in the evaluation interface (Premium) or open in Spotify app
- **Centralized Post-Processing** – Uniform filtering rules across all systems (1-per-artist limits, seed artist exclusion, etc.)
- **Smart Task Scheduling** – Prioritizes underfilled tasks and ensures balanced query coverage
- **Admin Dashboard** – Upload datasets, monitor progress, export judgments (CSV/JSON)
- **Statistical Analysis** – Built-in script computes win rates, confidence intervals, and significance tests

---

## Quick Start

### Prerequisites

- Python 3.9+
- [Supabase](https://supabase.com) account (free tier works)
- [Spotify Developer](https://developer.spotify.com/dashboard) app credentials

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/song-search-arena.git
   cd song-search-arena
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**

   Create a `.env` file:
   ```bash
   # Spotify OAuth
   SPOTIFY_CLIENT_ID=your_client_id
   SPOTIFY_CLIENT_SECRET=your_client_secret
   SPOTIFY_REDIRECT_URI=http://localhost:5001/callback

   # Supabase
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_ANON_KEY=your_anon_key
   SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

   # Passwords
   EVAL_PASSWORD=your_eval_password
   ADMIN_PASSWORD=your_admin_password

   # App config
   SECRET_KEY=your_secret_key
   FLASK_ENV=development
   ```

4. **Initialize the database**

   Run the schema SQL in your Supabase SQL editor:
   ```bash
   cat schema.sql
   # Copy and execute in Supabase dashboard
   ```

5. **Run the application**
   ```bash
   python -m song_search_arena.app
   ```

   Access at `http://localhost:5001`

### Deployment

To allow multiple raters to access the evaluation remotely, you can deploy to [Railway](https://railway.app):

1. **Create a Railway account** and install the CLI (or use the web dashboard)

2. **Update environment variables** for production:
   - Set `SPOTIFY_REDIRECT_URI` to your Railway domain (e.g., `https://your-app.up.railway.app/callback`)
   - Add the same redirect URI to your [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   - Set `FLASK_ENV=production`

3. **Deploy**
   ```bash
   railway login
   railway init
   railway up
   ```

4. **Configure environment variables** in the Railway dashboard under your project's Variables tab

Railway will automatically detect the Flask app and deploy it with HTTPS. Share the generated URL with your raters.

---

## Usage

### Running an Evaluation

1. **Prepare your data** following the `EvalQuery` and `EvalResponse` schemas (see `policies/` for examples)

2. **Set a post-processing policy** via the admin panel (`/admin`)
   - Upload `policies/eval_policy_v1.json` or create your own
   - Key parameters: `final_k`, `max_per_artist`, `exclude_seed_artist`

3. **Upload queries and system responses** in the admin panel
   - Drag-and-drop JSON files or paste directly
   - The arena validates and materializes pairwise tasks

4. **Share the evaluation link** with raters
   - Raters authenticate with Spotify and provide judgments
   - Progress tracked in real-time on admin dashboard

5. **Export and analyze results**
   - Download judgments from admin panel
   - Run analysis script:
     ```bash
     python analyze_results.py --judgments_path judgments.json --output_dir results/
     ```

### Analysis Script

The included analysis script computes:
- Win rates with 95% Wilson confidence intervals
- Statistical significance (binomial tests)
- Stratification by task type and genre
- Both plain majority vote and confidence-weighted results

```bash
# Basic usage
python analyze_results.py --judgments_path judgments.json --output_dir results/

# Custom system ordering
python analyze_results.py --judgments_path judgments.json --output_dir results/ \
  --system_order system_a_id system_b_id
```

---

## Project Structure

```
song-search-arena/
├── song_search_arena/       # Main application
│   ├── app.py               # Flask app and routes
│   ├── export.py            # Export functions
│   ├── constants.py         # Configuration constants
│   ├── templates/           # HTML templates
│   └── static/              # CSS, JS, assets
├── analyze_results.py       # Statistical analysis script
├── schema.sql               # Database schema
├── policies/                # Example post-processing policies
├── requirements.txt         # Python dependencies
└── README.md
```

---

## Citation

If you use Song Search Arena in your research, please cite:

```bibtex
@misc{song-search-arena,
  author = {Andrew Singh},
  title = {Song Search Arena: A Tool for Evaluating Music Retrieval Systems},
  year = {2025},
  url = {https://github.com/andrewsingh/song-search-arena}
}
``` 
