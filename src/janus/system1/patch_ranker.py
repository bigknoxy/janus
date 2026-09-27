"""Patch-candidate ranking — the second job of System 1 (JB-3).

Doctrine: deterministic verification is the judge; the decision model only
arbitrates WHICH candidate earns the verify cycle. First-candidate-wins
remains the law when the ranker has no signal — anchors carry safety,
hedges may not reorder reality.
"""



def rank_by_scores(scores: list[float]) -> list[int]:
    """Order candidate indexes by noul score; all-sub-0.5 ⇒ identity order."""
    if all(s < 0.5 for s in scores):
        return list(range(len(scores)))
    return sorted(range(len(scores)), key=lambda i: -scores[i])


def rank_questions(candidates: list[str]) -> dict[str, dict]:
    """One safe-fix noul per candidate patch (same head as file relevance)."""
    return {
        f"patch:{i}": {
            "type": "noul",
            "instructions": (
                f"Is patch candidate {i} a safe and correct fix for the "
                f"request? Candidate {i}:\n{patch[:500]}"
            ),
        }
        for i, patch in enumerate(candidates)
    }
