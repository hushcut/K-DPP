const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const sharp = require('sharp');
const { root, sources, targets, raster, adaptiveXml, adaptiveXmlPath } = require('./assets.cjs');
const BLUE = [74, 78, 254], GREEN = [99, 214, 139];
const same = (data, at, rgb) => rgb.every((value, i) => data[at + i] === value);

async function pixels(buffer) {
  return sharp(buffer).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
}

async function check(buffer, target) {
  const { size, kind, file } = target;
  const metadata = await sharp(buffer).metadata();
  assert.equal(metadata.width, size, `${file}: width`);
  assert.equal(metadata.height, size, `${file}: height`);
  // PNG IHDR colour type 2 = RGB, not RGBA, palette, or grey.
  if (kind === 'square') {
    assert.equal(buffer[25], 2, `${file}: iOS must be RGB`);
    assert.equal(metadata.hasAlpha, false, `${file}: iOS alpha channel`);
  } else assert.equal(metadata.hasAlpha, true, `${file}: alpha required`);
  const { data } = await pixels(buffer);
  let solidGreen = 0, solidBlue = 0;
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const at = (y * size + x) * 4, alpha = data[at + 3];
    if (!alpha) continue;
    assert.ok(data[at] || data[at + 1] || data[at + 2], `${file}: visible black at ${x},${y}`);
    if (alpha === 255 && same(data, at, GREEN)) solidGreen++;
    if (alpha === 255 && same(data, at, BLUE)) solidBlue++;
    if (kind === 'foreground') {
      // Check the farthest corner of every occupied pixel, not just centres.
      const dx = Math.max(Math.abs(x * 108 / size - 54), Math.abs((x + 1) * 108 / size - 54));
      const dy = Math.max(Math.abs(y * 108 / size - 54), Math.abs((y + 1) * 108 / size - 54));
      assert.ok(Math.hypot(dx, dy) <= 33, `${file}: outside 66dp safe circle`);
      // All foreground artwork consists of opaque colour interiors and AA edges;
      // white here means the tile was accidentally baked into the foreground.
      assert.ok(!same(data, at, [255,255,255]), `${file}: white foreground tile`);
    }
  }
  assert.ok(solidBlue > 0, `${file}: missing blue`);
  assert.ok(solidGreen > 0, `${file}: missing green`);
  for (const [x,y] of [[0,0],[size-1,0],[0,size-1],[size-1,size-1]]) {
    const at = (y * size + x) * 4;
    assert.equal(data[at + 3], kind === 'square' ? 255 : 0, `${file}: corner alpha`);
    if (kind === 'square') assert.ok(same(data, at, [255,255,255]), `${file}: corner must be white`);
  }
  return { solidGreen, solidBlue };
}

async function verify() {
  const source = await sources();
  for (const [name, svg] of Object.entries(source)) {
    for (const fill of svg.matchAll(/fill="(#[\da-f]+)"/gi)) {
      assert.ok(['#4A4EFE', '#63D68B', '#FFFFFF'].includes(fill[1]), `${name}: unexpected colour`);
    }
  }
  let total = 0, iosBytes = 0;
  const outputs = await targets();
  for (const target of outputs) {
    const buffer = await fs.readFile(path.join(root, target.file));
    await check(buffer, target);
    // Also catches hand edits or stale exports after source changes.
    assert.deepEqual(buffer, await raster(source[target.kind], target.size, target.kind === 'square'), `${target.file}: stale output`);
    total += buffer.length;
    if (target.kind === 'square') iosBytes += buffer.length;
  }
  assert.equal(await fs.readFile(path.join(root, adaptiveXmlPath), 'utf8'), adaptiveXml, 'Adaptive XML/reference mismatch');
  assert.ok(iosBytes <= 32 * 1024, `iOS budget exceeded: ${iosBytes} bytes`);
  assert.ok(total < 150 * 1024, `All PNG budget exceeded: ${total} bytes`);

  const tiny = [];
  for (const [kind, size] of [['mark',34],['tile',34],['square',20],['square',29]]) {
    const buffer = await raster(source[kind], size, kind === 'square');
    tiny.push({ kind, size, ...(await check(buffer, {kind,size,file:`preview ${kind} ${size}`})) });
  }
  // The entire leaf interior (and its boundary) must have blue under it, not a
  // transparent moat. Pixel probes straddle the left/right edges of the leaf.
  const markPixels = await pixels(await raster(source.mark, 100));
  for (const [x,y] of [[33,60],[66,60],[48,61]]) {
    const at = (y * 100 + x) * 4;
    assert.equal(markPixels.data[at+3], 255, 'Transparent gap around/in leaf');
  }
  const report = { pngCount:outputs.length, iosBytes, totalPngBytes:total, tiny };
  console.log(JSON.stringify(report, null, 2));
  return report;
}

module.exports = { verify };
if (require.main === module) verify().catch(error => { console.error(error); process.exitCode = 1; });
