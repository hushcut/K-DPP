"""PaddleOCR 추론 모델을 ONNX로 바꾸고 OpenVINO가 읽는지 확인한다.

experiments/igpu/paddle_convert/venv에서 실행한다. paddle2onnx가 Windows에서 Paddle 3.0.0을 막아서
변환에만 Paddle 3.1.1을 쓴다. 실행 환경(experiments/igpu/paddle/venv)은 기존과 같은 3.0.0이다.
"""
import subprocess
import sys
from pathlib import Path

import openvino as ov

PADDLE = Path(__file__).resolve().parents[2] / "paddleocr"
MODELS = ("PP-OCRv5_server_det", "korean_PP-OCRv5_mobile_rec")
OPSET = "11"


def main():
    target = PADDLE / "models" / "onnx"
    target.mkdir(parents=True, exist_ok=True)
    core = ov.Core()
    for name in MODELS:
        output = target / f"{name}.onnx"
        if output.exists():
            raise FileExistsError(f"이미 변환한 파일을 덮어쓰지 않습니다: {output}")
        subprocess.run(
            [str(Path(sys.executable).with_name("paddle2onnx.exe")),
             "--model_dir", str(PADDLE / "models" / "base" / f"{name}_infer"),
             "--model_filename", "inference.json", "--params_filename", "inference.pdiparams",
             "--save_file", str(output), "--opset_version", OPSET],
            check=True,
        )
        model = core.read_model(str(output))
        print(name, output.stat().st_size, "입력", [str(i.get_partial_shape()) for i in model.inputs],
              "출력", [str(o.get_partial_shape()) for o in model.outputs], flush=True)


if __name__ == "__main__":
    main()
