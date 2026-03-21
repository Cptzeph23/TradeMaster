#!/usr/bin/env bash
# ============================================================
# Generates all required PWA icon sizes from the SVG favicon
# Requires: Inkscape or rsvg-convert or ImageMagick (convert)
# Run once: bash generate_icons.sh
# ============================================================
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
ICONS_DIR="$PROJECT_DIR/static/images/icons"
SVG_SOURCE="$PROJECT_DIR/static/images/favicon.svg"

mkdir -p "$ICONS_DIR"

echo "Generating PWA icons from $SVG_SOURCE..."

SIZES=(72 96 128 144 192 512)

for SIZE in "${SIZES[@]}"; do
  OUTPUT="$ICONS_DIR/icon-${SIZE}.png"

  # Try Inkscape first (best SVG rendering)
  if command -v inkscape &>/dev/null; then
    inkscape --export-type=png \
             --export-filename="$OUTPUT" \
             --export-width="$SIZE" \
             --export-height="$SIZE" \
             "$SVG_SOURCE" 2>/dev/null \
    && echo "  ✅ ${SIZE}x${SIZE} (inkscape)" && continue
  fi

  # Try rsvg-convert (fast, good quality)
  if command -v rsvg-convert &>/dev/null; then
    rsvg-convert -w "$SIZE" -h "$SIZE" -o "$OUTPUT" "$SVG_SOURCE" 2>/dev/null \
    && echo "  ✅ ${SIZE}x${SIZE} (rsvg-convert)" && continue
  fi

  # Try ImageMagick convert
  if command -v convert &>/dev/null; then
    convert -background none -size "${SIZE}x${SIZE}" "$SVG_SOURCE" "$OUTPUT" 2>/dev/null \
    && echo "  ✅ ${SIZE}x${SIZE} (imagemagick)" && continue
  fi

  # Last resort — Python cairosvg
  if python3 -c "import cairosvg" 2>/dev/null; then
    python3 -c "
import cairosvg
cairosvg.svg2png(
    url='$SVG_SOURCE',
    write_to='$OUTPUT',
    output_width=$SIZE,
    output_height=$SIZE
)"  && echo "  ✅ ${SIZE}x${SIZE} (cairosvg)" && continue
  fi

  echo "  ⚠ Could not generate ${SIZE}x${SIZE} — install inkscape, rsvg-convert, or imagemagick"
  echo "    sudo apt install inkscape   OR   sudo apt install librsvg2-bin"
done

echo ""
echo "Icons saved to $ICONS_DIR/"
echo "Run: python manage.py collectstatic --noinput"