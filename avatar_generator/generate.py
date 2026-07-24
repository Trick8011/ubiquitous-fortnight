#!/usr/bin/env python3
"""CLI tool that generates unique, deterministic identicon-style avatars.

No network access or API key is required: an avatar is derived entirely
from a hash of its seed string, so the same seed always produces the same
image (like GitHub/DiceBear identicons).
"""
import argparse
import hashlib
import colorsys
import sys
import uuid

from PIL import Image, ImageDraw

DEFAULT_GRID = 5
DEFAULT_SIZE = 512
DEFAULT_PADDING = 0.1  # fraction of image size reserved as border


def _seed_hash(seed: str) -> bytes:
    return hashlib.sha256(seed.encode("utf-8")).digest()


def _foreground_color(digest: bytes) -> tuple[int, int, int]:
    hue = digest[0] / 255.0
    r, g, b = colorsys.hls_to_rgb(hue, 0.55, 0.65)
    return round(r * 255), round(g * 255), round(b * 255)


def _background_color(digest: bytes) -> tuple[int, int, int]:
    hue = digest[1] / 255.0
    r, g, b = colorsys.hls_to_rgb(hue, 0.95, 0.35)
    return round(r * 255), round(g * 255), round(b * 255)


def _cell_pattern(digest: bytes, grid: int) -> list[list[bool]]:
    """Build a grid-by-grid boolean matrix, mirrored left-right for symmetry."""
    half_width = (grid + 1) // 2
    pattern = [[False] * grid for _ in range(grid)]
    bit_index = 0
    for row in range(grid):
        for col in range(half_width):
            byte = digest[bit_index % len(digest)]
            bit = (byte >> (bit_index % 8)) & 1
            filled = bit == 1
            pattern[row][col] = filled
            pattern[row][grid - 1 - col] = filled
            bit_index += 1
    return pattern


def generate_avatar(seed: str, size: int = DEFAULT_SIZE, grid: int = DEFAULT_GRID) -> Image.Image:
    """Render a deterministic identicon-style avatar for the given seed."""
    digest = _seed_hash(seed)
    fg = _foreground_color(digest)
    bg = _background_color(digest)
    pattern = _cell_pattern(digest, grid)

    image = Image.new("RGB", (size, size), bg)
    draw = ImageDraw.Draw(image)

    padding = round(size * DEFAULT_PADDING)
    usable = size - 2 * padding
    cell_size = usable / grid

    for row in range(grid):
        for col in range(grid):
            if not pattern[row][col]:
                continue
            x0 = padding + col * cell_size
            y0 = padding + row * cell_size
            x1 = x0 + cell_size
            y1 = y0 + cell_size
            draw.rectangle([x0, y0, x1, y1], fill=fg)

    return image


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a unique, deterministic identicon-style avatar from a seed."
    )
    parser.add_argument(
        "seed",
        nargs="?",
        help="Seed string (e.g. a username) the avatar is derived from. "
        "Omit to generate a random one-off avatar.",
    )
    parser.add_argument(
        "-o", "--output", help="Output file path (default: <seed>.png, or avatar.png for random seeds)"
    )
    parser.add_argument(
        "-s", "--size", type=int, default=DEFAULT_SIZE, help=f"Image size in pixels (default: {DEFAULT_SIZE})"
    )
    parser.add_argument(
        "-g", "--grid", type=int, default=DEFAULT_GRID, help=f"Pattern grid dimension (default: {DEFAULT_GRID})"
    )
    parser.add_argument(
        "-n", "--count", type=int, default=1, help="Number of avatars to generate (default: 1)"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if args.size <= 0 or args.grid <= 0:
        print("error: --size and --grid must be positive integers", file=sys.stderr)
        return 1

    for i in range(args.count):
        seed = args.seed if args.seed else str(uuid.uuid4())

        if args.output:
            if args.count == 1:
                output_path = args.output
            else:
                base, _, ext = args.output.rpartition(".")
                ext = ext or "png"
                base = base or args.output
                output_path = f"{base}_{i + 1}.{ext}"
        else:
            output_path = f"{seed}.png"

        image = generate_avatar(seed, size=args.size, grid=args.grid)
        image.save(output_path)
        print(f"seed={seed} -> {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
