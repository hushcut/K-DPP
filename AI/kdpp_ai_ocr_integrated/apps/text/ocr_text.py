import os

from google.cloud import vision


def run_ocr(image_path: str, credential_path: str = "key.json") -> str:
    if credential_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credential_path

    client = vision.ImageAnnotatorClient()

    with open(image_path, "rb") as image_file:
        content = image_file.read()

    response = client.text_detection(image=vision.Image(content=content))
    if response.error.message:
        raise RuntimeError(response.error.message)

    texts = response.text_annotations
    return texts[0].description if texts else ""

