"""
Visual verification script for resizing strategy.

Creates comparison images showing:
1. Original 200-width patterns
2. Resized 150-width patterns
3. Different resampling methods comparison
4. Quality assessment charts
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from app.processing.image import resize_gray_width


def create_resize_comparison():
    """Create side-by-side comparison of original vs resized."""
    print("\n=== Creating Resize Comparison ===")
    
    # Create test patterns (200 pixels wide)
    height = 100
    patterns = []
    labels = []
    
    # Pattern 1: Vertical stripes (high frequency)
    stripe_pattern = np.zeros((height, 200), dtype=np.uint8)
    for i in range(0, 200, 10):
        stripe_pattern[:, i:i+5] = 255
    patterns.append(stripe_pattern)
    labels.append("Vertical Stripes")
    
    # Pattern 2: Horizontal gradient
    horiz_grad = np.linspace(0, 255, 200, dtype=np.uint8)
    horiz_grad = np.tile(horiz_grad.reshape(1, -1), (height, 1))
    patterns.append(horiz_grad)
    labels.append("Horizontal Gradient")
    
    # Pattern 3: Checkerboard
    checker = np.zeros((height, 200), dtype=np.uint8)
    block_size = 10
    for i in range(0, height, block_size):
        for j in range(0, 200, block_size):
            if ((i // block_size) + (j // block_size)) % 2 == 0:
                checker[i:i+block_size, j:j+block_size] = 255
    patterns.append(checker)
    labels.append("Checkerboard")
    
    # Pattern 4: Random noise
    np.random.seed(42)
    noise = np.random.randint(0, 256, (height, 200), dtype=np.uint8)
    patterns.append(noise)
    labels.append("Random Noise")
    
    # Create comparison image: [Original 200 | Resized 150] for each pattern
    spacing = 20
    total_height = len(patterns) * (height + spacing) + spacing
    total_width = 200 + 150 + 3 * spacing  # Original + Resized + spacings
    
    comparison = Image.new('RGB', (total_width, total_height), color='white')
    
    y_offset = spacing
    for pattern, label in zip(patterns, labels):
        # Original (200 width)
        original_img = Image.fromarray(pattern, mode='L')
        comparison.paste(original_img, (spacing, y_offset))
        
        # Resized (150 width)
        resized = resize_gray_width(pattern, new_width=150)
        resized_img = Image.fromarray(resized, mode='L')
        comparison.paste(resized_img, (200 + 2*spacing, y_offset))
        
        y_offset += height + spacing
    
    # Save
    filename = "resize_comparison.png"
    comparison.save(filename)
    print(f"✅ Saved: {filename}")
    print(f"   Size: {comparison.size}")
    print(f"   Shows: Original (200px) vs Resized (150px)")
    

def create_resampling_methods_comparison():
    """Compare different resampling methods."""
    print("\n=== Creating Resampling Methods Comparison ===")
    
    # Create challenging pattern (diagonal line)
    size = 200
    pattern = np.zeros((size, 200), dtype=np.uint8)
    for i in range(size):
        j = int(i * 200 / size)
        pattern[max(0, i-2):min(size, i+3), max(0, j-2):min(200, j+3)] = 255
    
    # Test each resampling method
    methods = [
        (Image.Resampling.NEAREST, "NEAREST (Fast)"),
        (Image.Resampling.BILINEAR, "BILINEAR (Default)"),
        (Image.Resampling.BICUBIC, "BICUBIC"),
        (Image.Resampling.LANCZOS, "LANCZOS (High Quality)")
    ]
    
    # Create comparison grid
    spacing = 20
    method_width = 150
    method_height = 150  # Scale up for visibility
    
    total_width = len(methods) * (method_width + spacing) + spacing
    total_height = method_height + 2 * spacing
    
    comparison = Image.new('RGB', (total_width, total_height), color='white')
    
    x_offset = spacing
    for resample_method, label in methods:
        # Resize with this method
        resized = resize_gray_width(
            pattern, 
            new_width=150, 
            resample=resample_method
        )
        
        # Scale up for visibility (150→150 square)
        img = Image.fromarray(resized, mode='L')
        img = img.resize((method_width, method_height), Image.Resampling.NEAREST)
        
        comparison.paste(img, (x_offset, spacing))
        x_offset += method_width + spacing
    
    filename = "resize_methods.png"
    comparison.save(filename)
    print(f"✅ Saved: {filename}")
    print(f"   Size: {comparison.size}")
    print(f"   Compares: NEAREST, BILINEAR, BICUBIC, LANCZOS")


def create_gradient_quality_test():
    """Test gradient quality with different methods."""
    print("\n=== Creating Gradient Quality Test ===")
    
    # Create smooth gradients
    gradients = []
    
    # Horizontal gradient (easy case)
    horiz = np.linspace(0, 255, 200, dtype=np.uint8)
    horiz = np.tile(horiz.reshape(1, -1), (50, 1))
    gradients.append(("Horizontal", horiz))
    
    # Vertical gradient (should be unaffected)
    vert = np.linspace(0, 255, 50, dtype=np.uint8)
    vert = np.tile(vert.reshape(-1, 1), (1, 200))
    gradients.append(("Vertical", vert))
    
    # Diagonal gradient (challenging)
    x = np.linspace(0, 1, 200)
    y = np.linspace(0, 1, 50)
    xx, yy = np.meshgrid(x, y)
    diag = ((xx + yy) / 2 * 255).astype(np.uint8)
    gradients.append(("Diagonal", diag))
    
    # Create comparison: Original | BILINEAR | LANCZOS
    methods = [
        ("Original (200px)", None),
        ("BILINEAR (150px)", Image.Resampling.BILINEAR),
        ("LANCZOS (150px)", Image.Resampling.LANCZOS)
    ]
    
    spacing = 10
    grad_height = 50
    
    # All images same visual width (scale resized up)
    display_width = 200
    
    total_width = len(methods) * (display_width + spacing) + spacing
    total_height = len(gradients) * (grad_height + spacing) + spacing
    
    comparison = Image.new('RGB', (total_width, total_height), color='white')
    
    y_offset = spacing
    for grad_label, grad_data in gradients:
        x_offset = spacing
        
        for method_label, resample_method in methods:
            if resample_method is None:
                # Original
                img = Image.fromarray(grad_data, mode='L')
            else:
                # Resized
                resized = resize_gray_width(
                    grad_data, 
                    new_width=150, 
                    resample=resample_method
                )
                # Scale back to 200 for visual comparison
                img = Image.fromarray(resized, mode='L')
                img = img.resize((200, grad_height), Image.Resampling.NEAREST)
            
            comparison.paste(img, (x_offset, y_offset))
            x_offset += display_width + spacing
        
        y_offset += grad_height + spacing
    
    filename = "resize_gradients.png"
    comparison.save(filename)
    print(f"✅ Saved: {filename}")
    print(f"   Size: {comparison.size}")
    print(f"   Shows: Horizontal, Vertical, Diagonal gradients")


def verify_resize_properties():
    """Print numerical verification of resize properties."""
    print("\n" + "="*70)
    print("RESIZE QUALITY VERIFICATION")
    print("="*70)
    
    # Test 1: Width correctness
    print("\n=== Width Correctness ===")
    for original_width in [50, 100, 200, 300]:
        gray = np.random.randint(0, 256, (1, original_width), dtype=np.uint8)
        resized = resize_gray_width(gray, new_width=150)
        print(f"  {original_width:3d} → 150: ✅ {resized.shape[1]} (correct: {resized.shape[1] == 150})")
    
    # Test 2: Uniform preservation
    print("\n=== Uniform Value Preservation ===")
    for value in [0, 64, 128, 192, 255]:
        gray = np.full((1, 200), value, dtype=np.uint8)
        resized = resize_gray_width(gray, new_width=150)
        preserved = np.all(resized == value)
        print(f"  Value {value:3d}: {'✅ Preserved' if preserved else '❌ Changed'}")
    
    # Test 3: Monotonicity
    print("\n=== Gradient Monotonicity ===")
    gray = np.linspace(0, 255, 200, dtype=np.uint8).reshape(1, -1)
    resized = resize_gray_width(gray, new_width=150)
    diffs = np.diff(resized[0])
    monotonic = np.all(diffs >= -1)  # Allow tiny decreases from rounding
    print(f"  Gradient remains monotonic: {'✅ Yes' if monotonic else '❌ No'}")
    print(f"  Min diff: {diffs.min()}, Max diff: {diffs.max()}")
    
    # Test 4: Performance
    print("\n=== Performance Metrics ===")
    import time
    
    # Single row
    gray = np.random.randint(0, 256, (1, 200), dtype=np.uint8)
    start = time.perf_counter()
    for _ in range(1000):
        resize_gray_width(gray, new_width=150)
    elapsed = time.perf_counter() - start
    print(f"  Single row (1000x): {elapsed*1000:.1f}ms total, {elapsed:.3f}ms per resize")
    
    # Batch
    gray = np.random.randint(0, 256, (500, 200), dtype=np.uint8)
    start = time.perf_counter()
    resized = resize_gray_width(gray, new_width=150)
    elapsed = time.perf_counter() - start
    print(f"  Batch 500 rows: {elapsed*1000:.2f}ms ({elapsed/500*1000:.3f}ms per row)")
    
    # Test 5: Memory
    print("\n=== Memory Efficiency ===")
    import sys
    original = np.random.randint(0, 256, (100, 200), dtype=np.uint8)
    resized = resize_gray_width(original, new_width=150)
    
    size_orig = sys.getsizeof(original)
    size_resized = sys.getsizeof(resized)
    ratio = size_resized / size_orig
    
    print(f"  Original: {size_orig:,} bytes (100×200)")
    print(f"  Resized:  {size_resized:,} bytes (100×150)")
    print(f"  Ratio: {ratio:.2f} (expected ~0.75)")
    
    print("\n" + "="*70)
    print("✅ ALL VERIFICATIONS COMPLETE")
    print("="*70)


def main():
    """Run all visualizations."""
    print("="*70)
    print("RESIZE STRATEGY VISUAL VERIFICATION")
    print("="*70)
    
    verify_resize_properties()
    create_resize_comparison()
    create_resampling_methods_comparison()
    create_gradient_quality_test()
    
    print("\n" + "="*70)
    print("✅ ALL RESIZE VISUALIZATIONS CREATED")
    print("="*70)
    print("\nGenerated files:")
    print("  1. resize_comparison.png    - Original vs Resized patterns")
    print("  2. resize_methods.png       - Resampling methods comparison")
    print("  3. resize_gradients.png     - Gradient quality test")
    print("\nPlease review to verify:")
    print("  • Width correctly 200→150")
    print("  • Minimal artifacts with BILINEAR")
    print("  • Smooth gradients preserved")
    print("  • Performance acceptable (<1ms per row)")


if __name__ == "__main__":
    main()
