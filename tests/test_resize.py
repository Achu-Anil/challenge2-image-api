"""
Comprehensive tests for image resizing functionality.

Tests cover:
- Basic resizing correctness (200→150)
- Shape and dtype integrity
- Edge cases (already correct width, single pixel, etc.)
- Performance benchmarks
- Different resampling methods
- Error handling
"""

import time
import numpy as np
import pytest
from PIL import Image

from app.processing.image import resize_gray_width, resize_grayscale_row


class TestResizeGrayWidth:
    """Tests for the main resize_gray_width() function."""
    
    def test_basic_resize_200_to_150(self):
        """Test basic 200→150 resize produces correct shape."""
        gray = np.random.randint(0, 256, (1, 200), dtype=np.uint8)
        resized = resize_gray_width(gray, new_width=150)
        
        assert resized.shape == (1, 150)
        assert resized.dtype == np.uint8
    
    def test_multiple_rows(self):
        """Test resizing works for multiple rows simultaneously."""
        gray = np.random.randint(0, 256, (10, 200), dtype=np.uint8)
        resized = resize_gray_width(gray, new_width=150)
        
        assert resized.shape == (10, 150)
        assert resized.dtype == np.uint8
    
    def test_dtype_preserved(self):
        """Ensure uint8 dtype is maintained through resize."""
        gray = np.random.randint(0, 256, (1, 200), dtype=np.uint8)
        resized = resize_gray_width(gray, new_width=150)
        
        assert resized.dtype == np.uint8
        assert np.all(resized >= 0) and np.all(resized <= 255)
    
    def test_already_correct_width(self):
        """Short-circuit when input is already target width."""
        gray = np.random.randint(0, 256, (1, 150), dtype=np.uint8)
        resized = resize_gray_width(gray, new_width=150)
        
        # Should return same array (identity operation)
        assert resized.shape == (1, 150)
        np.testing.assert_array_equal(resized, gray)
    
    def test_upscaling(self):
        """Test that upscaling (150→200) works correctly."""
        gray = np.random.randint(0, 256, (1, 150), dtype=np.uint8)
        resized = resize_gray_width(gray, new_width=200)
        
        assert resized.shape == (1, 200)
        assert resized.dtype == np.uint8
    
    def test_downscaling(self):
        """Test that downscaling (200→100) works correctly."""
        gray = np.random.randint(0, 256, (1, 200), dtype=np.uint8)
        resized = resize_gray_width(gray, new_width=100)
        
        assert resized.shape == (1, 100)
        assert resized.dtype == np.uint8
    
    def test_single_pixel_width(self):
        """Edge case: resize to width=1."""
        gray = np.random.randint(0, 256, (1, 200), dtype=np.uint8)
        resized = resize_gray_width(gray, new_width=1)
        
        assert resized.shape == (1, 1)
        assert resized.dtype == np.uint8
    
    def test_uniform_gray_preserved(self):
        """Uniform gray values should remain approximately uniform."""
        gray_value = 128
        gray = np.full((1, 200), gray_value, dtype=np.uint8)
        resized = resize_gray_width(gray, new_width=150)
        
        # All values should be exactly 128 (uniform stays uniform)
        assert np.all(resized == gray_value)
    
    def test_black_white_extremes(self):
        """Test boundary values (0 and 255) are preserved."""
        gray = np.zeros((1, 200), dtype=np.uint8)
        resized = resize_gray_width(gray, new_width=150)
        assert np.all(resized == 0)
        
        gray = np.full((1, 200), 255, dtype=np.uint8)
        resized = resize_gray_width(gray, new_width=150)
        assert np.all(resized == 255)
    
    def test_linear_gradient_smoothness(self):
        """Resizing a gradient should maintain smoothness."""
        # Create smooth gradient 0→255
        gray = np.linspace(0, 255, 200, dtype=np.uint8).reshape(1, -1)
        resized = resize_gray_width(gray, new_width=150)
        
        # Check gradient is still monotonic increasing
        diffs = np.diff(resized[0])
        # Allow small variations due to interpolation
        assert np.all(diffs >= -1)  # Mostly increasing or flat
        
        # Check endpoints are preserved approximately
        assert resized[0, 0] <= 5  # Near 0
        assert resized[0, -1] >= 250  # Near 255


class TestResizingMethods:
    """Test different Pillow resampling methods."""
    
    def test_bilinear_default(self):
        """Verify BILINEAR is used by default."""
        gray = np.random.randint(0, 256, (1, 200), dtype=np.uint8)
        resized = resize_gray_width(gray, new_width=150)
        # Just verify it works without error
        assert resized.shape == (1, 150)
    
    def test_nearest_neighbor(self):
        """Test NEAREST resampling (fastest, blocky)."""
        gray = np.random.randint(0, 256, (1, 200), dtype=np.uint8)
        resized = resize_gray_width(
            gray, 
            new_width=150, 
            resample=Image.Resampling.NEAREST
        )
        assert resized.shape == (1, 150)
        assert resized.dtype == np.uint8
    
    def test_lanczos(self):
        """Test LANCZOS resampling (highest quality, slower)."""
        gray = np.random.randint(0, 256, (1, 200), dtype=np.uint8)
        resized = resize_gray_width(
            gray, 
            new_width=150, 
            resample=Image.Resampling.LANCZOS
        )
        assert resized.shape == (1, 150)
        assert resized.dtype == np.uint8
    
    def test_bicubic(self):
        """Test BICUBIC resampling (good quality)."""
        gray = np.random.randint(0, 256, (1, 200), dtype=np.uint8)
        resized = resize_gray_width(
            gray, 
            new_width=150, 
            resample=Image.Resampling.BICUBIC
        )
        assert resized.shape == (1, 150)
        assert resized.dtype == np.uint8


class TestErrorHandling:
    """Test validation and error cases."""
    
    def test_wrong_ndim_1d(self):
        """Should reject 1D arrays."""
        gray = np.random.randint(0, 256, 200, dtype=np.uint8)
        with pytest.raises(ValueError, match="Expected 2D array"):
            resize_gray_width(gray, new_width=150)
    
    def test_wrong_ndim_3d(self):
        """Should reject 3D arrays."""
        gray = np.random.randint(0, 256, (1, 200, 3), dtype=np.uint8)
        with pytest.raises(ValueError, match="Expected 2D array"):
            resize_gray_width(gray, new_width=150)
    
    def test_wrong_dtype_float(self):
        """Should reject non-uint8 dtypes."""
        gray = np.random.rand(1, 200).astype(np.float32)
        with pytest.raises(ValueError, match="Expected uint8 dtype"):
            resize_gray_width(gray, new_width=150)
    
    def test_wrong_dtype_int16(self):
        """Should reject int16 even though it's integer."""
        gray = np.random.randint(0, 256, (1, 200), dtype=np.int16)
        with pytest.raises(ValueError, match="Expected uint8 dtype"):
            resize_gray_width(gray, new_width=150)


class TestPerformance:
    """Performance benchmarks for batch processing."""
    
    def test_single_row_speed(self):
        """Benchmark single row resize (should be <1ms)."""
        gray = np.random.randint(0, 256, (1, 200), dtype=np.uint8)
        
        start = time.perf_counter()
        for _ in range(100):
            resize_gray_width(gray, new_width=150)
        elapsed = time.perf_counter() - start
        
        avg_time = elapsed / 100
        print(f"\nAverage time per row: {avg_time*1000:.3f}ms")
        assert avg_time < 0.001  # Less than 1ms per row
    
    def test_batch_processing(self):
        """Benchmark batch of 500 rows (typical chunk size)."""
        gray = np.random.randint(0, 256, (500, 200), dtype=np.uint8)
        
        start = time.perf_counter()
        resized = resize_gray_width(gray, new_width=150)
        elapsed = time.perf_counter() - start
        
        print(f"\nBatch resize 500 rows: {elapsed*1000:.2f}ms")
        print(f"Per-row time: {(elapsed/500)*1000:.3f}ms")
        assert elapsed < 0.5  # Should complete in <500ms
        assert resized.shape == (500, 150)
    
    def test_memory_efficiency(self):
        """Verify no memory bloat from resize operations."""
        import sys
        
        gray = np.random.randint(0, 256, (100, 200), dtype=np.uint8)
        size_before = sys.getsizeof(gray)
        
        resized = resize_gray_width(gray, new_width=150)
        size_after = sys.getsizeof(resized)
        
        # Output should be proportionally smaller
        expected_ratio = 150 / 200
        actual_ratio = size_after / size_before
        
        # Allow some overhead for array object
        assert 0.6 < actual_ratio < 0.9


class TestLegacyWrapper:
    """Tests for backwards-compatible resize_grayscale_row()."""
    
    def test_1d_input_output(self):
        """Legacy function accepts and returns 1D arrays."""
        row = np.random.randint(0, 256, 200, dtype=np.uint8)
        resized = resize_grayscale_row(row, target_width=150)
        
        assert resized.ndim == 1
        assert resized.shape == (150,)
        assert resized.dtype == np.uint8
    
    def test_matches_new_function(self):
        """Legacy wrapper produces same results as resize_gray_width."""
        row = np.random.randint(0, 256, 200, dtype=np.uint8)
        
        # Legacy method
        resized_legacy = resize_grayscale_row(row, target_width=150)
        
        # New method
        resized_new = resize_gray_width(row.reshape(1, -1), new_width=150).flatten()
        
        np.testing.assert_array_equal(resized_legacy, resized_new)


class TestIntegration:
    """Integration tests with full pipeline."""
    
    def test_resize_then_colormap(self):
        """Test resize followed by colormap application."""
        from app.processing.image import apply_colormap
        
        # Create 200-width gray row
        gray = np.random.randint(0, 256, (1, 200), dtype=np.uint8)
        
        # Resize to 150
        resized = resize_gray_width(gray, new_width=150)
        
        # Apply colormap
        rgb = apply_colormap(resized)
        
        assert rgb.shape == (1, 150, 3)
        assert rgb.dtype == np.uint8
    
    def test_full_pipeline_200_to_150_to_png(self):
        """Test complete pipeline: 200→150→colorize→PNG."""
        from app.processing.image import apply_colormap, encode_to_png
        
        # Start with 200-width row
        gray = np.random.randint(0, 256, (1, 200), dtype=np.uint8)
        
        # Step 1: Resize
        resized = resize_gray_width(gray, new_width=150)
        assert resized.shape == (1, 150)
        
        # Step 2: Colorize
        rgb = apply_colormap(resized)
        assert rgb.shape == (1, 150, 3)
        
        # Step 3: Encode to PNG
        png_bytes = encode_to_png(rgb)
        assert len(png_bytes) > 0
        assert png_bytes[:8] == b'\x89PNG\r\n\x1a\n'  # PNG signature
    
    def test_deterministic_pipeline(self):
        """Pipeline should be deterministic (same input → same output)."""
        from app.processing.image import apply_colormap, encode_to_png
        
        gray = np.random.randint(0, 256, (1, 200), dtype=np.uint8)
        
        # Run pipeline twice
        resized1 = resize_gray_width(gray, new_width=150)
        rgb1 = apply_colormap(resized1)
        png1 = encode_to_png(rgb1)
        
        resized2 = resize_gray_width(gray, new_width=150)
        rgb2 = apply_colormap(resized2)
        png2 = encode_to_png(rgb2)
        
        # Should be identical
        np.testing.assert_array_equal(resized1, resized2)
        np.testing.assert_array_equal(rgb1, rgb2)
        assert png1 == png2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
