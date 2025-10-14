# Song Search Arena

Song Search Arena is a lightweight web application for conducting blinded, pairwise preference evaluations of music retrieval systems. The tool is **model-agnostic** and can be used to compare any music retrieval systems, whether they're based on embeddings, symbolic features, hybrid approaches, or collaborative filtering.
### How It Works
Song Search Arena takes two simple inputs following standardized schemas:

**1. Queries**: A list of `EvalQuery` objects, each one a single song or text query
```json

{
  "id": "5b227d8a11f528cd6230f86f03e69fcc",
  "type": "text", // or "song"
  "text": "reflective late-night electronic",
  "genres": ["edm"],
  "track_id": null // only for song-based queries
}
```

  
**2. Retrieval Results**: A list of `EvalResponse` objects, containing each system's top-K candidates per query
```json
{
  "system_id": "songmatch_prod_v1",
  "query_id": "5b227d8a11f528cd6230f86f03e69fcc",
  "candidates": [
  	{"track_id": "74tsW...", "score": 0.549, "rank": 1},
  	{"track_id": "2GQEM...", "score": 0.548, "rank": 2},
  	// ... top K results
  	]
}

```
  
The arena handles everything else: applying uniform post-processing policies, materializing head-to-head comparisons, serving randomized tasks to raters, and collecting judgments for analysis.
## Key Features
- **Blinded Comparisons**: Systems are anonymized and randomly positioned (left/right) to eliminate bias
- **Integrated Playback**: Raters can stream tracks directly via Spotify Web Playback without leaving the evaluation interface
- **Centralized Post-Processing**: Enforces consistent filtering rules across all systems (e.g., 1-per-artist limits, seed artist exclusion for discovery mode)
- **Smart Scheduling**: Prioritizes underfilled tasks and ensures balanced coverage across queries and system pairs
- **Admin Panel**: Password-protected page for the admin to upload queries and system responses, view progress per task, and download judgments in CSV or JSON for downstream analysis
- **Analysis Script**: Script that takes in the downloaded judgments as input and computes head-to-head win rates along with statistical tests. 
