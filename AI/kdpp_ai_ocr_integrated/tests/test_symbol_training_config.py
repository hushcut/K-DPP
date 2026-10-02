from torchvision import transforms

from apps.symbol.model_io import build_evaluation_transform
from apps.symbol.train_symbol_experiment import build_transforms, metric_selection_rank


def transform_types(transform: transforms.Compose) -> list[type]:
    return [type(item) for item in transform.transforms]


def test_random_erasing_runs_before_normalization() -> None:
    train_transform, _ = build_transforms()
    types = transform_types(train_transform)

    assert types.index(transforms.RandomErasing) < types.index(
        transforms.Normalize
    )


def test_training_uses_shared_evaluation_transform() -> None:
    _, training_evaluation_transform = build_transforms()
    inference_evaluation_transform = build_evaluation_transform()

    assert transform_types(training_evaluation_transform) == transform_types(
        inference_evaluation_transform
    )


def test_checkpoint_selection_uses_all_class_macro_f1() -> None:
    metrics = {
        "macro_f1_all_classes": 0.5,
        "macro_f1_observed": 1.0,
        "micro_f1": 0.8,
        "exact_match": 0.7,
    }

    rank = metric_selection_rank(metrics, valid_loss=0.2)

    assert rank == (0.5, 0.8, 0.7, -0.2)
