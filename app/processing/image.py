"""
Image processing utilities for grayscale to colorized PNG conversion.

This module provides vectorized operations for:
1. Color map LUT generation (256×3 RGB lookup table)
2. Image resizing (1×200 → 1×150 with bilinear interpolation)
3. Grayscale to RGB color mapping (vectorized via NumPy indexing)
"""

from io import BytesIO
from typing import Final

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from app.core import get_logger

logger = get_logger(__name__)

# Color stops for gradient (dark blue → teal/green → yellow → orange/red)
# These create a visually appealing depth colormap for seismic/geological data
# Format: (grayscale_value, (R, G, B))
COLOR_STOPS: Final[list[tuple[int, tuple[int, int, int]]]] = [
    (0, (0, 0, 139)),  # Deep blue (darkest/deepest)
    (64, (0, 139, 139)),  # Teal (deep)
    (128, (0, 200, 100)),  # Green (medium)
    (192, (255, 215, 0)),  # Yellow (shallow)
    (255, (255, 69, 0)),  # Orange-red (shallowest)
]


def make_colormap_lut() -> NDArray[np.uint8]:
    """
    Generate a 256×3 lookup table for grayscale to RGB color mapping.

    Creates a deterministic smooth gradient from dark blue (deep) through
    teal/green, yellow to orange/red (shallow). Uses linear interpolation
    between predefined color stops.

    Gradient design:
    - 0→64:   Deep blue → Teal (deep water/depth)
    - 65→128: Teal → Green (medium depth)
    - 129→192: Green → Yellow (transitional)
    - 193→255: Yellow → Orange-red (shallow/surface)

    Returns:
        NDArray[np.uint8]: Shape (256, 3) array where lut[i] gives RGB
        triple for grayscale value i. Deterministic - no randomness.

    Example:
        >>> lut = make_colormap_lut()
        >>> lut.shape
        (256, 3)
        >>> lut[0]    # Deep blue for value 0
        array([  0,   0, 139], dtype=uint8)
        >>> lut[255]  # Orange-red for value 255
        array([255,  69,   0], dtype=uint8)

    Notes:
        - Fully deterministic (no random seed needed)
        - Vectorized linear interpolation
        - Pre-computed at module load for O(1) lookup
    """
    # Initialize LUT array
    lut = np.zeros((256, 3), dtype=np.uint8)

    # Interpolate between each pair of color stops
    for i in range(len(COLOR_STOPS) - 1):
        start_idx, start_color = COLOR_STOPS[i]
        end_idx, end_color = COLOR_STOPS[i + 1]

        # Number of steps between stops
        num_steps = end_idx - start_idx

        # Linear interpolation for each RGB channel
        for channel in range(3):
            lut[start_idx : end_idx + 1, channel] = np.linspace(
                start_color[channel], end_color[channel], num_steps + 1, dtype=np.uint8
            )

    logger.debug("Generated colormap LUT", extra={"shape": lut.shape, "dtype": str(lut.dtype)})
    return lut


# Backwards compatibility alias
generate_colormap_lut = make_colormap_lut


# Precompute and cache the colormap LUT at module load time
COLORMAP_LUT: Final[NDArray[np.uint8]] = make_colormap_lut()


def apply_lut(gray_2d_uint8: NDArray[np.uint8], lut: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """
    Apply color LUT to grayscale image using vectorized indexing.

    Zero loops - pure NumPy advanced indexing for maximum performance.
    Maps each grayscale pixel to its corresponding RGB triple via LUT.

    Performance: O(H×W) with vectorization, ~100x faster than Python loops.

    Args:
        gray_2d_uint8: Grayscale image array with values 0-255, shape (H, W)
        lut: Color lookup table, shape (256, 3) with RGB values

    Returns:
        NDArray[np.uint8]: RGB image with shape (H, W, 3)

    Example:
        >>> gray = np.array([[0, 64, 128, 192, 255]], dtype=np.uint8)
        >>> lut = make_colormap_lut()
        >>> rgb = apply_lut(gray, lut)
        >>> rgb.shape
        (1, 5, 3)  # 1 row, 5 pixels, 3 RGB channels
        >>> rgb[0, 0]  # First pixel (gray=0) → deep blue
        array([  0,   0, 139], dtype=uint8)

    Notes:
        - Fully vectorized - no Python loops
        - Uses NumPy's advanced indexing: lut[gray] broadcasts correctly
        - Works with any 2D grayscale image shape
    """
    # Vectorized lookup: lut[gray_2d_uint8] returns RGB for each pixel
    # NumPy automatically broadcasts to shape (H, W, 3)
    return lut[gray_2d_uint8]


def apply_colormap(grayscale: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """
    Apply pre-computed color map to grayscale image using vectorized LUT indexing.

    Convenience wrapper around apply_lut() that uses the global COLORMAP_LUT.

    Args:
        grayscale: Grayscale image array with values 0-255, any shape

    Returns:
        NDArray[np.uint8]: RGB image with shape (*grayscale.shape, 3)

    Example:
        >>> gray = np.array([[0, 128, 255]], dtype=np.uint8)
        >>> rgb = apply_colormap(gray)
        >>> rgb.shape
        (1, 3, 3)  # 1 row, 3 pixels, 3 channels
    """
    return apply_lut(grayscale, COLORMAP_LUT)


def resize_gray_width(
    gray_2d_uint8: NDArray[np.uint8],
    new_width: int = 150,
    resample: Image.Resampling = Image.Resampling.BILINEAR,
) -> NDArray[np.uint8]:
    """
    Resize grayscale 2D image to new width using bilinear interpolation.

    **Resizing Strategy:**
    - Goal: Reliable 200→150 resizing, minimal artifacts, fast
    - Uses Pillow's bilinear resampling by default (good quality/speed balance)
    - Maintains dtype integrity (uint8) and proper shape
    - Suitable for batch processing

    Args:
        gray_2d_uint8: 2D grayscale array of shape (height, width) with uint8 values
        new_width: Target width (default 150 for 200→150 conversion)
        resample: Pillow resampling filter (default BILINEAR)

    Returns:
        NDArray[np.uint8]: Resized 2D array of shape (height, new_width)

    Raises:
        ValueError: If input is not 2D or not uint8

    Performance:
        - Bilinear: ~0.1ms per row, minimal artifacts
        - Suitable for batch processing thousands of rows

    Example:
        >>> gray = np.random.randint(0, 256, (1, 200), dtype=np.uint8)
        >>> resized = resize_gray_width(gray, new_width=150)
        >>> resized.shape
        (1, 150)
        >>> resized.dtype
        dtype('uint8')
    """
    # Validate input
    if gray_2d_uint8.ndim != 2:
        raise ValueError(f"Expected 2D array, got shape {gray_2d_uint8.shape}")
    if gray_2d_uint8.dtype != np.uint8:
        raise ValueError(f"Expected uint8 dtype, got {gray_2d_uint8.dtype}")

    height, width = gray_2d_uint8.shape

    # Short-circuit if already target width
    if width == new_width:
        return gray_2d_uint8

    # Convert to PIL Image (PIL infers mode='L' from uint8 2D array)
    img = Image.fromarray(gray_2d_uint8)

    # Resize using specified resampling method
    resized_img = img.resize((new_width, height), resample)

    # Convert back to numpy array (maintains uint8)
    resized_array = np.array(resized_img, dtype=np.uint8)

    # Ensure shape is correct
    assert resized_array.shape == (
        height,
        new_width,
    ), f"Expected shape ({height}, {new_width}), got {resized_array.shape}"
    assert resized_array.dtype == np.uint8, f"Expected uint8, got {resized_array.dtype}"

    return resized_array


def resize_grayscale_row(row: NDArray[np.uint8], target_width: int = 150) -> NDArray[np.uint8]:
    """
    Resize a single grayscale row from 200 to target width.

    Legacy convenience wrapper around resize_gray_width() for 1D arrays.
    For new code, prefer resize_gray_width() which handles 2D arrays directly.

    Args:
        row: 1D grayscale array of shape (200,) with uint8 values
        target_width: Desired width (default 150)

    Returns:
        NDArray[np.uint8]: Resized 1D array of shape (target_width,)

    Example:
        >>> row = np.random.randint(0, 256, 200, dtype=np.uint8)
        >>> resized = resize_grayscale_row(row, 150)
        >>> resized.shape
        (150,)
    """
    # Reshape to 2D, resize, then flatten
    gray_2d = row.reshape(1, -1)
    resized_2d = resize_gray_width(gray_2d, new_width=target_width)
    return resized_2d.flatten()


def encode_to_png(rgb_array: NDArray[np.uint8]) -> bytes:
    """
    Encode RGB array to PNG bytes.

    Args:
        rgb_array: RGB image array of shape (height, width, 3)

    Returns:
        bytes: PNG-encoded image data

    Example:
        >>> rgb = np.random.randint(0, 256, (1, 150, 3), dtype=np.uint8)
        >>> png_bytes = encode_to_png(rgb)
        >>> len(png_bytes) > 0
        True
    """
    # Create PIL Image from RGB array (PIL infers mode='RGB' from uint8 3D array with shape[2]==3)
    img = Image.fromarray(rgb_array)

    # Encode to PNG in memory
    buffer = BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    png_bytes = buffer.getvalue()

    logger.debug(
        "Encoded to PNG",
        extra={"input_shape": rgb_array.shape, "output_size_bytes": len(png_bytes)},
    )

    return png_bytes


def process_row_to_png(
    row_data: NDArray[np.float64] | list[float], source_width: int = 200, target_width: int = 150
) -> tuple[bytes, int, int]:
    """
    Complete pipeline: CSV row → resized colorized PNG.

    Steps:
    1. Convert to uint8 grayscale array (clamp to 0-255)
    2. Resize from source_width to target_width
    3. Apply colormap (grayscale → RGB)
    4. Encode to PNG bytes

    Args:
        row_data: Array or list of pixel values (0-255 range)
        source_width: Original width (default 200)
        target_width: Target width (default 150)

    Returns:
        tuple: (png_bytes, width, height)
            - png_bytes: PNG-encoded image data
            - width: Final image width (target_width)
            - height: Final image height (always 1)

    Example:
        >>> row = np.random.rand(200) * 255
        >>> png_bytes, width, height = process_row_to_png(row)
        >>> width, height
        (150, 1)
        >>> len(png_bytes) > 0
        True
    """
    # Convert to numpy array and ensure uint8 (0-255)
    grayscale = np.array(row_data, dtype=np.float64)
    grayscale = np.clip(grayscale, 0, 255).astype(np.uint8)

    # Ensure we have expected source width
    if len(grayscale) != source_width:
        raise ValueError(f"Expected {source_width} pixel values, got {len(grayscale)}")

    # Step 1: Resize grayscale row
    resized_gray = resize_grayscale_row(grayscale, target_width)

    # Step 2: Apply colormap to get RGB
    # Reshape to (1, target_width) for 2D image, then apply colormap
    rgb = apply_colormap(resized_gray.reshape(1, -1))

    # rgb shape is now (1, target_width, 3)

    # Step 3: Encode to PNG
    png_bytes = encode_to_png(rgb)

    return png_bytes, target_width, 1
