"""
Unit tests for colormap LUT generation and application.

Tests verify:
1. Deterministic LUT generation
2. Correct shape and dtype
3. Expected color stops
4. Smooth interpolation
5. Vectorized application
6. Edge cases and boundaries
"""

import numpy as np
import pytest

from app.processing.image import (
    COLOR_STOPS,
    COLORMAP_LUT,
    apply_colormap,
    apply_lut,
    make_colormap_lut,
)


class TestColormapLUTGeneration:
    """Tests for make_colormap_lut() function."""

    def test_lut_shape(self):
        """LUT should be 256×3 array."""
        lut = make_colormap_lut()
        assert lut.shape == (256, 3), f"Expected (256, 3), got {lut.shape}"

    def test_lut_dtype(self):
        """LUT should be uint8."""
        lut = make_colormap_lut()
        assert lut.dtype == np.uint8, f"Expected uint8, got {lut.dtype}"

    def test_deterministic(self):
        """LUT generation should be deterministic (same output every time)."""
        lut1 = make_colormap_lut()
        lut2 = make_colormap_lut()
        np.testing.assert_array_equal(lut1, lut2, err_msg="LUT not deterministic")

    def test_color_stops_exact(self):
        """Color stops should match exactly at defined indices."""
        lut = make_colormap_lut()

        for idx, expected_rgb in COLOR_STOPS:
            actual_rgb = lut[idx]
            np.testing.assert_array_equal(
                actual_rgb,
                expected_rgb,
                err_msg=f"Color stop at index {idx} mismatch: "
                f"expected {expected_rgb}, got {tuple(actual_rgb)}",
            )

    def test_precomputed_lut_matches(self):
        """Pre-computed COLORMAP_LUT should match freshly generated one."""
        fresh_lut = make_colormap_lut()
        np.testing.assert_array_equal(
            COLORMAP_LUT, fresh_lut, err_msg="Pre-computed LUT doesn't match fresh generation"
        )

    def test_smooth_interpolation(self):
        """Values between stops should interpolate smoothly."""
        lut = make_colormap_lut()

        # Check between first two stops (0→64)
        # Should see gradual change in blue component
        start_blue = lut[0, 2]  # B channel at index 0
        mid_blue = lut[32, 2]  # B channel at midpoint
        end_blue = lut[64, 2]  # B channel at index 64

        # Midpoint should be between start and end
        assert (
            start_blue <= mid_blue <= end_blue or end_blue <= mid_blue <= start_blue
        ), f"Non-monotonic interpolation: {start_blue}, {mid_blue}, {end_blue}"

    def test_no_gaps(self):
        """Every index 0-255 should have a valid RGB value."""
        lut = make_colormap_lut()

        # Check no zeros (except where expected)
        # At least one channel should be non-zero for most values
        for i in range(256):
            rgb_sum = int(lut[i, 0]) + int(lut[i, 1]) + int(lut[i, 2])
            assert rgb_sum > 0, f"All-zero RGB at index {i}"

    def test_boundary_values(self):
        """Test extreme boundary values."""
        lut = make_colormap_lut()

        # First value (deep blue)
        assert lut[0, 0] == 0  # No red
        assert lut[0, 1] == 0  # No green
        assert lut[0, 2] == 139  # Blue component

        # Last value (orange-red)
        assert lut[255, 0] == 255  # Full red
        assert lut[255, 1] == 69  # Some green
        assert lut[255, 2] == 0  # No blue


class TestApplyLUT:
    """Tests for apply_lut() function."""

    def test_single_pixel(self):
        """Test LUT application on single pixel."""
        gray = np.array([[128]], dtype=np.uint8)
        lut = make_colormap_lut()

        rgb = apply_lut(gray, lut)

        assert rgb.shape == (1, 1, 3), f"Expected (1, 1, 3), got {rgb.shape}"
        np.testing.assert_array_equal(rgb[0, 0], lut[128])

    def test_color_stops_mapping(self):
        """Known grayscale inputs should map to expected RGB stops."""
        # Create array with color stop values
        gray = np.array([[0, 64, 128, 192, 255]], dtype=np.uint8)
        lut = make_colormap_lut()

        rgb = apply_lut(gray, lut)

        assert rgb.shape == (1, 5, 3), f"Expected (1, 5, 3), got {rgb.shape}"

        # Check each color stop
        for i, (stop_idx, expected_color) in enumerate(COLOR_STOPS):
            actual_rgb = rgb[0, i]
            np.testing.assert_array_equal(
                actual_rgb,
                expected_color,
                err_msg=f"Stop {stop_idx}: expected {expected_color}, got {tuple(actual_rgb)}",
            )

    def test_full_gradient(self):
        """Test complete 0-255 gradient."""
        gray = np.arange(256, dtype=np.uint8).reshape(1, 256)
        lut = make_colormap_lut()

        rgb = apply_lut(gray, lut)

        assert rgb.shape == (1, 256, 3), f"Expected (1, 256, 3), got {rgb.shape}"

        # Verify each pixel maps correctly
        for i in range(256):
            np.testing.assert_array_equal(rgb[0, i], lut[i])

    def test_2d_image(self):
        """Test LUT application on 2D grayscale image."""
        # Create 10x10 gradient image
        gray = np.tile(np.arange(10, dtype=np.uint8) * 25, (10, 1))
        lut = make_colormap_lut()

        rgb = apply_lut(gray, lut)

        assert rgb.shape == (10, 10, 3), f"Expected (10, 10, 3), got {rgb.shape}"
        assert rgb.dtype == np.uint8

    def test_vectorized_no_loops(self):
        """Verify vectorization - should be fast even for large images."""
        # Large image: 1000×1000 pixels
        gray = np.random.randint(0, 256, (1000, 1000), dtype=np.uint8)
        lut = make_colormap_lut()

        import time

        start = time.time()
        rgb = apply_lut(gray, lut)
        elapsed = time.time() - start

        # Should complete in under 100ms (vectorized)
        assert elapsed < 0.1, f"Too slow: {elapsed:.3f}s (should be <0.1s)"
        assert rgb.shape == (1000, 1000, 3)

    def test_dtype_preserved(self):
        """Output should be uint8."""
        gray = np.array([[100, 200]], dtype=np.uint8)
        lut = make_colormap_lut()

        rgb = apply_lut(gray, lut)

        assert rgb.dtype == np.uint8

    def test_boundary_cases(self):
        """Test extreme values (0 and 255)."""
        gray = np.array([[0, 255]], dtype=np.uint8)
        lut = make_colormap_lut()

        rgb = apply_lut(gray, lut)

        # Check first pixel (0 → deep blue)
        np.testing.assert_array_equal(rgb[0, 0], [0, 0, 139])

        # Check last pixel (255 → orange-red)
        np.testing.assert_array_equal(rgb[0, 1], [255, 69, 0])


class TestApplyColormapWrapper:
    """Tests for apply_colormap() convenience wrapper."""

    def test_uses_global_lut(self):
        """apply_colormap() should use pre-computed COLORMAP_LUT."""
        gray = np.array([[0, 128, 255]], dtype=np.uint8)

        rgb = apply_colormap(gray)

        # Should match manual application with global LUT
        expected = apply_lut(gray, COLORMAP_LUT)
        np.testing.assert_array_equal(rgb, expected)

    def test_known_values(self):
        """Test with known grayscale values."""
        gray = np.array([[64, 192]], dtype=np.uint8)

        rgb = apply_colormap(gray)

        # 64 → teal
        np.testing.assert_array_equal(rgb[0, 0], [0, 139, 139])

        # 192 → yellow
        np.testing.assert_array_equal(rgb[0, 1], [255, 215, 0])


class TestIntegration:
    """Integration tests combining LUT generation and application."""

    def test_full_pipeline(self):
        """Test complete LUT generation → application pipeline."""
        # Generate fresh LUT
        lut = make_colormap_lut()

        # Create test gradient
        gray = np.linspace(0, 255, 256, dtype=np.uint8).reshape(1, 256)

        # Apply LUT
        rgb = apply_lut(gray, lut)

        # Verify output
        assert rgb.shape == (1, 256, 3)
        assert rgb.dtype == np.uint8

        # Check endpoints
        np.testing.assert_array_equal(rgb[0, 0], lut[0])
        np.testing.assert_array_equal(rgb[0, 255], lut[255])

    def test_deterministic_pipeline(self):
        """Entire pipeline should be deterministic."""
        gray = np.random.RandomState(42).randint(0, 256, (10, 10), dtype=np.uint8)

        # Run twice
        rgb1 = apply_colormap(gray)
        rgb2 = apply_colormap(gray)

        np.testing.assert_array_equal(rgb1, rgb2)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
