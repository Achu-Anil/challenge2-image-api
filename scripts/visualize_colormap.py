"""
Visual verification script for colormap.

Creates sample images to visually verify:
1. Full gradient (0-255)
2. Color stop markers
3. Smooth interpolation
4. Sample image with colorization
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.core import setup_logging
from app.processing.image import COLOR_STOPS, COLORMAP_LUT, apply_lut, make_colormap_lut


def create_gradient_visualization(output_path: Path = Path("colormap_gradient.png")):
    """
    Create a visual representation of the full colormap gradient.

    Shows:
    - Full 0-255 gradient as horizontal bar (scaled up for visibility)
    - Color stop markers
    - Value labels
    """
    print("\n=== Creating Gradient Visualization ===")

    # Create gradient: 256 pixels wide, scaled vertically for visibility
    gradient_1d = np.arange(256, dtype=np.uint8)
    gradient_2d = np.tile(gradient_1d, (100, 1))  # 100 pixels tall

    # Apply colormap
    rgb_gradient = apply_lut(gradient_2d, COLORMAP_LUT)

    # Convert to PIL Image
    img = Image.fromarray(rgb_gradient, mode="RGB")

    # Scale up 4x for better visibility
    img = img.resize((1024, 400), Image.Resampling.NEAREST)

    # Add color stop markers
    draw = ImageDraw.Draw(img)

    for stop_idx, stop_color in COLOR_STOPS:
        # Scale position
        x = int(stop_idx * 4)

        # Draw vertical line
        draw.line([(x, 0), (x, 400)], fill=(255, 255, 255), width=2)

        # Add label
        try:
            # Try to load a font, fall back to default
            font = ImageFont.truetype("arial.ttf", 16)
        except:
            font = ImageFont.load_default()

        draw.text((x + 5, 10), f"{stop_idx}", fill=(255, 255, 255), font=font)

    # Save
    img.save(output_path)
    print(f"✅ Saved gradient visualization: {output_path}")
    print(f"   Size: {img.size}, Mode: {img.mode}")

    return output_path


def create_color_stops_chart(output_path: Path = Path("colormap_stops.png")):
    """
    Create a chart showing each color stop with labels.
    """
    print("\n=== Creating Color Stops Chart ===")

    # Create image with color stop swatches
    swatch_width = 100
    swatch_height = 80
    num_stops = len(COLOR_STOPS)

    img_width = swatch_width * num_stops
    img_height = swatch_height + 40  # Extra space for labels

    img = Image.new("RGB", (img_width, img_height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        font_large = ImageFont.truetype("arial.ttf", 14)
        font_small = ImageFont.truetype("arial.ttf", 12)
    except:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    for i, (stop_idx, stop_color) in enumerate(COLOR_STOPS):
        x = i * swatch_width

        # Draw color swatch
        draw.rectangle(
            [(x, 0), (x + swatch_width, swatch_height)], fill=stop_color, outline=(0, 0, 0), width=2
        )

        # Add labels
        # Index label
        text_color = (255, 255, 255) if sum(stop_color) < 400 else (0, 0, 0)
        draw.text((x + 10, 10), f"Gray: {stop_idx}", fill=text_color, font=font_large)

        # RGB label
        draw.text((x + 10, 30), f"RGB: {stop_color}", fill=text_color, font=font_small)

        # Value label below
        draw.text(
            (x + 10, swatch_height + 10), f"Value {stop_idx}", fill=(0, 0, 0), font=font_small
        )

    img.save(output_path)
    print(f"✅ Saved color stops chart: {output_path}")

    return output_path


def create_sample_image(output_path: Path = Path("colormap_sample.png")):
    """
    Create a sample 2D image with various grayscale patterns to visualize colorization.
    """
    print("\n=== Creating Sample Image ===")

    # Create 200x200 test image with various patterns
    img_size = 200

    # Pattern 1: Vertical gradient (each column same, rows 0-255)
    vert_gradient = np.linspace(0, 255, img_size, dtype=np.uint8)
    vert_gradient = np.tile(vert_gradient.reshape(-1, 1), (1, img_size))  # (200, 200)

    # Pattern 2: Horizontal gradient (each row same, cols 0-255)
    horiz_gradient = np.linspace(0, 255, img_size, dtype=np.uint8)
    horiz_gradient = np.tile(horiz_gradient.reshape(1, -1), (img_size, 1))  # (200, 200)

    # Combine patterns side-by-side
    gray_image = np.hstack([vert_gradient, horiz_gradient])  # (200, 400)

    # Apply colormap
    rgb_image = apply_lut(gray_image, COLORMAP_LUT)

    # Save
    img = Image.fromarray(rgb_image, mode="RGB")

    # Scale up 2x for visibility (200x400 -> 400x800)
    img = img.resize((img.width * 2, img.height * 2), Image.Resampling.NEAREST)

    img.save(output_path)
    print(f"✅ Saved sample image: {output_path}")
    print(f"   Size: {img.size}")
    print(f"   Left half: Vertical gradient (dark→light)")
    print(f"   Right half: Horizontal gradient (dark→light)")

    return output_path


def create_comparison_strip(output_path: Path = Path("colormap_comparison.png")):
    """
    Create a comparison showing grayscale vs colorized versions.
    """
    print("\n=== Creating Comparison Strip ===")

    # Create gradient
    gradient = np.arange(256, dtype=np.uint8).reshape(1, 256)
    gradient_tall = np.tile(gradient, (50, 1))  # Make it taller

    # Grayscale version (convert to RGB for stacking)
    gray_rgb = np.stack([gradient_tall] * 3, axis=-1)

    # Colorized version
    color_rgb = apply_lut(gradient_tall, COLORMAP_LUT)

    # Stack vertically with separator
    separator = np.ones((10, 256, 3), dtype=np.uint8) * 255  # White line

    combined = np.vstack([gray_rgb, separator, color_rgb])

    # Convert and save
    img = Image.fromarray(combined, mode="RGB")

    # Scale up for visibility
    img = img.resize((1024, 440), Image.Resampling.NEAREST)

    img.save(output_path)
    print(f"✅ Saved comparison strip: {output_path}")
    print(f"   Top: Original grayscale")
    print(f"   Bottom: Colorized with LUT")

    return output_path


def verify_lut_properties():
    """
    Print LUT properties and verify correctness.
    """
    print("\n=== LUT Properties ===")

    lut = make_colormap_lut()

    print(f"Shape: {lut.shape}")
    print(f"Dtype: {lut.dtype}")
    print(f"Memory: {lut.nbytes} bytes")
    print(f"\nColor Stops:")

    for idx, expected_rgb in COLOR_STOPS:
        actual_rgb = tuple(lut[idx])
        match = "✅" if actual_rgb == expected_rgb else "❌"
        print(f"  {match} Index {idx:3d}: RGB{actual_rgb} (expected {expected_rgb})")

    # Check some interpolated values
    print(f"\nSample Interpolated Values:")
    for idx in [32, 96, 160, 224]:
        rgb = tuple(lut[idx])
        print(f"  Index {idx:3d}: RGB{rgb}")

    # Verify determinism
    lut2 = make_colormap_lut()
    is_deterministic = np.array_equal(lut, lut2)
    print(f"\nDeterministic: {'✅ Yes' if is_deterministic else '❌ No'}")

    # Verify pre-computed matches
    matches_precomputed = np.array_equal(lut, COLORMAP_LUT)
    print(f"Matches pre-computed: {'✅ Yes' if matches_precomputed else '❌ No'}")


def main():
    """Run all visualizations."""
    setup_logging("INFO")

    print("=" * 70)
    print("COLORMAP VISUAL VERIFICATION")
    print("=" * 70)

    # Verify LUT properties
    verify_lut_properties()

    # Create visualizations
    create_gradient_visualization()
    create_color_stops_chart()
    create_sample_image()
    create_comparison_strip()

    print("\n" + "=" * 70)
    print("✅ ALL VISUALIZATIONS CREATED")
    print("=" * 70)
    print("\nGenerated files:")
    print("  1. colormap_gradient.png  - Full gradient with markers")
    print("  2. colormap_stops.png     - Color stop swatches")
    print("  3. colormap_sample.png    - Sample patterns colorized")
    print("  4. colormap_comparison.png - Before/after comparison")
    print("\nPlease review these images to verify:")
    print("  • Smooth color transitions")
    print("  • Correct color stops at defined indices")
    print("  • No banding or artifacts")
    print("  • Visually appealing gradient")


if __name__ == "__main__":
    main()
