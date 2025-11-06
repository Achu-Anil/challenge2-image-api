"""
Unit tests for image processing functions.

Tests the colormap LUT creation, LUT application, and resize functions
with deterministic inputs and expected outputs.
"""

import base64
from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from app.processing.image import (
    apply_lut,
    encode_to_png,
    make_colormap_lut,
    resize_grayscale_row,
)


class TestColormapLUT:
    """Test colormap lookup table creation."""

    def test_lut_shape(self):
        """LUT should have 256 entries with RGB triples."""
        lut = make_colormap_lut()

        assert lut.shape == (256, 3)
        assert lut.dtype == np.uint8

    def test_lut_range(self):
        """All LUT values should be in valid RGB range [0, 255]."""
        lut = make_colormap_lut()

        assert np.all(lut >= 0)
        assert np.all(lut <= 255)

    def test_lut_specific_values(self):
        """Test specific grayscale values map to expected RGB colors."""
        lut = make_colormap_lut()

        # Value 0 (minimum) should be dark blue
        rgb_0 = lut[0]
        assert rgb_0[2] > rgb_0[0]  # Blue > Red
        assert rgb_0[2] > rgb_0[1]  # Blue > Green

        # Value 255 (maximum) should be red/orange
        rgb_255 = lut[255]
        assert rgb_255[0] > rgb_255[2]  # Red > Blue

        # Mid values should show smooth gradient
        # Check that colors change smoothly
        for i in range(0, 250, 10):
            color1 = lut[i]
            color2 = lut[i + 10]
            # At least one channel should change
            assert not np.array_equal(color1, color2)

    def test_lut_monotonicity(self):
        """LUT should show general progression from blue to red."""
        lut = make_colormap_lut()

        # Red channel should generally increase
        red_start = np.mean(lut[0:50, 0])
        red_end = np.mean(lut[200:256, 0])
        assert red_end > red_start

        # Blue channel should generally decrease
        blue_start = np.mean(lut[0:50, 2])
        blue_end = np.mean(lut[200:256, 2])
        assert blue_end < blue_start

    def test_lut_deterministic(self):
        """LUT creation should be deterministic."""
        lut1 = make_colormap_lut()
        lut2 = make_colormap_lut()

        np.testing.assert_array_equal(lut1, lut2)


class TestApplyColormapLUT:
    """Test applying colormap LUT to grayscale data."""

    @pytest.fixture
    def lut(self):
        """Create LUT for tests."""
        return make_colormap_lut()

    def test_apply_lut_shape(self, lut):
        """Output should have correct shape (H, W, 3)."""
        gray = np.array([[0, 128, 255]], dtype=np.uint8)

        rgb = apply_lut(gray, lut)

        assert rgb.shape == (1, 3, 3)  # (H, W, 3)
        assert rgb.dtype == np.uint8

    def test_apply_lut_known_values(self, lut):
        """Test specific grayscale values map correctly."""
        # Test value 0 (black -> dark blue)
        gray = np.array([[0]], dtype=np.uint8)
        rgb = apply_lut(gray, lut)

        expected_rgb = lut[0]
        np.testing.assert_array_equal(rgb[0, 0], expected_rgb)

        # Test value 255 (white -> red/orange)
        gray = np.array([[255]], dtype=np.uint8)
        rgb = apply_lut(gray, lut)

        expected_rgb = lut[255]
        np.testing.assert_array_equal(rgb[0, 0], expected_rgb)

        # Test value 128 (mid gray -> green/yellow)
        gray = np.array([[128]], dtype=np.uint8)
        rgb = apply_lut(gray, lut)

        expected_rgb = lut[128]
        np.testing.assert_array_equal(rgb[0, 0], expected_rgb)

    def test_apply_lut_multiple_values(self, lut):
        """Test applying LUT to multiple grayscale values."""
        gray = np.array([[0, 64, 128, 192, 255]], dtype=np.uint8)

        rgb = apply_lut(gray, lut)

        # Verify each pixel maps correctly
        for i, gray_val in enumerate([0, 64, 128, 192, 255]):
            expected_rgb = lut[gray_val]
            np.testing.assert_array_equal(rgb[0, i], expected_rgb)

    def test_apply_lut_2d_input(self, lut):
        """Test LUT application on 2D grayscale array."""
        gray = np.array(
            [
                [0, 128, 255],
                [64, 192, 32],
            ],
            dtype=np.uint8,
        )

        rgb = apply_lut(gray, lut)

        assert rgb.shape == (2, 3, 3)  # (2 rows, 3 cols, 3 channels)

        # Verify a few pixels
        np.testing.assert_array_equal(rgb[0, 0], lut[0])
        np.testing.assert_array_equal(rgb[0, 1], lut[128])
        np.testing.assert_array_equal(rgb[1, 0], lut[64])

    def test_apply_lut_preserves_range(self, lut):
        """Output RGB values should stay in valid range."""
        gray = np.random.randint(0, 256, size=(5, 10), dtype=np.uint8)

        rgb = apply_lut(gray, lut)

        assert np.all(rgb >= 0)
        assert np.all(rgb <= 255)


class TestResizeGrayscaleRow:
    """Test grayscale row resizing function."""

    def test_resize_shape(self):
        """Resized output should have target width."""
        gray_row = np.arange(200, dtype=np.uint8)

        resized = resize_grayscale_row(gray_row, target_width=150)

        assert resized.shape == (150,)
        assert resized.dtype == np.uint8

    def test_resize_preserves_range(self):
        """Resized values should stay within original range."""
        # Create a row with gradual gradient
        gray_row = np.linspace(0, 255, 200).astype(np.uint8)

        resized = resize_grayscale_row(gray_row, target_width=150)

        # Values should stay in range
        assert resized.min() >= 0
        assert resized.max() <= 255
        # Should preserve approximate range
        assert resized[0] <= 20  # Start near 0
        assert resized[-1] >= 235  # End near 255

    def test_resize_downsampling(self):
        """Test downsampling from 200 to 150."""
        # Create pattern: 0, 1, 2, ..., 199
        gray_row = np.arange(200, dtype=np.uint8)

        resized = resize_grayscale_row(gray_row, target_width=150)

        assert len(resized) == 150
        # Values should be in reasonable range
        assert resized.min() >= 0
        assert resized.max() <= 199

    def test_resize_constant_input(self):
        """Constant input should produce constant output."""
        gray_row = np.full(200, 128, dtype=np.uint8)

        resized = resize_grayscale_row(gray_row, target_width=150)

        # All values should be close to 128 (allowing for minor interpolation artifacts)
        assert np.all(np.abs(resized.astype(int) - 128) <= 2)

    def test_resize_deterministic(self):
        """Resize should be deterministic."""
        gray_row = np.random.RandomState(42).randint(0, 256, size=200, dtype=np.uint8)

        resized1 = resize_grayscale_row(gray_row, target_width=150)
        resized2 = resize_grayscale_row(gray_row, target_width=150)

        np.testing.assert_array_equal(resized1, resized2)

    def test_resize_no_op(self):
        """Resizing to same width should return near-identical array."""
        gray_row = np.arange(200, dtype=np.uint8)

        resized = resize_grayscale_row(gray_row, target_width=200)

        assert len(resized) == 200
        # Should be very close to original (exact match with nearest neighbor)
        np.testing.assert_array_almost_equal(resized, gray_row, decimal=0)

    def test_resize_gradient(self):
        """Test resize preserves gradient pattern."""
        # Create gradient from 0 to 255
        gray_row = np.linspace(0, 255, 200).astype(np.uint8)

        resized = resize_grayscale_row(gray_row, target_width=150)

        # Should still be roughly ascending
        assert resized[0] < resized[74]  # First half
        assert resized[74] < resized[149]  # Second half


class TestEncodeToPNG:
    """Test PNG encoding function (RGB only)."""

    def test_encode_rgb(self):
        """Encode RGB image to PNG."""
        rgb = np.zeros((2, 3, 3), dtype=np.uint8)
        rgb[0, 0] = [255, 0, 0]  # Red
        rgb[0, 1] = [0, 255, 0]  # Green
        rgb[0, 2] = [0, 0, 255]  # Blue

        png_bytes = encode_to_png(rgb)

        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"  # PNG signature

    def test_encode_rgb_roundtrip(self):
        """RGB encode/decode roundtrip."""
        original = np.array(
            [
                [[255, 0, 0], [0, 255, 0], [0, 0, 255]],
            ],
            dtype=np.uint8,
        )

        # Encode
        png_bytes = encode_to_png(original)

        # Decode
        img = Image.open(BytesIO(png_bytes))
        decoded = np.array(img)

        np.testing.assert_array_equal(decoded, original)

    def test_encode_deterministic(self):
        """Same input should produce same PNG bytes."""
        rgb = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255]]], dtype=np.uint8)

        png1 = encode_to_png(rgb)
        png2 = encode_to_png(rgb)

        assert png1 == png2

    def test_encode_base64_decodable(self):
        """Encoded PNG should be base64-encodable."""
        rgb = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255]]], dtype=np.uint8)

        png_bytes = encode_to_png(rgb)

        # Should be base64 encodable without error
        base64_str = base64.b64encode(png_bytes).decode("ascii")

        # Should be decodable back to PNG
        decoded_bytes = base64.b64decode(base64_str)
        assert decoded_bytes == png_bytes

    def test_encode_single_pixel(self):
        """Encode single pixel RGB image."""
        rgb = np.array([[[128, 128, 128]]], dtype=np.uint8)

        png_bytes = encode_to_png(rgb)

        assert len(png_bytes) > 0
        img = Image.open(BytesIO(png_bytes))
        assert img.size == (1, 1)
        assert img.mode == "RGB"


class TestImagePipelineIntegration:
    """Test complete image processing pipeline."""

    def test_full_pipeline(self):
        """Test complete pipeline: resize -> colormap -> encode."""
        # Create 200-pixel grayscale row
        gray_row = np.linspace(0, 255, 200).astype(np.uint8)

        # Step 1: Resize to 150
        resized = resize_grayscale_row(gray_row, target_width=150)
        assert len(resized) == 150

        # Step 2: Reshape to 2D
        gray_2d = resized.reshape(1, 150)

        # Step 3: Apply colormap
        lut = make_colormap_lut()
        rgb = apply_lut(gray_2d, lut)
        assert rgb.shape == (1, 150, 3)

        # Step 4: Encode to PNG
        png_bytes = encode_to_png(rgb)
        assert len(png_bytes) > 0

        # Step 5: Verify decodable
        img = Image.open(BytesIO(png_bytes))
        assert img.size == (150, 1)
        assert img.mode == "RGB"

    def test_pipeline_preserves_extremes(self):
        """Pipeline should preserve min/max intensity mapping."""
        # Create row with extreme values
        gray_row = np.zeros(200, dtype=np.uint8)
        gray_row[0] = 0
        gray_row[50] = 128
        gray_row[199] = 255

        # Resize
        resized = resize_grayscale_row(gray_row, target_width=150)

        # Apply colormap
        lut = make_colormap_lut()
        gray_2d = resized.reshape(1, 150)
        rgb = apply_lut(gray_2d, lut)

        # Check that we have variation in colors (not all the same)
        assert not np.all(rgb == rgb[0, 0])

    def test_pipeline_deterministic(self):
        """Complete pipeline should be deterministic."""
        gray_row = np.random.RandomState(42).randint(0, 256, size=200, dtype=np.uint8)

        # Run pipeline twice
        def run_pipeline(row):
            resized = resize_grayscale_row(row, target_width=150)
            lut = make_colormap_lut()
            gray_2d = resized.reshape(1, 150)
            rgb = apply_lut(gray_2d, lut)
            return encode_to_png(rgb)

        png1 = run_pipeline(gray_row)
        png2 = run_pipeline(gray_row)

        assert png1 == png2


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_all_zeros(self):
        """Handle all-zero grayscale input."""
        gray_row = np.zeros(200, dtype=np.uint8)

        resized = resize_grayscale_row(gray_row, target_width=150)
        assert np.all(resized == 0)

        lut = make_colormap_lut()
        gray_2d = resized.reshape(1, 150)
        rgb = apply_lut(gray_2d, lut)

        # All should map to lut[0]
        assert np.all(rgb == lut[0])

    def test_all_max(self):
        """Handle all-max grayscale input."""
        gray_row = np.full(200, 255, dtype=np.uint8)

        resized = resize_grayscale_row(gray_row, target_width=150)
        assert np.all(resized == 255)

        lut = make_colormap_lut()
        gray_2d = resized.reshape(1, 150)
        rgb = apply_lut(gray_2d, lut)

        # All should map to lut[255]
        assert np.all(rgb == lut[255])

    def test_single_pixel(self):
        """Handle single pixel (edge case for resize)."""
        gray = np.array([[128]], dtype=np.uint8)

        lut = make_colormap_lut()
        rgb = apply_lut(gray, lut)

        assert rgb.shape == (1, 1, 3)
        np.testing.assert_array_equal(rgb[0, 0], lut[128])

    def test_alternating_pattern(self):
        """Test alternating black/white pattern."""
        gray_row = np.tile([0, 255], 100).astype(np.uint8)  # 200 pixels alternating

        resized = resize_grayscale_row(gray_row, target_width=150)

        # Should have variation (not all same value)
        assert len(np.unique(resized)) > 1
