# Scientific Regression Tests — LOCKED

This document records the Task 15.4 scientific regression test pass,
the fourth task of Phase 15. It is not a brainstorming document.

Task 15.4 asks for five properties of the training pipeline to be
verified: target definition, temporal split, leakage checks, metric
calculations, reproducibility metadata. Four of the five already had
dedicated regression coverage from Phase 3/4 (the training pipeline's
own build phases); this task's own work was finding and closing the
one real gap -- the production model's save/load/metadata contract had
no test file of its own -- and re-running everything else to confirm it
still holds on the current code.

## Target definition

`forecast/labels.py`: the target is 1 iff a qualifying VIIRS detection
(nominal or high confidence; low-confidence `"l"` detections excluded)
falls in the tile within `(cutoff, cutoff + 24h]` -- a forward-looking
window that starts strictly after the cutoff, never at or before it.

```text
test_labels.py            test_is_qualifying_observation_accepts_nominal_and_high_confidence
                           test_is_qualifying_observation_rejects_low_confidence
                           test_is_qualifying_observation_accepts_missing_confidence
                           test_is_qualifying_observation_rejects_invalid_coordinates
                           test_is_qualifying_observation_rejects_naive_timestamp
                           test_construct_labels_positive_example
                           test_construct_labels_negative_example_no_observations
                           test_construct_labels_excludes_observation_exactly_at_cutoff
                           test_construct_labels_includes_observation_exactly_at_window_end
                           test_construct_labels_excludes_observation_just_after_window_end
                           test_construct_labels_excludes_low_confidence_observation
test_leakage.py            test_label_target_only_reflects_the_forward_window
```

## Temporal split

`forecast/spec.py` locks three non-overlapping calendar ranges --
`TRAIN_SPLIT` (2019-2022), `VALIDATION_SPLIT` (2023), `TEST_SPLIT`
(2024) -- and `split_for_date` maps a cutoff's date into one of them or
`None`. `build_dataset.py` assigns every row's `split` field this way,
never a random or row-level split.

```text
test_spec.py               test_split_ranges_are_locked
                            test_split_ranges_do_not_overlap
                            test_split_for_date_train_boundaries
                            test_split_for_date_validation_boundaries
                            test_split_for_date_test_boundaries
                            test_split_for_date_outside_all_splits_returns_none
                            test_split_for_date_train_validation_gap_is_exact
                            test_split_for_date_validation_test_gap_is_exact
test_leakage.py             test_train_validation_test_splits_partition_every_day_exactly_once
                            test_dates_outside_the_locked_range_belong_to_no_split
                            test_no_single_date_matches_more_than_one_split_boundary_directly
test_build_dataset.py       test_build_dataset_assigns_correct_split_per_cutoff
                            test_cutoff_outside_any_split_gets_unassigned_marker
                            test_manifest_split_dates_match_locked_spec
```

## Leakage checks

`ml/tests/forecast/test_leakage.py` is Task 3.6's own consolidated
leakage-safety suite; its docstring is already a checklist mapping each
handbook item to the test that proves it, reproduced here for a single
place to look:

```text
future timestamps excluded          test_fire_history_features_never_uses_future_timestamps
                                     test_environmental_features_never_uses_future_timestamps
future target excluded              test_label_target_never_uses_observations_at_or_before_cutoff
train/validation/test do not        test_train_validation_test_splits_partition_every_day_exactly_once
  overlap
feature windows stop at cutoff      test_fire_history_windows_never_extend_past_cutoff
                                     test_environmental_feature_never_uses_record_after_cutoff
learned preprocessing uses          test_preprocessing.py::
  training data only                  test_transform_uses_train_statistics_not_the_input_rows_own_distribution
test set never influences           test_xgboost_model.py::
  model selection                     test_evaluate_xgboost_does_not_use_test_targets_to_select_config
```

## Metric calculations

`models/metrics.py::compute_metrics` reports PR-AUC, ROC-AUC, Brier
score, and log loss (accuracy deliberately excluded -- PROJECT_BIBLE
§6, wrong for this class imbalance). Every metric is checked against an
independent reference, not just against itself:

```text
test_metrics.py            test_roc_auc_matches_known_reference_value        (sklearn docstring's own documented value)
                            test_brier_score_matches_hand_computed_mean_squared_error
                            test_log_loss_matches_independently_computed_formula  (hand-rolled via math.log, not sklearn)
                            test_positive_rate_and_counts
                            test_single_class_produces_nan_auc_not_a_crash
                            test_all_positive_class_produces_nan_auc_not_a_crash
                            test_extreme_predictions_do_not_produce_infinite_log_loss
                            test_compute_metrics_rejects_mismatched_lengths
                            test_compute_metrics_rejects_empty_input
                            test_metrics_to_dict_is_json_serializable
                            test_save_metrics_roundtrip
test_xgboost_model.py      test_evaluate_xgboost_produces_locked_metrics
test_calibration.py        test_calibration_table_matches_sklearn_calibration_curve
                            test_evaluate_calibration_produces_metrics_and_table
```

## Reproducibility metadata

**The gap this task closes.** `models/production_model.py` writes
`metadata.json` alongside the pickled model -- `model_version`,
`calibration_method`, `best_iteration`, the training `config` (including
the fixed `random_state=20240815` from `xgboost_model.BASE_CONFIG`),
per-split summaries (row counts, positive rate, cutoff range) for both
train and validation, `trained_at`, and the exact installed versions of
every pinned library (`xgboost`, `scikit-learn`, `numpy`) --
`load_production_model` refuses to load if any of those have since
changed. None of this had a test file before this task; it was only
ever touched indirectly, and only when `ml/artifacts/production_model_v1`
happened to already exist on disk, through
`query/test_run_forecast.py`'s `REAL_INPUTS_PRESENT`-gated tests. There
was also no test that the fixed seed actually reproduces anything.

New: `ml/tests/models/test_production_model.py`, 6 tests:

```text
test_train_production_model_metadata_has_every_reproducibility_field
    every metadata key present: model_version, calibration_method,
    best_iteration, trained_at, config.random_state (the real value
    BASE_CONFIG used, not a placeholder), libraries (every pinned
    library's real installed version)
test_train_production_model_split_summaries_match_the_real_rows
    train/validation row counts, positive counts/rate, cutoff count,
    first/last cutoff all match the actual input rows
test_save_and_load_production_model_roundtrips_predictions
    save then load reproduces identical predictions, an identical
    calibration table, and identical metadata
test_load_production_model_missing_metadata_raises_with_the_retrain_hint
    an empty directory raises FileNotFoundError naming
    train_production_model.py, not a bare stack trace
test_load_production_model_refuses_a_library_version_mismatch
    a metadata.json edited to claim a different numpy version is
    refused with a RuntimeError naming the mismatch, never silently
    loaded
test_retraining_on_identical_inputs_with_the_fixed_seed_reproduces_predictions
    training twice on the same rows produces byte-identical
    predictions, calibration table, and best_iteration -- the fixed
    random_state genuinely reproduces, not just documents an intent
```

## Results

`.venv/Scripts/python -m pytest ml/tests -q`: **539 passed, 0 failures,
0 skipped** (previously 2 skipped -- the real-model forecast tests --
before `production_model_v1` existed; Task 15.3 built that model, so
every test in the suite now runs for real). Includes the 6 new
`test_production_model.py` tests above and the fix from Task 15.3
(`test_run_forecast.py`'s real-model test moved to an on-grid cutoff).

## What this task does not do

- **Does not add new leakage properties.** `test_leakage.py`'s own
  checklist from Task 3.6 already covers every property the handbook
  asks for; this task only re-confirms it still passes on the current
  code, it does not extend the checklist.
- **Does not test `harness.py`'s own metadata/config.json separately.**
  `models/harness.py` writes a parallel metadata artifact (config.json
  plus a README) for benchmark runs, already covered by
  `ml/tests/models/test_harness.py`; `production_model.py` is a
  separate, simpler artifact (the one the product actually serves) and
  is what this task's new test file targets.
