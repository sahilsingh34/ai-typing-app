"""
KeyWise AI — Icon Generator
Run this once to create assets/icon.ico for PyInstaller builds.
"""
import os
from PIL import Image, ImageDraw


def create_icon():
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = []

    for s in sizes:
        img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        pad = max(1, s // 16)

        # Outer circle
        d.ellipse([pad, pad, s - pad, s - pad], fill='#7C3AED')
        # Inner highlight
        hi = pad + s // 7
        d.ellipse([hi, hi, s - hi, s - hi], fill='#9F67FF')
        # Border
        d.ellipse([pad, pad, s - pad, s - pad],
                  outline='#5B21B6', width=max(1, s // 16))

        # Draw "K"
        lw = max(1, s // 10)
        x1, x2 = s // 3, s * 2 // 3
        y1, y2 = s // 4, s * 3 // 4
        mid = s // 2
        d.line([(x1, y1), (x1, y2)], fill='white', width=lw)
        d.line([(x1, mid), (x2, y1)], fill='white', width=lw)
        d.line([(x1, mid), (x2, y2)], fill='white', width=lw)

        images.append(img)

    os.makedirs('assets', exist_ok=True)
    images[0].save(
        'assets/icon.ico',
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    print('✅  Icon saved to assets/icon.ico')


if __name__ == '__main__':
    create_icon()
