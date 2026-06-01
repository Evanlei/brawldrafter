# BrawlDrafter — Project Specification

**Version:** 2.0  
**Last Updated:** May 2026  
**Stack:** React · Tailwind · FastAPI · SQLite · Python · PyTorch

---

## Changelog (v1.4 -> v2.0)

- **Changed:** Recommendation engine architecture pivoted from external LLM APIs to a fully local hybrid system.
- **Removed:** All third-party LLM API dependencies from recommendation flow.
- **Added:** Deterministic recommendation scoring based on map/mode win-rate math, counters, and synergies.
- **Added:** Local neural scoring layer using a custom PyTorch model (`.pt`) for team-comp synergy prediction.
- **Added:** Backend model-loading lifecycle (startup load, warm health check, fallback behavior if model unavailable).
- **Updated:** API and error contracts to reference local model service rather than external AI providers.
- **Updated:** Environment variable requirements to include local model path and model runtime settings.
- **Updated:** Testing strategy to validate deterministic scorer + PyTorch scorer + fusion logic.

---

## 1. Project Overview

BrawlDrafter is a web application that provides data-driven pick recommendations for Brawl Stars drafting.  
The system now uses **local inference only**:

1. A deterministic stats-based algorithm.
2. A custom-trained PyTorch neural network that scores brawler synergy in context.

No third-party LLM APIs are used by the recommendation engine.

### Core Goals

- Recommend the best Blue-team picks for the current draft state.
- Use high-ELO match data as the primary signal source.
- Keep recommendation behavior explainable, fast, and reproducible.
- Keep inference local and deterministic enough for stable behavior across repeated calls.

---

## 2. Tech Stack

### Frontend
- React
- Tailwind CSS
- Zustand
- React Router
- Vite

### Backend
- Python 3.11+
- FastAPI
- SQLite (WAL mode)
- SQLAlchemy
- Alembic
- Pydantic
- httpx (Brawl Stars data ingestion)
- APScheduler
- slowapi
- **PyTorch (local model inference)**

### ML / Recommendation Layer
- **Deterministic scoring engine** (Python service)
- **Custom-trained PyTorch model** loaded from local `.pt` file
- **Weighted score fusion** to produce final ranking and confidence

---

## 3. Recommendation Engine (Hybrid v2)

The recommendation engine is now a **two-part hybrid system**.

### Part A — Deterministic Scorer

For each available brawler candidate on current `(map_id, mode_id)`:

- Base win-rate score from `brawler_stats.win_rate`
- Reliability weighting using `sample_size`
- Counter adjustment from `counters` against current Red picks
- Synergy adjustment from `synergies` with current Blue picks
- Optional pick-rate penalty/boost to reduce overfitting to low-volume anomalies

Example high-level formula:

```text
det_score =
  w_wr * normalized_win_rate
  + w_ctr * avg_counter_advantage_vs_red
  + w_syn * avg_synergy_with_blue
  + w_ss * reliability(sample_size)
```

### Part B — PyTorch Neural Synergy Scorer

A local PyTorch model predicts composition quality in the current draft context.

- Model file: local `.pt`
- Inputs: encoded candidate brawler + current blue/red picks + map + mode features
- Output: scalar synergy/fit score (`nn_score`) in normalized range

### Score Fusion

Final score per candidate:

```text
final_score = alpha * det_score + (1 - alpha) * nn_score
```

- `alpha` is config-driven (default `0.6`)
- Candidates ranked by `final_score`
- Top 3 returned with normalized confidence and short deterministic reason text

### Why this architecture

- Eliminates external model API cost and latency variance.
- Produces stable, testable recommendation behavior.
- Keeps explainability via deterministic factors while improving comp-level pattern recognition via ML.

---

## 4. Backend Architecture Updates

### Service Design

`services/recommendation.py` orchestrates:

1. Request validation.
2. Candidate pool derivation (exclude banned/picked).
3. Deterministic feature/scoring pass.
4. Neural model scoring pass.
5. Score fusion + ranking.
6. Response shaping (top 3).

### Model Loading Lifecycle

Create a dedicated local model runtime module, e.g. `services/model_runtime.py`:

- Load `.pt` model on FastAPI startup.
- Keep singleton model instance in memory.
- Set model to eval mode and no-grad inference path.
- Surface readiness in health checks.
- Fail gracefully if model file missing/corrupt.

### External API Boundary

- **Allowed external API:** Brawl Stars API for data ingestion only.
- **Disallowed in recommendation path:** all third-party LLM APIs.

---

## 5. API Contract (`POST /api/v1/recommendations`)

### Request

Same draft-state payload as v1.x:

- `map_id`, `mode_id`
- `first_pick_team`
- `blue_bans`, `red_bans`
- `blue_picks`, `red_picks`
- `current_pick_number`

### Response

Returns top 3 ranked recommendations:

```json
{
  "recommendations": [
    {
      "brawler_id": 8,
      "name": "Tara",
      "confidence": 0.87,
      "reason": "Strong map win rate and favorable counters into current red picks"
    }
  ]
}
```

### Error behavior

- `422`: validation failures
- `503`: recommendation service unavailable (e.g., model not loaded, model runtime failure)

---

## 6. Environment Variables (Backend)

| Variable | Required | Description |
|---|---|---|
| `BRAWLSTARS_API_KEY` | Yes | Bearer token for Brawl Stars ingestion endpoints |
| `INTERNAL_API_KEY` | Yes | Secret for internal pipeline endpoints |
| `DATABASE_URL` | Yes | SQLite/Postgres connection string |
| `FRONTEND_ORIGIN` | Yes | CORS allowed origin |
| `RECOMMENDER_MODEL_PATH` | Yes | Absolute/relative path to local `.pt` model file |
| `RECOMMENDER_ALPHA` | No | Deterministic-vs-NN fusion weight (default `0.6`) |
| `MODEL_DEVICE` | No | `cpu` (default) or `mps/cuda` where supported |

> Any third-party LLM API keys are removed from recommendation requirements.

---

## 7. Folder Structure (Backend excerpt)

```text
backend/
├── app/
│   ├── api/routes/
│   │   ├── recommendations.py
│   │   └── ...
│   ├── services/
│   │   ├── recommendation.py      # Hybrid scorer orchestration
│   │   ├── deterministic.py       # Win-rate math + counter/synergy scoring
│   │   ├── model_runtime.py       # .pt loading + singleton inference runtime
│   │   ├── nn_scorer.py           # Feature encoding + model inference wrapper
│   │   ├── aggregation.py
│   │   └── meta_snapshot.py
│   └── core/config.py             # Includes RECOMMENDER_MODEL_PATH, RECOMMENDER_ALPHA
├── models/
│   └── recommender.pt             # Local model artifact (environment-specific)
└── tests/
    ├── test_recommendation.py
    ├── test_model_runtime.py
    └── test_deterministic.py
```

---

## 8. Testing Strategy (Recommendation Layer)

### Deterministic scorer tests

- Correct win-rate normalization and sample-size weighting.
- Correct synergy and counter aggregation.
- Stable ranking when deterministic input data unchanged.

### Model runtime tests

- Model loads from valid path.
- Clean failure when file missing/corrupt.
- Inference shape/type contracts are enforced.

### Hybrid fusion tests

- `alpha=1.0` yields deterministic-only ordering.
- `alpha=0.0` yields NN-only ordering.
- Default alpha yields expected blended ordering on fixture cases.

### Endpoint tests

- 422 validation ordering still enforced.
- 503 returned when model runtime unavailable.
- Successful responses always contain exactly 3 recommendations.

---

## 9. Security & Reliability Notes

- No external LLM prompts or third-party inference calls in recommendation flow.
- Recommendation logic runs entirely on local backend runtime.
- Restrict write access to model artifact path to trusted operators only.
- On startup, log model checksum/version metadata for traceability.

---

## 10. Known Limitations

- High-ELO source bias remains (top-ranked player data).
- No ban data in standard Brawl Stars battle logs.
- Recommendation quality depends on model training quality and freshness.
- Local inference currently optimized for CPU-first environments unless hardware acceleration configured.

---

## 11. Future Considerations

- Add model version registry and staged rollout support.
- Automate model retraining + offline evaluation pipeline.
- Add feature-store style snapshotting for reproducible training/inference parity.
- Add calibrated confidence mapping for better probability interpretability.
- Explore online reweighting of `alpha` by sample-size confidence.

