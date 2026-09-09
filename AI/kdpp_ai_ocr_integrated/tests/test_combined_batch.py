from scripts import run_combined_batch


def test_combined_batch_does_not_load_symbol_runtime_without_the_option(monkeypatch) -> None:
    def unavailable_runtime():
        raise AssertionError("symbol runtime must stay unloaded")

    monkeypatch.setattr(run_combined_batch, "load_symbol_runtime", unavailable_runtime)

    predictor, model_path = run_combined_batch.configure_symbol_runtime(
        include_symbol_crops=False,
        requested_model_path="",
    )

    assert predictor is None
    assert model_path == ""


def test_combined_batch_loads_default_model_only_for_symbol_crops(monkeypatch) -> None:
    marker = object()
    monkeypatch.setattr(
        run_combined_batch,
        "load_symbol_runtime",
        lambda: ("models/default.pt", marker),
    )

    predictor, model_path = run_combined_batch.configure_symbol_runtime(
        include_symbol_crops=True,
        requested_model_path="",
    )

    assert predictor is marker
    assert model_path == "models/default.pt"
