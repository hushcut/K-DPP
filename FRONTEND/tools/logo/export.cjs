const fs = require('node:fs/promises');
const path = require('node:path');
const { root, sources, targets, raster, adaptiveXml, adaptiveXmlPath } = require('./assets.cjs');

async function main() {
  const source = await sources();
  const outputs = await targets();
  for (const target of outputs) {
    const file = path.join(root, target.file);
    const buffer = await raster(source[target.kind], target.size, target.kind === 'square');
    await fs.mkdir(path.dirname(file), { recursive: true });
    await fs.writeFile(file, buffer);
  }
  const xmlFile = path.join(root, adaptiveXmlPath);
  await fs.mkdir(path.dirname(xmlFile), { recursive: true });
  await fs.writeFile(xmlFile, adaptiveXml);
  console.log(`Exported ${outputs.length} PNGs and Android adaptive XML.`);
  await require('./verify.cjs').verify();
}

main().catch(error => { console.error(error); process.exitCode = 1; });
