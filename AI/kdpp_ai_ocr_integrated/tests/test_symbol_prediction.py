from io import BytesIO

from PIL import Image
import torch

from apps.symbol import predict_symbol


def image_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (224, 224), "white").save(buffer, format="PNG")
    return buffer.getvalue()


class FixedLogitModel(torch.nn.Module):
    def __init__(self, logits: list[float]):
        super().__init__()
        self.register_buffer(
            "fixed_logits",
            torch.tensor([logits], dtype=torch.float32),
        )

    def forward(self, _tensor):
        return self.fixed_logits


def test_no_symbol_result_does_not_force_argmax(monkeypatch) -> None:
    monkeypatch.setattr(
        predict_symbol,
        "load_model",
        lambda *_args, **_kwargs: (
            FixedLogitModel([-4.0, -3.0]),
            ["wash", "iron"],
            [0.9, 0.9],
        ),
    )
    monkeypatch.setattr(
        predict_symbol,
        "build_evaluation_transform",
        lambda: (lambda _image: torch.zeros((3, 224, 224))),
    )

    result = predict_symbol.predict_symbol_bytes(image_bytes(), device="cpu")

    assert result["status"] == "no_symbol"
    assert result["symbols"] == []
    assert result["symbol_class"] == ""


def test_prediction_uses_each_class_threshold(monkeypatch) -> None:
    monkeypatch.setattr(
        predict_symbol,
        "load_model",
        lambda *_args, **_kwargs: (
            FixedLogitModel([0.0, 3.0]),
            ["wash", "iron"],
            [0.9, 0.9],
        ),
    )
    monkeypatch.setattr(
        predict_symbol,
        "build_evaluation_transform",
        lambda: (lambda _image: torch.zeros((3, 224, 224))),
    )

    result = predict_symbol.predict_symbol_bytes(image_bytes(), device="cpu")

    assert result["status"] == "success"
    assert [item["symbol_class"] for item in result["symbols"]] == ["iron"]

