import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import main


class _FakeWatermarkProcessor:
    def __init__(self, config=None):
        self.config = config or {}

    def process(self, input_path, output_path):
        with Image.open(input_path) as image:
            image.convert("RGB").save(output_path, "JPEG", quality=95)
        return output_path


class BatchProcessRegressionTests(unittest.TestCase):
    def test_batch_process_uses_actual_output_extension_and_keeps_source_file(self):
        with tempfile.TemporaryDirectory() as input_dir_name, tempfile.TemporaryDirectory() as output_dir_name:
            input_dir = Path(input_dir_name)
            output_dir = Path(output_dir_name)
            source_path = input_dir / "sample.png"
            Image.new("RGBA", (8, 8), (255, 0, 0, 128)).save(source_path, "PNG")

            with patch.object(main, "WatermarkProcessor", _FakeWatermarkProcessor):
                main.batch_process(
                    input_dir,
                    output_dir,
                    watermark_config={"text": "KH38MT"},
                    order=["watermark"],
                )

            output_path = output_dir / "sample.jpg"
            self.assertTrue(output_path.exists(), "expected batch output to follow the actual JPEG format")
            self.assertTrue(source_path.exists(), "source image should stay in the input directory")
            self.assertFalse((output_dir / "sample.png").exists(), "output should not keep the stale source suffix")

            with Image.open(output_path) as output_image:
                self.assertEqual(output_image.format, "JPEG")


if __name__ == "__main__":
    unittest.main()
