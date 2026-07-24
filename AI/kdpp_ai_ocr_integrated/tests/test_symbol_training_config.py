from torchvision import transforms

from apps.symbol.model_io import build_evaluation_transform
from apps.symbol.train_symbol_experiment import build_transforms


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
