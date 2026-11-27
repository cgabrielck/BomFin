import {test,expect} from './fixtures/secure-market';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
test.use({ignoreHTTPSErrors:true,trace:'off'});
const folder=resolve('../../docs/audit/artifacts/s04-04e');
async function save(name:string,value:unknown){await mkdir(folder,{recursive:true});await writeFile(resolve(folder,name),JSON.stringify(value,null,2));}

test('keyboard dialog escape restores focus and search remains usable',async({page})=>{
  await page.goto('/');
  const research=page.getByRole('button',{name:/研究中心/});await research.focus();await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog')).toBeVisible();await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();await expect(research).toBeFocused();
  await page.getByRole('searchbox').focus();await page.keyboard.type('MSFT');
  await expect(page.getByRole('button',{name:'MSFT ↗',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'AAPL ↗',exact:true})).toHaveCount(0);
});

test('quote trace correlates receive, state, consumer and render without credentials',async({page,market})=>{
  test.setTimeout(60000);
  await page.addInitScript(()=>{
    (window as any).__traces=[];
    window.addEventListener('gabfin:market-trace',event=>{
      const values=(window as any).__traces;values.push((event as CustomEvent).detail);if(values.length>100)values.shift();
    });
  });
  await page.goto(market.origin+'/#stock/AAPL');
  await page.getByRole('combobox',{name:'資料模式'}).selectOption('server');
  await expect(page.getByRole('heading',{name:'登入行情工作台'})).toBeVisible();
  const {code}=await market.command('pair');await page.getByLabel('配對碼',{exact:true}).fill(String(code));
  await page.getByRole('button',{name:'配對登入',exact:true}).click();
  await expect(page.getByTestId('last-price')).toHaveText('210.00');
  await expect(page.getByTestId('market-health')).toContainText('連線：已連線');
  await expect.poll(()=>page.evaluate(()=>(window as any).__traces.length)).toBeGreaterThan(0);
  await page.evaluate(()=>(window as any).__traces=[]);
  for(let index=0;index<30;index++){
    await market.command('price',{symbol:'AAPL',price:String(220+index)});
    await expect(page.getByTestId('last-price')).toHaveText(String(220+index));
    await expect.poll(()=>page.evaluate(()=>(window as any).__traces.length)).toBe(index+1);
  }
  const traces=await page.evaluate(()=>(window as any).__traces);
  expect(new Set(traces.map((item:any)=>item.eventId)).size).toBe(30);
  for(const item of traces){expect(item.receivedMono).toBeLessThanOrEqual(item.stateMono);expect(item.stateMono).toBeLessThanOrEqual(item.consumerMono);expect(item.consumerMono).toBeLessThanOrEqual(item.renderMono);}
  expect(JSON.stringify(traces)).not.toMatch(/csrf|token|cookie|password/i);
  // The trace carries timing and identity only. A whitelist of field names is
  // the real guard: a regex over the whole payload cannot tell a leaked
  // value from a field that never existed.
  const allowed=['eventId','instrumentId','epoch','sequence','source','eventAt','providerReceivedAt',
    'processedAt','receivedMono','receivedWall','stateMono','consumerMono','renderMono',
    'sourceToProviderReceiveMs','providerToBrowserReceiveMs','browserReceiveToRenderMs','clockSkew','renderBoundary'];
  for(const item of traces){
    expect(Object.keys(item).sort()).toEqual([...allowed].sort());
    expect(item.source).toBe('fixture');
    expect(String(item.eventAt)).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(item.price).toBeUndefined();
    expect(item.payload).toBeUndefined();
  }
  const api:number[]=[];
  for(let index=0;index<20;index++)api.push(await page.evaluate(async()=>{
    const csrf=document.cookie.split('; ').find(value=>value.startsWith('__Host-gabfin_csrf='))!.split('=').slice(1).join('=');
    const start=performance.now();const response=await fetch('/market/snapshot',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':decodeURIComponent(csrf)},body:JSON.stringify({version:1,keys:[{instrument_id:'11111111-1111-4111-8111-111111111111',channel:'quote',timeframe:null}]})});
    await response.arrayBuffer();if(!response.ok)throw new Error('Snapshot benchmark failed');return performance.now()-start;
  }));
  await save('market-measurements.json',{source:'synthetic TLS fixture',environment:'TLS fixture serving the production bundle (apps/desk-web/dist) over loopback; API snapshot and quote trace numbers come from this environment',traces,newApiMs:api,legacyApiMs:null,apiSnapshotCache:'no-store on every request; each sample re-parses the payload, so this is not an HTTP-cache hit',clockCondition:'one local Windows host; wall clock comparisons diagnostic only',renderBoundary:'two RAF paint opportunity, not hardware pixel presentation'});
});

test('desktop cached navigation and initial content timing are recorded',async({page})=>{
  test.setTimeout(60000);await page.setViewportSize({width:1440,height:1000});
  const initial:number[]=[],navigation:number[]=[];
  for(let index=0;index<20;index++){
    await page.goto('/');await expect(page.getByRole('heading',{name:'值得留意的下一步。'})).toBeVisible();
    initial.push(await page.evaluate(()=>performance.now()));
  }
  for(const symbol of ['MSFT','NVDA']){await page.goto('/#stock/'+symbol);await expect(page.getByTestId('last-price')).not.toHaveText('—');}
  for(let index=0;index<30;index++){
    const symbol=index%2?'MSFT':'NVDA',expected=index%2?'420.00':'140.00';
    const start=await page.evaluate(()=>performance.now());await page.evaluate(symbol=>location.hash='stock/'+symbol,symbol);
    await expect(page.getByTestId('selected-symbol')).toHaveText(symbol);await expect(page.getByTestId('last-price')).toHaveText(expected);
    navigation.push(await page.evaluate(()=>performance.now())-start);
  }
  await save('navigation-measurements.json',{desktopInitialMs:initial,cachedNavigationMs:navigation,condition:'Edge 1440x1000 loopback; browser HTTP cache enabled, no CPU/network throttle; test-observed usable content upper bound',environment:'Vite dev server (playwright baseURL http://127.0.0.1:19045), not the TLS fixture and not the production bundle; first-screen and cached-navigation numbers are dev-server numbers',iphoneHardwareMs:null});
});

test('a provider that reuses an event id in a new epoch is still measured',async({page,market})=>{
  test.setTimeout(60000);
  await page.addInitScript(()=>{
    (window as any).__traces=[];
    window.addEventListener('gabfin:market-trace',event=>{
      const values=(window as any).__traces;values.push((event as CustomEvent).detail);if(values.length>100)values.shift();
    });
  });
  await page.goto(market.origin+'/#stock/AAPL');
  await page.getByRole('combobox',{name:'資料模式'}).selectOption('server');
  const {code}=await market.command('pair');await page.getByLabel('配對碼',{exact:true}).fill(String(code));
  await page.getByRole('button',{name:'配對登入',exact:true}).click();
  await expect(page.getByTestId('last-price')).toHaveText('210.00');
  await expect.poll(()=>page.evaluate(()=>(window as any).__traces.length)).toBeGreaterThan(0);
  const first=await page.evaluate(()=>(window as any).__traces[0]);
  await page.evaluate(()=>(window as any).__traces=[]);
  // The same source facts produce the same event id on purpose. A new epoch
  // makes it a different market event, so it must still be measured.
  await market.command('new_epoch');
  await market.command('replay_quote',{symbol:'AAPL',price:'210.00'});
  await expect.poll(()=>page.evaluate(()=>(window as any).__traces.length)).toBeGreaterThan(0);
  const second=await page.evaluate(()=>(window as any).__traces[0]);
  expect(second.eventId).toBe(first.eventId);
  expect(second.epoch).not.toBe(first.epoch);
});

test('a bar subscriber does not add a second trace for the same quote',async({page,market})=>{
  test.setTimeout(60000);
  await page.addInitScript(()=>{
    (window as any).__traces=[];
    window.addEventListener('gabfin:market-trace',event=>{
      const values=(window as any).__traces;values.push((event as CustomEvent).detail);if(values.length>100)values.shift();
    });
  });
  await page.goto(market.origin+'/#stock/AAPL');
  await page.getByRole('combobox',{name:'資料模式'}).selectOption('server');
  const {code}=await market.command('pair');await page.getByLabel('配對碼',{exact:true}).fill(String(code));
  await page.getByRole('button',{name:'配對登入',exact:true}).click();
  await expect(page.getByTestId('last-price')).toHaveText('210.00');
  await expect.poll(()=>page.evaluate(()=>(window as any).__traces.length)).toBeGreaterThan(0);
  // The chart panel subscribes to the bar channel only, on the same page and
  // at the same time. It must not report a quote trace of its own, so one
  // market event still yields exactly one trace.
  await page.evaluate(()=>(window as any).__traces=[]);
  await market.command('price',{symbol:'AAPL',price:'231.00'});
  await expect(page.getByTestId('last-price')).toHaveText('231.00');
  await expect.poll(()=>page.evaluate(()=>(window as any).__traces.length)).toBe(1);
  const traces=await page.evaluate(()=>(window as any).__traces);
  expect(traces[0].instrumentId).toBe('11111111-1111-4111-8111-111111111111');
});
