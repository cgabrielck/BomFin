import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { compile } from 'json-schema-to-typescript';

const root = new URL('../', import.meta.url);
const schema = JSON.parse(await readFile(new URL('schemas/gabfin-1.0.json', root), 'utf8'));
const target = new URL('apps/desk-web/src/shared/contracts/generated.ts', root);
const text = await compile(schema, 'GabFinContracts', {
  bannerComment:
    '/* Generated from schemas/gabfin-1.0.json. Run npm run contracts; do not edit. */',
  style: { singleQuote: true, semi: true },
  unknownAny: true,
});
await mkdir(fileURLToPath(new URL('./', target)), { recursive: true });
await writeFile(target, text);
console.log('Generated browser contract types from canonical schema');
