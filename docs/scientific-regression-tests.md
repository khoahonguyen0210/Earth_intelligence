# Scientific Regression Tests

This pass checks five properties of the training pipeline: the target
definition, the time split, leakage, metric calculations and
reproducibility metadata. Four of the five already had their own
regression tests. The fifth had a gap: the save, load and metadata
behavior of the production model had no test file. This pass adds those
tests and runs everything else again on the current code.

## Target definition

`forecast/labels.py`: the target is 1 if and only if a qualifying VIIRS
detection (nominal or high confidence; low-confidence `"l"` detections
are excluded) falls in the tile within `(cutoff, cutoff + 24h]`. The
window looks forward and starts strictly after the cutoff, never at or
before it.

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
test_leakage.py           test_label_target_only_reflects_the_forward_window
```

## Time split

`forecast/spec.py` fixes three calendar ranges that do not overlap:
`TRAIN_SPLIT` (2019-2022), `VALIDATION_SPLIT` (2023) and `TEST_SPLIT`
(2024). `split_for_date` maps a cutoff's date to one of them, or to
`None`. `build_dataset.py` sets every row's `split` field this way, never
with a random or per-row split.

```text
test_spec.py              test_split_ranges_are_fixed
                          test_split_ranges_do_not_overlap
                          test_split_for_date_train_boundaries
                          test_split_for_date_validation_boundaries
                          test_split_for_date_test_boundaries
                          test_split_for_date_outside_all_splits_returns_none
                          test_split_for_date_train_validation_gap_is_exact
                          test_split_for_date_validation_test_gap_is_exact
test_leakage.py           test_train_validation_test_splits_partition_every_day_exactly_once
                          test_dates_outside_the_split_range_belong_to_no_split
                          test_no_single_date_matches_more_than_one_split_boundary_directly
test_build_dataset.py     test_build_dataset_assigns_correct_split_per_cutoff
                          test_cutoff_outside_any_split_gets_unassigned_marker
                          test_manifest_split_dates_match_the_spec
```

## Leakage

`ml/tests/forecast/test_leakage.py` collects the leakage tests in one
place. Its docstring maps each required property to the test that
checks it, copied here:

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
score and log loss. Accuracy is left out on purpose, because it is
misleading with this class imbalance. Every metric is checked against an
independent reference, not against itself:

```text
test_metrics.py           test_roc_auc_matches_known_reference_value        (the value documented in sklearn's docstring)
                          test_brier_score_matches_hand_computed_mean_squared_error
                          test_log_loss_matches_independently_computed_formula  (written with math.log, not sklearn)
                          test_positive_rate_and_counts
                          test_single_class_produces_nan_auc_not_a_crash
                          test_all_positive_class_produces_nan_auc_not_a_crash
                          test_extreme_predictions_do_not_produce_infinite_log_loss
                          test_compute_metrics_rejects_mismatched_lengths
                          test_compute_metrics_rejects_empty_input
                          test_metrics_to_dict_is_json_serializable
                          test_save_metrics_roundtrip
test_xgboost_model.py     test_evaluate_xgboost_produces_expected_metrics
test_calibration.py       test_calibration_table_matches_sklearn_calibration_curve
                          test_evaluate_calibration_produces_metrics_and_table
```

## Reproducibility metadata

**The gap.** `models/production_model.py` writes `metadata.json` next to
the pickled model. It holds `model_version`, `calibration_method`,
`best_iteration`, the training `config` (including the fixed
`random_state=20240815` from `xgboost_model.BASE_CONFIG`), summaries of
the train and validation splits (row counts, positive rate and cutoff
range), `trained_at`, and the installed version of every pinned library
(`xgboost`, `scikit-learn`, `numpy`). `load_production_model` refuses to
load if any of these versions have changed.

None of this had its own test file. It was tested only indirectly, and
only when `ml/artifacts/production_model_v1` already existed, through the
`REAL_INPUTS_PRESENT` tests in `query/test_run_forecast.py`. No test
checked that the fixed seed actually reproduces anything.

New: `ml/tests/models/test_production_model.py`, 6 tests:

```text
test_train_production_model_metadata_has_every_reproducibility_field
    every metadata key is present: model_version, calibration_method,
    best_iteration, trained_at, config.random_state (the value that
    BASE_CONFIG used, not a placeholder) and libraries (the installed
    version of every pinned library)
test_train_production_model_split_summaries_match_the_real_rows
    train and validation row counts, positive counts and rate, cutoff
    count, and first and last cutoff all match the input rows
test_save_and_load_production_model_roundtrips_predictions
    saving and loading gives identical predictions, an identical
    calibration table and identical metadata
test_load_production_model_missing_metadata_raises_with_the_retrain_hint
    an empty folder raises FileNotFoundError naming
    train_production_model.py, not a bare stack trace
test_load_production_model_refuses_a_library_version_mismatch
    a metadata.json edited to claim a different numpy version is
    refused with a RuntimeError naming the mismatch; it is never loaded
test_retraining_on_identical_inputs_with_the_fixed_seed_reproduces_predictions
    training twice on the same rows gives byte-identical predictions,
    calibration table and best_iteration, so the fixed random_state
    really does reproduce the model
```

## Results

`.venv/Scripts/python -m pytest ml/tests -q`: **539 passed, 0 failures,
0 skipped**. Before `production_model_v1` was built, 2 tests (the
forecast tests that need the trained model) were skipped; now every test
runs. The count includes the 6 new tests above and an earlier fix in
`test_run_forecast.py` (its trained-model test moved to a cutoff on the
weekly grid).

## Out of scope

- **No new leakage properties.** The checklist in `test_leakage.py`
  already covers every required property. This pass only confirms that
  it still passes on the current code.
- **`harness.py` metadata is not tested here.** `models/harness.py`
  writes its own metadata (config.json and a README) for benchmark runs,
  which `ml/tests/models/test_harness.py` covers. `production_model.py`
  writes a separate, simpler artifact, the one the product serves, and
  that is what the new test file covers.
