from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class MultiLabelMetrics:
    sample_count: int
    exact_match: float
    hamming_accuracy: float
    micro_precision: float
    micro_recall: float
    micro_f1: float
    macro_f1_observed: float
    per_class: tuple[dict[str, float | int], ...]

    def to_dict(self) -> dict:
        return {
            "sample_count": self.sample_count,
            "exact_match": self.exact_match,
            "hamming_accuracy": self.hamming_accuracy,
            "micro_precision": self.micro_precision,
            "micro_recall": self.micro_recall,
            "micro_f1": self.micro_f1,
            "macro_f1_observed": self.macro_f1_observed,
            "per_class": list(self.per_class),
        }


def _as_binary_matrix(values: np.ndarray | Iterable) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 2:
        raise ValueError("멀티라벨 값은 [샘플, 클래스] 형태여야 합니다.")
    return (array > 0).astype(np.uint8)


def _threshold_array(
    thresholds: float | Iterable[float],
    num_classes: int,
) -> np.ndarray:
    values = np.asarray(thresholds, dtype=np.float64)
    if values.ndim == 0:
        values = np.repeat(values, num_classes)
    if values.shape != (num_classes,):
        raise ValueError(
            f"임계값 수({values.size})와 클래스 수({num_classes})가 다릅니다."
        )
    if np.any((values < 0.0) | (values > 1.0)):
        raise ValueError("임계값은 0과 1 사이여야 합니다.")
    return values


def apply_thresholds(
    probabilities: np.ndarray | Iterable,
    thresholds: float | Iterable[float],
) -> np.ndarray:
    probs = np.asarray(probabilities, dtype=np.float64)
    if probs.ndim != 2:
        raise ValueError("확률은 [샘플, 클래스] 형태여야 합니다.")
    values = _threshold_array(thresholds, probs.shape[1])
    return (probs >= values.reshape(1, -1)).astype(np.uint8)


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def compute_multilabel_metrics(
    targets: np.ndarray | Iterable,
    predictions: np.ndarray | Iterable,
) -> MultiLabelMetrics:
    truth = _as_binary_matrix(targets)
    predicted = _as_binary_matrix(predictions)
    if truth.shape != predicted.shape:
        raise ValueError("정답과 예측 배열 크기가 다릅니다.")
    if truth.shape[0] == 0:
        raise ValueError("평가할 샘플이 없습니다.")

    tp = np.sum((truth == 1) & (predicted == 1), axis=0)
    fp = np.sum((truth == 0) & (predicted == 1), axis=0)
    fn = np.sum((truth == 1) & (predicted == 0), axis=0)
    tn = np.sum((truth == 0) & (predicted == 0), axis=0)

    per_class: list[dict[str, float | int]] = []
    observed_f1: list[float] = []
    for class_index in range(truth.shape[1]):
        precision = _safe_divide(
            float(tp[class_index]),
            float(tp[class_index] + fp[class_index]),
        )
        recall = _safe_divide(
            float(tp[class_index]),
            float(tp[class_index] + fn[class_index]),
        )
        f1 = _safe_divide(2.0 * precision * recall, precision + recall)
        support = int(tp[class_index] + fn[class_index])
        predicted_positive = int(tp[class_index] + fp[class_index])
        if support or predicted_positive:
            observed_f1.append(f1)
        per_class.append(
            {
                "tp": int(tp[class_index]),
                "fp": int(fp[class_index]),
                "fn": int(fn[class_index]),
                "tn": int(tn[class_index]),
                "support": support,
                "predicted_positive": predicted_positive,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }
        )

    total_tp = float(np.sum(tp))
    total_fp = float(np.sum(fp))
    total_fn = float(np.sum(fn))
    micro_precision = _safe_divide(total_tp, total_tp + total_fp)
    micro_recall = _safe_divide(total_tp, total_tp + total_fn)
    micro_f1 = _safe_divide(
        2.0 * micro_precision * micro_recall,
        micro_precision + micro_recall,
    )

    return MultiLabelMetrics(
        sample_count=truth.shape[0],
        exact_match=float(np.mean(np.all(truth == predicted, axis=1))),
        # This number is diagnostic only. It is dominated by true negatives
        # when the class set is sparse and must not be used as headline accuracy.
        hamming_accuracy=float(np.mean(truth == predicted)),
        micro_precision=micro_precision,
        micro_recall=micro_recall,
        micro_f1=micro_f1,
        macro_f1_observed=(
            float(np.mean(observed_f1)) if observed_f1 else 0.0
        ),
        per_class=tuple(per_class),
    )


def tune_class_thresholds(
    probabilities: np.ndarray | Iterable,
    targets: np.ndarray | Iterable,
    *,
    default_threshold: float = 0.5,
    min_positive_samples: int = 2,
) -> list[float]:
    probs = np.asarray(probabilities, dtype=np.float64)
    truth = _as_binary_matrix(targets)
    if probs.shape != truth.shape:
        raise ValueError("검증 확률과 정답 배열 크기가 다릅니다.")

    candidates = np.arange(0.10, 0.951, 0.05)
    thresholds: list[float] = []
    for class_index in range(truth.shape[1]):
        class_truth = truth[:, class_index]
        positives = int(np.sum(class_truth))
        if positives == 0:
            # The validation split contains no evidence for this class.
            # Suppress it instead of selecting a threshold from true negatives.
            thresholds.append(1.0)
            continue
        if positives < min_positive_samples:
            thresholds.append(float(default_threshold))
            continue

        best_threshold = float(default_threshold)
        best_rank = (-1.0, -1.0, -1.0)
        for threshold in candidates:
            class_pred = probs[:, class_index] >= threshold
            tp = int(np.sum((class_truth == 1) & class_pred))
            fp = int(np.sum((class_truth == 0) & class_pred))
            fn = int(np.sum((class_truth == 1) & ~class_pred))
            precision = _safe_divide(tp, tp + fp)
            recall = _safe_divide(tp, tp + fn)
            f1 = _safe_divide(2.0 * precision * recall, precision + recall)
            # Prefer precision, then the higher threshold, on an F1 tie.
            rank = (round(f1, 12), round(precision, 12), float(threshold))
            if rank > best_rank:
                best_rank = rank
                best_threshold = float(round(threshold, 2))
        thresholds.append(best_threshold)

    return thresholds
