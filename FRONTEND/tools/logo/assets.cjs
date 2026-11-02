const fs = require('node:fs/promises');
const path = require('node:path');
const sharp = require('sharp');

const root = path.resolve(__dirname, '../..');
const android = 'android/app/src/main/res';
const ios = 'ios/Runner/Assets.xcassets/AppIcon.appiconset';
const densities = [['mdpi', 1], ['hdpi', 1.5], ['xhdpi', 2], ['xxhdpi', 3], ['xxxhdpi', 4]];
const adaptiveXml = `<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@android:color/white" />
    <foreground android:drawable="@mipmap/ic_launcher_foreground" />
</adaptive-icon>
`;
const adaptiveXmlPath = `${android}/mipmap-anydpi-v26/ic_launcher.xml`;

async function sources() {
  const mark = await fs.readFile(path.join(root, 'assets/images/kdpp_logo_mark.svg'), 'utf8');
  const tile = await fs.readFile(path.join(root, 'assets/images/kdpp_logo_tile.svg'), 'utf8');
  const inner = svg => svg.match(/<g id="mark"[^>]*>([\s\S]*?)<\/g>/)?.[1].trim();
  if (!inner(mark) || inner(mark) !== inner(tile)) throw new Error('Mark and tile artwork differ');
  if (!tile.includes('rx="27"')) throw new Error('Tile must declare its corner radius');
  // Same artwork/spacing as the tile, with a square white background for iOS.
  const square = tile.replace('rx="27"', 'rx="0"');
  // Adaptive icons have their own framing: 70% scale, centred on 108dp.
  // verify.cjs checks every occupied pixel against the 66dp safety circle.
  const foreground = `<svg xmlns="http://www.w3.org/2000/svg" width="108" height="108" viewBox="0 0 108 108"><g transform="translate(19 19) scale(.70)">${inner(mark)}</g></svg>`;
  return { mark, tile, square, foreground };
}

async function targets() {
  const result = [1, 2, 3].map(scale => ({
    file: `assets/images/${scale === 1 ? '' : `${scale}.0x/`}kdpp_logo.png`,
    size: 96 * scale, kind: 'mark',
  }));
  for (const [density, scale] of densities) {
    result.push({ file: `${android}/mipmap-${density}/ic_launcher.png`, size: 48 * scale, kind: 'tile' });
    result.push({ file: `${android}/mipmap-${density}/ic_launcher_foreground.png`, size: 108 * scale, kind: 'foreground' });
  }
  const catalog = JSON.parse(await fs.readFile(path.join(root, ios, 'Contents.json'), 'utf8'));
  const seen = new Map();
  for (const entry of catalog.images) {
    if (!entry.filename) continue;
    if (path.basename(entry.filename) !== entry.filename) throw new Error('Invalid icon filename');
    const [width, height] = entry.size.split('x').map(Number);
    const size = width * Number.parseFloat(entry.scale);
    if (width !== height || !Number.isInteger(size) || size <= 0) throw new Error('Invalid icon dimensions');
    if (seen.has(entry.filename) && seen.get(entry.filename) !== size) throw new Error('Conflicting icon dimensions');
    seen.set(entry.filename, size);
  }
  if (seen.size !== 15) throw new Error(`Review changed iOS catalog: expected 15 unique PNGs, got ${seen.size}`);
  for (const [file, size] of seen) result.push({ file: `${ios}/${file}`, size, kind: 'square' });
  return result;
}

async function raster(svg, size, rgb = false) {
  // Render every size from vector; do not downsample a large PNG. SVG intrinsic
  // dimensions equal output dimensions so the SVG renderer antialiases at 1x.
  const sized = svg.replace(/(<svg\b[^>]*\bwidth=")[^"]+/, `$1${size}`)
    .replace(/(<svg\b[^>]*\bheight=")[^"]+/, `$1${size}`);
  let image = sharp(Buffer.from(sized));
  if (rgb) image = image.flatten({ background: '#FFFFFF' }).removeAlpha().toColourspace('srgb');
  // Truecolour avoids palette quantization drifting the two brand colours.
  return image.png({ compressionLevel: 9, adaptiveFiltering: true, palette: false }).toBuffer();
}

module.exports = { root, android, ios, adaptiveXml, adaptiveXmlPath, sources, targets, raster };
