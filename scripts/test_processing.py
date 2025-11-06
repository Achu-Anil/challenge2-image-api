"""
Test script to validate image processing pipeline.

This script tests the complete pipeline:
1. Generate synthetic test data
2. Process through resize + colormap + PNG encode
3. Validate output dimensions and format
"""

import asyncio
from pathlib import Path

import numpy as np
import pandas as pd

from app.core import setup_logging
from app.processing import process_row_to_png
from app.processing.image import (
    COLORMAP_LUT,
    apply_colormap,
    generate_colormap_lut,
    resize_grayscale_row,
)


def test_colormap_lut():
    """Test colormap LUT generation and properties."""
    print("\n=== Testing Colormap LUT ===")

    lut = generate_colormap_lut()
    print(f"LUT shape: {lut.shape}")
    print(f"LUT dtype: {lut.dtype}")

    # Check color stops
    print(f"\nColor at index 0 (dark blue): {lut[0]}")
    print(f"Color at index 64 (cyan): {lut[64]}")
    print(f"Color at index 128 (green): {lut[128]}")
    print(f"Color at index 192 (yellow): {lut[192]}")
    print(f"Color at index 255 (red): {lut[255]}")

    # Verify precomputed LUT matches
    assert np.array_equal(lut, COLORMAP_LUT), "Precomputed LUT mismatch"
    print("\n✅ Colormap LUT test passed")


def test_resize():
    """Test grayscale row resize function."""
    print("\n=== Testing Resize Function ===")

    # Create test row: gradient from 0 to 255
    row = np.linspace(0, 255, 200, dtype=np.uint8)
    print(f"Original row shape: {row.shape}")
    print(f"Original row range: [{row.min()}, {row.max()}]")

    # Resize
    resized = resize_grayscale_row(row, target_width=150)
    print(f"Resized row shape: {resized.shape}")
    print(f"Resized row range: [{resized.min()}, {resized.max()}]")

    assert resized.shape == (150,), f"Expected shape (150,), got {resized.shape}"
    assert resized.dtype == np.uint8, f"Expected uint8, got {resized.dtype}"
    print("\n✅ Resize test passed")


def test_colormap_application():
    """Test applying colormap to grayscale data."""
    print("\n=== Testing Colormap Application ===")

    # Create simple grayscale row
    gray = np.array([[0, 64, 128, 192, 255]], dtype=np.uint8)
    print(f"Grayscale input shape: {gray.shape}")
    print(f"Grayscale values: {gray[0]}")

    # Apply colormap
    rgb = apply_colormap(gray)
    print(f"RGB output shape: {rgb.shape}")
    print("\nRGB values:")
    for i, val in enumerate(gray[0]):
        print(f"  Gray {val:3d} → RGB {rgb[0, i]}")

    assert rgb.shape == (1, 5, 3), f"Expected shape (1, 5, 3), got {rgb.shape}"
    assert rgb.dtype == np.uint8, f"Expected uint8, got {rgb.dtype}"
    print("\n✅ Colormap application test passed")


def test_full_pipeline():
    """Test complete pipeline: row → resized colorized PNG."""
    print("\n=== Testing Full Pipeline ===")

    # Create synthetic test row (200 pixels)
    # Gradient from dark (0) to bright (255)
    row_data = np.linspace(0, 255, 200)
    print(
        f"Input: {len(row_data)} pixel values, range [{row_data.min():.1f}, {row_data.max():.1f}]"
    )

    # Process to PNG
    png_bytes, width, height = process_row_to_png(row_data, source_width=200, target_width=150)

    print(f"Output: {len(png_bytes)} bytes, dimensions {width}x{height}")
    print(f"PNG header: {png_bytes[:8].hex()}")  # Should start with PNG signature

    # Verify PNG signature
    png_signature = b"\x89PNG\r\n\x1a\n"
    assert png_bytes[:8] == png_signature, "Invalid PNG signature"

    assert width == 150, f"Expected width 150, got {width}"
    assert height == 1, f"Expected height 1, got {height}"
    assert len(png_bytes) > 100, f"PNG seems too small: {len(png_bytes)} bytes"

    print("\n✅ Full pipeline test passed")

    return png_bytes


def create_test_csv(path: Path = Path("test_frames.csv"), num_rows: int = 10):
    """Create a small test CSV file for ingestion testing."""
    print(f"\n=== Creating Test CSV: {path} ===")

    # Generate synthetic data
    depths = np.linspace(100.0, 200.0, num_rows)

    # Create pixel data: each row is a gradient
    pixel_data = []
    for i in range(num_rows):
        # Varying gradients for visual interest
        start_val = (i * 25) % 256
        end_val = (start_val + 200) % 256
        row = np.linspace(start_val, end_val, 200, dtype=np.uint8)
        pixel_data.append(row)

    # Create DataFrame
    pixel_cols = [f"pixel_{i}" for i in range(200)]
    df = pd.DataFrame(pixel_data, columns=pixel_cols)
    df.insert(0, "depth", depths)

    # Save to CSV
    df.to_csv(path, index=False)

    print(f"Created CSV with {num_rows} rows, {len(df.columns)} columns")
    print(f"Depth range: [{depths.min()}, {depths.max()}]")
    print(f"File size: {path.stat().st_size / 1024:.2f} KB")
    print("\n✅ Test CSV created")

    return path


async def test_csv_exploration(csv_path: Path):
    """Test CSV exploration function."""
    print("\n=== Testing CSV Exploration ===")

    from app.processing.ingest import explore_csv

    info = explore_csv(csv_path)

    print(f"CSV path: {info['csv_path']}")
    print(f"Rows: {info['num_rows']}")
    print(f"Columns: {info['num_cols']}")
    print(f"First column: {info['first_column']}")
    print(f"Pixel columns: {info['num_pixel_columns']}")
    print(f"Sample depths: {info['sample_depths']}")
    print(f"File size: {info['file_size_mb']:.2f} MB")

    print("\n✅ CSV exploration test passed")

    return info


def main():
    """Run all tests."""
    setup_logging("INFO")

    print("=" * 60)
    print("IMAGE PROCESSING PIPELINE TESTS")
    print("=" * 60)

    # Run tests
    test_colormap_lut()
    test_resize()
    test_colormap_application()
    png_bytes = test_full_pipeline()

    # Create test CSV and explore it
    test_csv_path = create_test_csv(num_rows=5)
    asyncio.run(test_csv_exploration(test_csv_path))

    # Optional: save test PNG for visual inspection
    test_png_path = Path("test_frame.png")
    with open(test_png_path, "wb") as f:
        f.write(png_bytes)
    print(f"\n💾 Saved test PNG to: {test_png_path}")

    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Verify test_frame.png visually (should be 150x1 colorized gradient)")
    print("2. Run ingestion with: python -m scripts.ingest test_frames.csv")


if __name__ == "__main__":
    main()
