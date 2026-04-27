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
    def test_hidden_subprocess_kwargs_hide_windows_console(self):
        kwargs = main._hidden_subprocess_kwargs()
        if main.os.name != "nt":
            self.assertEqual(kwargs, {})
            return

        self.assertEqual(kwargs["creationflags"] & main.subprocess.CREATE_NO_WINDOW, main.subprocess.CREATE_NO_WINDOW)
        self.assertTrue(kwargs["startupinfo"].dwFlags & main.subprocess.STARTF_USESHOWWINDOW)

    def test_mosaic_region_object_can_use_masked_shape(self):
        image = Image.new("RGB", (24, 24), "white")
        for x in range(8, 16):
            for y in range(8, 16):
                image.putpixel((x, y), (0, 0, 0))

        result = main.MosaicProcessor.gaussian_blur(image.copy(), (4, 4, 20, 20), radius=4, shape="ellipse")

        self.assertEqual(result.getpixel((4, 4)), image.getpixel((4, 4)), "ellipse mask should preserve box corners")
        self.assertNotEqual(result.getpixel((12, 8)), image.getpixel((12, 8)), "inside of the ellipse should be blurred")

    def test_mosaic_region_object_can_use_triangle_shape(self):
        image = Image.new("RGB", (24, 24), "white")
        for x in range(8, 16):
            for y in range(8, 16):
                image.putpixel((x, y), (0, 0, 0))

        result = main.MosaicProcessor.gaussian_blur(image.copy(), (4, 4, 20, 20), radius=4, shape="triangle")

        self.assertEqual(result.getpixel((4, 4)), image.getpixel((4, 4)), "triangle mask should preserve box corners")
        self.assertNotEqual(result.getpixel((12, 12)), image.getpixel((12, 12)), "inside of the triangle should be blurred")

    def test_mosaic_region_object_can_use_brush_shape(self):
        image = Image.new("RGB", (24, 24), "white")
        for x in range(0, 12):
            for y in range(24):
                image.putpixel((x, y), (0, 0, 0))

        result = main.MosaicProcessor.gaussian_blur(
            image.copy(),
            (2, 8, 22, 16),
            radius=4,
            shape="brush",
            points=[(2, 12), (22, 12)],
            brush_size=6,
        )

        self.assertEqual(result.getpixel((12, 2)), image.getpixel((12, 2)), "brush mask should preserve pixels away from the stroke")
        self.assertNotEqual(result.getpixel((12, 12)), image.getpixel((12, 12)), "pixels under the brush stroke should be blurred")

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
