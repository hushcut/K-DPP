import numpy as np
import pytest

from apps.symbol.metrics import (
    apply_thresholds,
    compute_multilabel_metrics,
    tune_class_thresholds,
)


def test_multilabel_metrics_do_not_hide_errors_behind_true_negatives() -> None:
    truth = np.array([[1, 0, 0], [0, 1, 0]], dtype=np.uint8)
    predicted = np.array([[1, 0, 0], [0, 0, 0]], dtype=np.uint8)

    metrics = compute_multilabel_metrics(truth, predicted)

    assert metrics.exact_match == pytest.approx(0.5)
    assert metrics.hamming_accuracy == pytest.approx(5 / 6)
    assert metrics.micro_precision == pytest.approx(1.0)
    assert metrics.micro_recall == pytest.approx(0.5)
    assert metrics.micro_f1 == pytest.approx(2 / 3)


def test_all_class_macro_f1_includes_validation_absent_classes() -> None:
    truth = np.array([[1, 0], [1, 0]], dtype=np.uint8)
    predicted = np.array([[1, 0], [1, 0]], dtype=np.uint8)

    metrics = compute_multilabel_metrics(truth, predicted)

    assert metrics.macro_f1_observed == pytest.approx(1.0)
    assert metrics.macro_f1_all_classes == pytest.approx(0.5)
    assert metrics.class_count == 2
    assert metrics.supported_class_count == 1


def test_threshold_application_validates_class_count() -> None:
    with pytest.raises(ValueError):
        apply_thresholds([[0.5, 0.6]], [0.5])


def test_threshold_tuning_suppresses_class_absent_from_validation() -> None:
    probabilities = np.array(
        [[0.9, 0.8], [0.8, 0.7], [0.1, 0.6]],
        dtype=np.float64,
    )
    truth = np.array([[1, 0], [1, 0], [0, 0]], dtype=np.uint8)

    thresholds = tune_class_thresholds(probabilities, truth)

    assert thresholds[0] >= 0.1
    assert thresholds[1] == 1.0

