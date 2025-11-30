#!/usr/bin/env python3
"""Generate icon files for the application"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_icon():
    """Create the purple M icon in various sizes"""
    sizes = [16, 32, 48, 64, 128, 256]
    images = []

    for size in sizes:
        # Create image with transparent background
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Draw rounded rectangle (purple background)
        corner_radius = size // 6
        draw.rounded_rectangle(
            [0, 0, size-1, size-1],
            radius=corner_radius,
            fill='#7c3aed'
        )

        # Draw "M" text
        font_size = int(size * 0.6)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
        except:
            try:
                font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", font_size)
            except:
                font = ImageFont.load_default()

        # Center the text
        text = "M"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (size - text_width) // 2
        y = (size - text_height) // 2 - bbox[1]

        draw.text((x, y), text, fill='white', font=font)
        images.append(img)

    # Save as ICO for Windows
    images[0].save(
        'icon.ico',
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=images[1:]
    )
    print("Created icon.ico")

    # Save as PNG for other uses
    images[-1].save('icon.png', format='PNG')
    print("Created icon.png (256x256)")

    # Save as ICNS for macOS (just save the largest as PNG, macOS can use it)
    images[-1].save('icon.icns', format='PNG')
    print("Created icon.icns")

if __name__ == '__main__':
    create_icon()
