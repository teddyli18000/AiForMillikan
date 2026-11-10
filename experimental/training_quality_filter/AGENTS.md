# AGENTS.md

## Project Context

This project is a Millikan oil drop experiment analysis system.

The training-related subsystem is responsible only for trajectory quality filtering after the video-processing module has already extracted oil-drop trajectories.

The agent must not design this subsystem as an end-to-end deep learning model that directly predicts electric charge from video.

Correct responsibility:

```text
trajectory data
→ trajectory features
→ quality scoring
→ filtering decision
→ report
```

Incorrect responsibility:

```text
raw video
→ neural network
→ predicted charge q
```

The electric charge q must be computed by physics-based inversion formulas in the main algorithm, not learned as a black-box prediction target.

---

## Main Design Principle

Use a physics-informed, label-free or weakly supervised quality filtering pipeline.

Preferred methods:

```text
hard-rule filtering
+ feature engineering
+ unsupervised anomaly detection
+ physics consistency scoring
+ optional weak supervision from pseudo-labels
```

Avoid:

```text
manual frame-by-frame labeling
manual good/bad trajectory labeling as a required dependency
CNN / YOLO / Transformer as the first solution
direct q prediction
black-box decisions without explanation
```

The model should answer:

```text
Is this trajectory reliable enough for q inversion?
```

not:

```text
What is the charge of this oil drop?
```

---

## Scope Boundary

All training-related work must stay inside:

```text
training_quality_filter/
```

Do not modify unrelated project files unless explicitly requested.

Allowed files and folders:

```text
training_quality_filter/
├── README.md
├── configs/
├── data/
├── src/
├── scripts/
├── tests/
└── pyproject.toml
```

If upstream or downstream changes are necessary, write a clear interface proposal instead of editing other modules directly.

---

## Expected Data Contract

The training subsystem consumes trajectory data exported by the video-processing module.

Preferred input file:

```text
tracks.parquet
```

Acceptable alternative:

```text
tracks.csv
```

Each row should represent one observation of one oil drop in one video frame.

Required columns:

```text
video_id
track_id
frame_idx
time_s
x_px
y_px
voltage_V
platform_id
```

Optional but recommended columns:

```text
radius_px
area_px
brightness
is_valid_detection
```

Do not assume raw video access inside this subsystem.

Do not require image labels, bounding-box labels, segmentation masks, or manually assigned good / bad labels.

---

## Output Contract

The subsystem must output a trajectory-level scoring table.

Required output file:

```text
training_quality_filter/data/reports/quality_scores.parquet
```

Required columns:

```text
video_id
track_id
quality_score
keep
reject_reasons
hard_rule_score
physics_quality_score
unsupervised_score
```

Optional columns:

```text
weak_model_score
pseudo_label
pseudo_label_confidence
q_cv
speed_fit_r2_min
speed_fit_rmse_mean
track_length
missing_frame_ratio
```

Also generate:

```text
training_quality_filter/data/reports/quality_report.json
training_quality_filter/data/reports/quality_report.html
```

The report must explain why trajectories were kept or rejected.

---

## Folder Structure

Use this structure:

```text
training_quality_filter/
├── README.md
├── configs/
│   └── default.yaml
├── data/
│   ├── input/
│   ├── interim/
│   ├── features/
│   ├── models/
│   └── reports/
├── src/
│   └── qfilter/
│       ├── __init__.py
│       ├── schema.py
│       ├── features.py
│       ├── physics.py
│       ├── rules.py
│       ├── weak_labels.py
│       ├── unsupervised.py
│       ├── train.py
│       ├── score.py
│       ├── report.py
│       └── utils.py
├── scripts/
│   ├── extract_features.py
│   ├── train_unsupervised.py
│   ├── train_weak_model.py
│   ├── score_tracks.py
│   └── generate_report.py
├── tests/
│   ├── test_schema.py
│   ├── test_features.py
│   ├── test_rules.py
│   └── test_scoring.py
└── pyproject.toml
```

---

## Module Responsibilities

### `schema.py`

Define and validate the input and output schemas.

Responsibilities:

```text
validate required columns
validate numeric types
validate missing values
validate time ordering within each track
validate platform_id consistency
```

The code should fail early with clear error messages if the input data contract is violated.

---

### `features.py`

Convert frame-level trajectory data into track-level features.

Feature groups:

```text
trajectory completeness
motion stability
velocity fitting quality
morphology stability
voltage-platform coverage
physical consistency
```

Each output row must represent exactly one trajectory:

```text
(video_id, track_id)
```

---

### `physics.py`

Implement physics-related helper functions.

Responsibilities:

```text
fit velocity within voltage platforms
estimate q per platform or platform pair if enough information exists
compute q consistency metrics
compute physics residual metrics
```

Important:

Do not hard-code final apparatus constants unless they are placed in `configs/default.yaml`.

Any physical constant must come from config or function arguments.

---

### `rules.py`

Implement deterministic hard rules.

Responsibilities:

```text
reject too-short tracks
reject tracks with too many missing frames
reject tracks covering too few voltage platforms
reject tracks with unstable velocity fitting
reject tracks with excessive horizontal drift
reject tracks with unstable morphology if morphology features exist
```

Rules should output both:

```text
hard_rule_pass
hard_rule_reasons
```

Never silently reject a trajectory without a reason.

---

### `unsupervised.py`

Implement unsupervised anomaly detection.

Default model:

```text
RobustScaler + IsolationForest
```

Optional models:

```text
LocalOutlierFactor
OneClassSVM
```

The first implementation should prefer stability and interpretability over complexity.

Output:

```text
unsupervised_score
```

Normalize the score to:

```text
0 = very bad
1 = very good
```

---

### `weak_labels.py`

Generate pseudo-labels from strict high-confidence rules.

Allowed labels:

```text
good
bad
uncertain
```

Only high-confidence good and high-confidence bad samples should be used for weak model training.

Do not treat uncertain samples as negative.

---

### `train.py`

Train and save models.

Responsibilities:

```text
load features
apply preprocessing
train unsupervised model
optionally train weak supervised model if enough pseudo-labels exist
save model artifacts
save training metadata
```

If pseudo-label count is too small, skip weak model training and continue with the unsupervised pipeline.

Do not fail the full pipeline just because weak training is unavailable.

---

### `score.py`

Combine all scores into final trajectory quality score.

Recommended initial formula:

```text
quality_score =
    0.30 * hard_rule_score
  + 0.50 * physics_quality_score
  + 0.20 * unsupervised_score
```

If weak model score exists, use:

```text
quality_score =
    0.25 * hard_rule_score
  + 0.40 * physics_quality_score
  + 0.20 * unsupervised_score
  + 0.15 * weak_model_score
```

The final decision:

```text
keep = quality_score >= threshold and hard_rule_pass == true
```

Default threshold should be configurable.

---

### `report.py`

Generate machine-readable and human-readable reports.

Required report content:

```text
number of total tracks
number of kept tracks
number of rejected tracks
retention rate
reject reason counts
quality score distribution
feature summary
q consistency summary if q features exist
before / after filtering comparison
```

The report should support debugging and presentation.

---

## Configuration

Use:

```text
training_quality_filter/configs/default.yaml
```

All thresholds and constants must be configurable.

Suggested config fields:

```yaml
input:
  tracks_path: "data/input/tracks.parquet"

output:
  features_path: "data/features/track_features.parquet"
  scores_path: "data/reports/quality_scores.parquet"
  report_json_path: "data/reports/quality_report.json"
  report_html_path: "data/reports/quality_report.html"
  model_dir: "data/models"

rules:
  min_track_length: 30
  min_duration_s: 1.0
  min_num_platforms: 2
  max_missing_frame_ratio: 0.2
  min_speed_fit_r2: 0.90
  max_q_cv: 0.30
  max_horizontal_drift_ratio: 0.30

scoring:
  quality_threshold: 0.60
  weights_without_weak_model:
    hard_rule_score: 0.30
    physics_quality_score: 0.50
    unsupervised_score: 0.20
  weights_with_weak_model:
    hard_rule_score: 0.25
    physics_quality_score: 0.40
    unsupervised_score: 0.20
    weak_model_score: 0.15

model:
  random_seed: 42
  isolation_forest:
    n_estimators: 300
    contamination: "auto"
  weak_model:
    min_good_samples: 20
    min_bad_samples: 20
```

---

## Coding Standards

Use Python.

Preferred libraries:

```text
pandas
numpy
scipy
scikit-learn
pydantic or pandera
pyarrow
joblib
matplotlib
pytest
```

Do not introduce heavy dependencies unless necessary.

Avoid:

```text
deep learning frameworks
GPU-only dependencies
large model checkpoints
internet-required runtime behavior
```

All scripts must run offline.

---

## Reproducibility Requirements

Every training run must record:

```text
timestamp
input file path
input file hash if feasible
config used
model parameters
random seed
number of tracks
number of kept tracks
number of rejected tracks
```

Save metadata to:

```text
training_quality_filter/data/models/training_metadata.json
```

Use fixed random seeds where applicable.

---

## Testing Requirements

Add tests for:

```text
schema validation
feature extraction on synthetic toy tracks
hard-rule rejection reasons
score range between 0 and 1
stable behavior when optional columns are missing
```

Minimum expected test command:

```bash
pytest training_quality_filter/tests
```

---

## CLI Expectations

Provide script-level entry points.

Expected commands:

```bash
python training_quality_filter/scripts/extract_features.py --config training_quality_filter/configs/default.yaml
python training_quality_filter/scripts/train_unsupervised.py --config training_quality_filter/configs/default.yaml
python training_quality_filter/scripts/train_weak_model.py --config training_quality_filter/configs/default.yaml
python training_quality_filter/scripts/score_tracks.py --config training_quality_filter/configs/default.yaml
python training_quality_filter/scripts/generate_report.py --config training_quality_filter/configs/default.yaml
```

A later version may add one pipeline script:

```bash
python training_quality_filter/scripts/run_pipeline.py --config training_quality_filter/configs/default.yaml
```

---

## Quality Bar

The solution is acceptable only if:

```text
it does not require manual labels
it does not predict q directly
it outputs explainable keep / reject decisions
it preserves physics-based reasoning
it can run on local Windows environment
it produces reports useful for debugging and presentation
```

The filtering result should improve at least one of the following after filtering:

```text
lower velocity fitting residuals
lower q consistency error
clearer q distribution structure
more stable estimated elementary charge e
```

If filtering does not improve physical consistency, the agent must report that honestly instead of claiming success.

---

## Forbidden Claims

Do not claim:

```text
the model has learned the true physical law
the model can replace Millikan oil drop formulas
the model can accurately predict charge without physical inversion
the model is supervised if no human labels exist
the model is deep learning if only classical ML is used
```

Preferred description:

```text
physics-informed trajectory quality scoring
unsupervised anomaly detection
weak supervision from high-confidence physical rules
automatic filtering of unreliable oil-drop trajectories
```

---

## Development Priority

Implement in this order:

1. Data schema validation.
2. Track-level feature extraction.
3. Hard-rule filtering.
4. Physics consistency scoring.
5. Isolation Forest anomaly detection.
6. Final quality score fusion.
7. Report generation.
8. Weak pseudo-label model.
9. Feature importance and visualization.
10. Integration with q inversion pipeline.

Do not start with neural networks.

Do not optimize prematurely.

Prefer a correct, explainable, reproducible baseline over a complex model.
