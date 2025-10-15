#!/usr/bin/env python3
"""
Song Search Arena Results Analysis

Analyzes exported judgments to compute head-to-head win rates with statistical tests.

Usage:
    python analyze_results.py <judgments_json_path> [--output <output_dir>]

Computes:
- Plain majority vote win rates
- Confidence-weighted win rates
- Stratified by: overall, task type, genre
- 95% Wilson confidence intervals
- Binomial tests against 50%
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict, Counter
import pandas as pd
import numpy as np
from scipy.stats import binomtest
from statsmodels.stats.proportion import proportion_confint


def load_judgments(path: str) -> List[Dict]:
    """Load judgments from exported JSON file."""
    with open(path, 'r') as f:
        judgments = json.load(f)

    print(f"Loaded {len(judgments)} judgments from {path}")

    # Validate required fields
    required_fields = ['query_id', 'pair_id', 'choice', 'confidence',
                      'left_system_id', 'right_system_id', 'task_type']

    for i, j in enumerate(judgments):
        missing = [f for f in required_fields if f not in j or j[f] is None]
        if missing:
            print(f"Warning: Judgment {i} missing fields: {missing}")

    return judgments


def aggregate_majority_vote(judgments: List[Dict], query_id: str, pair_id: str,
                            use_confidence: bool = False) -> Tuple[str, Dict]:
    """
    Aggregate judgments for a query to determine winner via majority vote.

    Args:
        judgments: All judgments for this (query_id, pair_id)
        query_id: Query ID
        pair_id: Pair ID
        use_confidence: If True, weight votes by confidence score

    Returns:
        Tuple of (winner, details_dict)
        winner: 'left', 'right', or 'tie'
        details_dict: Contains vote counts, systems, etc.
    """
    if not judgments:
        return 'tie', {}

    # Get system IDs (should be same across all judgments for this query-pair)
    left_system = judgments[0]['left_system_id']
    right_system = judgments[0]['right_system_id']

    # Count votes
    if use_confidence:
        # Sum confidence scores (skip judgments with None confidence)
        left_score = sum(j['confidence'] for j in judgments
                        if j['choice'] == 'left' and j['confidence'] is not None)
        right_score = sum(j['confidence'] for j in judgments
                         if j['choice'] == 'right' and j['confidence'] is not None)
        tie_score = sum(j['confidence'] for j in judgments
                       if j['choice'] == 'tie' and j['confidence'] is not None)

        # Winner is highest score
        scores = {'left': left_score, 'right': right_score, 'tie': tie_score}
        max_score = max(scores.values())

        # Check for actual ties (multiple choices with max score)
        winners = [choice for choice, score in scores.items() if score == max_score]
        winner = 'tie' if len(winners) > 1 else winners[0]

        details = {
            'left_score': left_score,
            'right_score': right_score,
            'tie_score': tie_score,
            'n_judgments': len(judgments)
        }
    else:
        # Plain majority vote
        left_votes = sum(1 for j in judgments if j['choice'] == 'left')
        right_votes = sum(1 for j in judgments if j['choice'] == 'right')
        tie_votes = sum(1 for j in judgments if j['choice'] == 'tie')

        # Winner is most votes
        votes = {'left': left_votes, 'right': right_votes, 'tie': tie_votes}
        max_votes = max(votes.values())

        # Check for actual ties
        winners = [choice for choice, count in votes.items() if count == max_votes]
        winner = 'tie' if len(winners) > 1 else winners[0]

        details = {
            'left_votes': left_votes,
            'right_votes': right_votes,
            'tie_votes': tie_votes,
            'n_judgments': len(judgments)
        }

    details.update({
        'query_id': query_id,
        'pair_id': pair_id,
        'left_system': left_system,
        'right_system': right_system,
        'winner': winner
    })

    return winner, details


def wilson_confidence_interval(successes: int, trials: int, alpha: float = 0.05) -> Tuple[float, float]:
    """
    Compute Wilson score confidence interval for a proportion.

    Args:
        successes: Number of successes
        trials: Total number of trials
        alpha: Significance level (default 0.05 for 95% CI)

    Returns:
        Tuple of (lower_bound, upper_bound)
    """
    if trials == 0:
        return (0.0, 0.0)

    ci_low, ci_high = proportion_confint(successes, trials, alpha=alpha, method='wilson')
    return (ci_low, ci_high)


def binomial_test_pvalue(successes: int, trials: int, p_null: float = 0.5) -> float:
    """
    Compute p-value for binomial test against null hypothesis.

    Args:
        successes: Number of successes
        trials: Total number of trials
        p_null: Null hypothesis probability (default 0.5)

    Returns:
        Two-tailed p-value
    """
    if trials == 0:
        return 1.0

    result = binomtest(successes, trials, p_null, alternative='two-sided')
    return result.pvalue


def compute_pairwise_stats(query_results: List[Dict],
                           stratification_type: str = 'overall',
                           stratification_value: str = 'all',
                           system_order: Optional[List[str]] = None) -> Dict:
    """
    Compute win rate statistics for a set of query results.

    Args:
        query_results: List of query-level results (after majority aggregation)
        stratification_type: Type of stratification ('overall', 'task_type', 'genre')
        stratification_value: Value of stratification ('all', 'text', 'song', 'pop', etc.)
        system_order: Optional list of [system_a, system_b] to use instead of alphabetical ordering

    Returns:
        Dict with statistics
    """
    if not query_results:
        return {
            'stratification_type': stratification_type,
            'stratification_value': stratification_value,
            'n_queries': 0,
            'system_a': None,
            'system_b': None,
            'wins_a': 0,
            'wins_b': 0,
            'ties': 0,
            'win_rate': 0.0,
            'tie_rate': 0.0,
            'ci_lower': 0.0,
            'ci_upper': 0.0,
            'p_value': 1.0
        }

    # Determine the two systems in this pair
    # Since left/right assignments are randomized per query, we need to find the unique systems
    all_systems = set()
    for r in query_results:
        all_systems.add(r['left_system'])
        all_systems.add(r['right_system'])

    if len(all_systems) != 2:
        raise ValueError(f"Expected exactly 2 systems, found {len(all_systems)}: {all_systems}")

    # Establish canonical ordering
    if system_order:
        # Use provided ordering
        if set(system_order) != all_systems:
            raise ValueError(f"Provided system_order {system_order} doesn't match systems in data {all_systems}")
        system_a, system_b = system_order[0], system_order[1]
    else:
        # Default to alphabetical ordering
        system_a, system_b = sorted(all_systems)

    # Count wins, accounting for which side each system is on
    wins_a = 0
    wins_b = 0
    ties = 0

    for r in query_results:
        winner = r['winner']

        if winner == 'tie':
            ties += 1
        elif winner == 'left':
            # Left side won - check which system was on the left
            if r['left_system'] == system_a:
                wins_a += 1
            else:
                wins_b += 1
        elif winner == 'right':
            # Right side won - check which system was on the right
            if r['right_system'] == system_a:
                wins_a += 1
            else:
                wins_b += 1

    n_queries = len(query_results)
    n_decisive = wins_a + wins_b  # Exclude ties for win rate calculation

    # Compute win rate (ignoring ties)
    win_rate = wins_a / n_decisive if n_decisive > 0 else 0.5
    tie_rate = ties / n_queries if n_queries > 0 else 0.0

    # Compute 95% Wilson CI
    ci_lower, ci_upper = wilson_confidence_interval(wins_a, n_decisive)

    # Compute binomial test p-value
    p_value = binomial_test_pvalue(wins_a, n_decisive)

    return {
        'stratification_type': stratification_type,
        'stratification_value': stratification_value,
        'n_queries': n_queries,
        'system_a': system_a,
        'system_b': system_b,
        'wins_a': wins_a,
        'wins_b': wins_b,
        'ties': ties,
        'win_rate': win_rate,
        'tie_rate': tie_rate,
        'ci_lower': ci_lower,
        'ci_upper': ci_upper,
        'p_value': p_value
    }


def stratify_by_task_type(query_results: List[Dict], judgments_by_query: Dict) -> Dict[str, List[Dict]]:
    """
    Stratify query results by task type.

    Returns:
        Dict mapping task_type to list of query results
    """
    stratified = defaultdict(list)

    for result in query_results:
        query_id = result['query_id']
        # Get task type from one of the judgments for this query
        task_type = judgments_by_query[query_id][0]['task_type']
        stratified[task_type].append(result)

    return dict(stratified)


def stratify_by_genre(query_results: List[Dict], judgments_by_query: Dict) -> Dict[str, List[Dict]]:
    """
    Stratify query results by genre.
    Multi-genre queries contribute to all their genres.

    Returns:
        Dict mapping genre to list of query results
    """
    stratified = defaultdict(list)

    for result in query_results:
        query_id = result['query_id']
        # Get genres from one of the judgments for this query
        genres = judgments_by_query[query_id][0].get('genres', [])

        if not genres:
            # Query has no genres - add to 'unspecified' category
            stratified['unspecified'].append(result)
        else:
            # Add to all genres
            for genre in genres:
                stratified[genre].append(result)

    return dict(stratified)


def analyze_judgments(judgments: List[Dict], use_confidence: bool = False,
                      system_order: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Analyze judgments and compute stratified statistics.

    Args:
        judgments: List of judgment dicts
        use_confidence: If True, use confidence-weighted voting
        system_order: Optional list of [system_a, system_b] to use instead of alphabetical ordering

    Returns:
        DataFrame with statistics for all stratifications
    """
    # Group judgments by (query_id, pair_id)
    judgments_by_query_pair = defaultdict(list)
    judgments_by_query = defaultdict(list)

    for j in judgments:
        key = (j['query_id'], j['pair_id'])
        judgments_by_query_pair[key].append(j)
        judgments_by_query[j['query_id']].append(j)

    print(f"Found {len(judgments_by_query_pair)} unique (query, pair) combinations")
    print(f"Found {len(judgments_by_query)} unique queries")

    # Aggregate each query via majority vote
    query_results = []
    for (query_id, pair_id), query_judgments in judgments_by_query_pair.items():
        winner, details = aggregate_majority_vote(
            query_judgments, query_id, pair_id, use_confidence=use_confidence
        )
        query_results.append(details)

    print(f"Aggregated {len(query_results)} query-level results")

    # Collect statistics for all stratifications
    all_stats = []

    # 1. Overall statistics
    overall_stats = compute_pairwise_stats(query_results, 'overall', 'all', system_order)
    all_stats.append(overall_stats)

    # 2. Stratify by task type
    by_task_type = stratify_by_task_type(query_results, judgments_by_query)
    for task_type, results in by_task_type.items():
        stats = compute_pairwise_stats(results, 'task_type', task_type, system_order)
        all_stats.append(stats)

    # 3. Stratify by genre
    by_genre = stratify_by_genre(query_results, judgments_by_query)
    for genre, results in by_genre.items():
        stats = compute_pairwise_stats(results, 'genre', genre, system_order)
        all_stats.append(stats)

    # Convert to DataFrame
    df = pd.DataFrame(all_stats)

    # Reorder columns for readability
    column_order = [
        'stratification_type', 'stratification_value',
        'system_a', 'system_b',
        'n_queries', 'wins_a', 'wins_b', 'ties',
        'win_rate', 'tie_rate',
        'ci_lower', 'ci_upper', 'p_value'
    ]
    df = df[column_order]

    return df


def main():
    parser = argparse.ArgumentParser(
        description='Analyze Song Search Arena judgment data'
    )
    parser.add_argument(
        '--judgments_path',
        type=str,
        help='Path to exported judgments JSON file'
    )
    parser.add_argument(
        '--output_dir',
        type=str,
        default='.',
        help='Output directory for results (default: current directory)'
    )
    parser.add_argument(
        '--system_order',
        type=str,
        nargs=2,
        metavar=('SYSTEM_A', 'SYSTEM_B'),
        help='Specify system ordering (default: alphabetical). Provide two system IDs.'
    )

    args = parser.parse_args()

    # Create output directory if needed
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load judgments
    print(f"\nLoading judgments from {args.judgments_path}...")
    judgments = load_judgments(args.judgments_path)

    if not judgments:
        print("No judgments found!")
        return

    # Display system ordering
    if args.system_order:
        print(f"\nUsing custom system ordering: A={args.system_order[0]}, B={args.system_order[1]}")
    else:
        print("\nUsing default alphabetical system ordering")

    # Analyze with plain majority vote
    print("\n" + "="*60)
    print("PLAIN MAJORITY VOTE ANALYSIS")
    print("="*60)
    plain_results = analyze_judgments(judgments, use_confidence=False, system_order=args.system_order)

    # Save plain results
    plain_csv = output_dir / 'results_plain_majority.csv'
    plain_results.to_csv(plain_csv, index=False)
    print(f"\nPlain majority vote results saved to: {plain_csv}")

    # Print plain results
    print("\n" + plain_results.to_string(index=False))

    # Analyze with confidence weighting
    print("\n" + "="*60)
    print("CONFIDENCE-WEIGHTED ANALYSIS")
    print("="*60)
    weighted_results = analyze_judgments(judgments, use_confidence=True, system_order=args.system_order)

    # Save weighted results
    weighted_csv = output_dir / 'results_confidence_weighted.csv'
    weighted_results.to_csv(weighted_csv, index=False)
    print(f"\nConfidence-weighted results saved to: {weighted_csv}")

    # Print weighted results
    print("\n" + weighted_results.to_string(index=False))

    print("\n" + "="*60)
    print("ANALYSIS COMPLETE")
    print("="*60)
    print(f"\nResults saved to:")
    print(f"  - {plain_csv}")
    print(f"  - {weighted_csv}")


if __name__ == '__main__':
    main()
