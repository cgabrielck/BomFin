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
// Runtime browser validators need only the market graph, not every contract.
const definitions = {};
const queue = ['MarketSnapshot', 'SnapshotFrame', 'UpdateFrame', 'ErrorFrame'];
const scan = value => {
  if (!value || typeof value !== 'object') return;
  if (typeof value.$ref === 'string' && value.$ref.startsWith('#/$defs/')) queue.push(value.$ref.slice(8));
  for (const child of Object.values(value)) scan(child);
};
while(queue.length){
  const name=queue.pop();if(name in definitions)continue;
  if(!schema.$defs[name])throw new Error(`Missing canonical definition ${name}`);
  const definition=structuredClone(schema.$defs[name]);
  // JSON integer values beyond this bound cannot be represented losslessly by JS.
  const bound=value=>{if(!value||typeof value!=='object')return;
    if(value.type==='integer')value.maximum=Math.min(value.maximum??Number.MAX_SAFE_INTEGER,Number.MAX_SAFE_INTEGER);
    for(const child of Object.values(value))bound(child)};
  bound(definition);definitions[name]=definition;scan(definition);
}
await writeFile(new URL('market.schema.json',target),JSON.stringify({$schema:schema.$schema,$defs:definitions},null,2)+'\n');
console.log('Generated browser contract types from canonical schema');
