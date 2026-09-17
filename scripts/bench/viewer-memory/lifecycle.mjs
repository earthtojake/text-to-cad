// Same-tab CAD lifecycle QA. Starts its own browser, uses an existing viewer.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { viewerRuntimeFingerprint, verifyServedViewerClient } from './fingerprint.mjs';
import { installWorkerProbe } from './worker-probe.mjs';
const require = createRequire(new URL('../../../apps/web/package.json', import.meta.url));
const { chromium } = require(process.env.PLAYWRIGHT_FROM || 'playwright');

const args = {};
for (let i=2;i<process.argv.length;i+=2) {
  const flag=process.argv[i];
  if (!['--url','--file','--other','--out','--first-part','--animation-ms','--edit-target','--edit-variant','--edit-cycles','--min-lod'].includes(flag) || !process.argv[i+1]) {
    throw new Error('Usage: lifecycle.mjs --url ORIGIN --file repeated.step --other assembly.step --out REPORT.json [--first-part box_1]');
  }
  args[flag.slice(2)]=process.argv[i+1];
}
if (!args.url || !args.file || !args.other || !args.out) throw new Error('--url, --file, --other and --out are required');
const base=args.url.replace(/\/+$/, '');
const repeatedFile=args.file, otherFile=args.other;
const firstPart=args['first-part'] || 'box_1';
const animationMs=Number(args['animation-ms'] || 0);
const minimumLevel=Number(args['min-lod'] || 0);
if(!Number.isInteger(minimumLevel)||minimumLevel<0||minimumLevel>3)throw new Error('--min-lod must be 0–3');
if (!Number.isInteger(animationMs) || animationMs < 0 || animationMs > 30000) throw new Error('--animation-ms must be 0–30000');
const editCycles=Number(args['edit-cycles'] || 0);
if(!Number.isInteger(editCycles)||editCycles<0||editCycles>12||(editCycles>0&&editCycles<4))throw new Error('--edit-cycles must be 0 or 4–12; plateau checks require two observations of each revision');
const loadTimings=[];
const runtimeFingerprintAtStart=viewerRuntimeFingerprint();
const startedAt=new Date().toISOString();
const servedClientProof=await verifyServedViewerClient(base);
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
let editFixture=null;
if(editCycles>0){
  const target=path.resolve(args['edit-target'] || ''), variant=path.resolve(args['edit-variant'] || '');
  const models=path.join(repo,'models')+path.sep;
  if(!target.startsWith(models)||!variant.startsWith(models)||!target.endsWith('.step')||!variant.endsWith('.step'))throw new Error('Edit fixtures must be explicit .step paths beneath models/');
  if(fs.existsSync(target+'.json')||fs.existsSync(variant+'.json'))throw new Error('Use geometry-only edit fixtures without annotation sidecars');
  const original=fs.readFileSync(target),replacement=fs.readFileSync(variant),stat=fs.statSync(target);
  if(original.equals(replacement))throw new Error('Edit fixtures must contain different STEP bytes');
  editFixture={target,variant,original,replacement,stat};
}
function publishEditBytes(bytes){
  const temporary=editFixture.target+'.lifecycle-tmp';
  fs.writeFileSync(temporary,bytes);fs.renameSync(temporary,editFixture.target);
}
const git=(...argv)=>execFileSync('git',argv,{cwd:repo,encoding:'utf8'}).trim();
const revision=git('rev-parse','HEAD');
const runtimeChanges=git('status','--porcelain','--','packages/core/src','packages/ui/src','apps/web/src','packages/cadgen/src/cadgen');
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'viewer-cycle-'));
const errors=[];
const failed=[];
const badResponseTasks=[];
const context=await chromium.launchPersistentContext(profile,{
  headless:true, viewport:{width:1400,height:900},
  args:['--use-angle=metal','--enable-precise-memory-info','--disable-features=PrivateNetworkAccessSendPreflights']
});
let page;
try {
page=context.pages()[0] || await context.newPage();
await page.addInitScript(installWorkerProbe);
await page.addInitScript(level=>{window.__CAD_VIEWER_MIN_LOD__=level},minimumLevel);
await page.addInitScript(() => {
  const stats={liveBytes:0,peakBytes:0,liveBufferCount:0,peakBufferCount:0,uploads:0,deletes:0,draws:0,instancedDraws:0};
  const sizes=new WeakMap();
  const bound=new WeakMap();
  window.__cycleGpu=stats;
  const patch=(proto)=>{
    if(!proto || proto.__cyclePatched)return; proto.__cyclePatched=true;
    const bindBuffer=proto.bindBuffer,bufferData=proto.bufferData,deleteBuffer=proto.deleteBuffer;
    proto.bindBuffer=function(target,buffer){let map=bound.get(this);if(!map){map=new Map();bound.set(this,map)}map.set(target,buffer);return bindBuffer.apply(this,arguments)};
    proto.bufferData=function(target,source){const size=typeof source==='number'?source:(source?.byteLength||0);const buffer=bound.get(this)?.get(target);if(buffer){const old=sizes.get(buffer)||0;if(!old){stats.liveBufferCount++;stats.peakBufferCount=Math.max(stats.peakBufferCount,stats.liveBufferCount)}sizes.set(buffer,size);stats.liveBytes+=size-old;stats.peakBytes=Math.max(stats.peakBytes,stats.liveBytes)}stats.uploads++;return bufferData.apply(this,arguments)};
    proto.deleteBuffer=function(buffer){const old=sizes.get(buffer)||0;if(old){stats.liveBytes-=old;stats.liveBufferCount--;sizes.set(buffer,0);stats.deletes++}return deleteBuffer.apply(this,arguments)};
    for(const name of ['drawElements','drawArrays','drawElementsInstanced','drawArraysInstanced']){const original=proto[name];if(typeof original!=='function')continue;proto[name]=function(){stats.draws++;if(name.includes('Instanced'))stats.instancedDraws++;return original.apply(this,arguments)}}
  };
  patch(window.WebGLRenderingContext?.prototype); patch(window.WebGL2RenderingContext?.prototype);
});
page.on('pageerror',e=>errors.push(String(e?.message||e)));
page.on('console',message=>{
  if(message.type()!=='error')return;
  const location=message.location()?.url||'';
  if(location.includes('/__tess_cache/') && /404/.test(message.text()))return;
  errors.push(`console: ${message.text()}`);
});
page.on('requestfailed',r=>failed.push(`${r.failure()?.errorText||'failed'} ${r.url()}`));
page.on('response',response=>{
  if(response.status()<400)return;
  if(response.status()===404 && response.url().includes('/__tess_cache/'))return;
  badResponseTasks.push(response.text()
    .then(body=>({status:response.status(),url:response.url(),body:body.slice(0,2000)}))
    .catch(()=>({status:response.status(),url:response.url(),body:null})));
});

async function waitLoaded(file,previousModelKey=null){
  await page.waitForFunction(({expected,previousModelKey,minimumLevel})=>{
    const browse=[...document.querySelectorAll('button')].some(b=>b.getAttribute('aria-label')===`Browse ${expected}`);
    const c=window.__cadMeshCost;
    const key=window.__cadModelPlacement?.modelKey;
    const lod=window.__cadViewportLod?.();
    const entries=window.__cadSceneSync?.entries||[],scene=entries[entries.length-1];
    return browse && c && c.final===true && key && key!==previousModelKey &&
      c.loadedComponents===c.totalComponents && scene?.records===c.occurrenceCount && scene.atMs>=Math.floor(c.at) &&
      (minimumLevel===0 || (lod?.minimumLevel===minimumLevel && lod.belowMinimum===0 && !lod.busy && !lod.pendingEvaluation));
  },{expected:file,previousModelKey,minimumLevel},{timeout:120000});
  const finalPublicationObservedAt=performance.now();
  process.stderr.write(`complete ${file}\n`);
  await page.waitForTimeout(900);
  return finalPublicationObservedAt;
}
async function choose(file){
  let button=page.locator('button[aria-label^="Browse "]:visible').first();
  if(await button.count()===0){await page.getByRole('button',{name:'Toggle CAD Viewer',exact:true}).click({force:true});button=page.locator('button[aria-label^="Browse "]:visible').first();}
  await button.click({force:true});
  const previousModelKey=await page.evaluate(()=>window.__cadModelPlacement?.modelKey);
  const started=performance.now();
  await page.getByRole('menuitem',{name:file,exact:true}).click();
  const readyAt=await waitLoaded(file,previousModelKey);
  loadTimings.push({file,kind:'same-tab-switch',throughFinalPublicationMs:readyAt-started,throughSettleMs:performance.now()-started,settleMs:900});
}
const cdp=await context.newCDPSession(page);
async function collect(label,forceGc=true){
  if(forceGc){await cdp.send('HeapProfiler.collectGarbage');await page.waitForTimeout(700)}
  return page.evaluate(label=>({
    label,
    file:[...document.querySelectorAll('button')].find(b=>b.getAttribute('aria-label')?.startsWith('Browse '))?.getAttribute('aria-label')?.slice(7)||'',
    probe:window.__cadRenderMemoryProbe?.()||null,
    lod:window.__cadViewportLod?.()||null,
    workers:window.__cadWorkerProbe?{...window.__cadWorkerProbe}:null,
    gpu:{...window.__cycleGpu},
    heap:performance.memory?{used:performance.memory.usedJSHeapSize,total:performance.memory.totalJSHeapSize}:null,
    limitation:window.__cadRenderMemoryProbe?.()?.memoryPolicy?.lastLimitation ?? window.__cadViewerMemory?.lastLimitation ?? null,
    inspector:(document.body?.innerText||'').split('\n').slice(-12)
  }),label);
}

const navigationStarted=performance.now();
await page.goto(`${base}/?file=${encodeURIComponent(repeatedFile)}`,{waitUntil:'domcontentloaded',timeout:120000});
const readyAt=await waitLoaded(repeatedFile);
loadTimings.push({file:repeatedFile,kind:'fresh-browser-navigation',throughFinalPublicationMs:readyAt-navigationStarted,throughSettleMs:performance.now()-navigationStarted,settleMs:900});
const snapshots=[];
snapshots.push(await collect('repeated-initial'));
const selectorsBefore=snapshots[0].probe?.assetCaches?.selector?.entries ?? null;
let firstPickMethod='canvas';
// Sweep a small central grid: the repeated fixture spans most of this region.
for(const [x,y] of [[570,430],[500,430],[640,430],[570,360],[570,500]]){
  await page.mouse.move(x,y); await page.waitForTimeout(120); await page.mouse.click(x,y); await page.waitForTimeout(350);
  const entries=await page.evaluate(()=>window.__cadRenderMemoryProbe?.().assetCaches?.selector?.entries||0);
  if(entries>selectorsBefore)break;
}
let selectorsAfter=await page.evaluate(()=>window.__cadRenderMemoryProbe?.().assetCaches?.selector?.entries||0);
if(selectorsAfter<=selectorsBefore){
  firstPickMethod='tree-expand-fallback';
  const demandStarted=performance.now();
  await page.getByRole('button',{name:`Expand ${firstPart}`,exact:true}).click();
  await page.waitForFunction(before=>(window.__cadRenderMemoryProbe?.().assetCaches?.selector?.entries||0)>before,selectorsBefore,{timeout:30000});
  selectorsAfter=await page.evaluate(()=>window.__cadRenderMemoryProbe?.().assetCaches?.selector?.entries||0);
  loadTimings.push({file:repeatedFile,kind:'first-tree-topology-demand',throughSelectorReadyMs:performance.now()-demandStarted});
}
snapshots.push(await collect('repeated-after-first-pick'));

const sequence=[otherFile,repeatedFile,otherFile,repeatedFile,otherFile,repeatedFile];
for(let i=0;i<sequence.length;i++){
  await choose(sequence[i]);
  // The initial pick above already exercises lazy selector loading. Preserve
  // that tab selection across switches and move hover outside the viewport so
  // every plateau sample measures the same interaction state. Clicking a fixed
  // screen coordinate here selects different topology after camera restoration,
  // legitimately changing the size of Three's selection buffers.
  await page.mouse.move(1,1);await page.waitForTimeout(180);
  snapshots.push(await collect(`cycle-${i+1}-${sequence[i]}`));
}
await page.getByRole('button',{name:'Orbit',exact:true}).click();
await page.mouse.move(550,430);
await page.evaluate(()=>{
  const sample={frames:[],drawCalls:[],active:true,last:performance.now(),drawBase:window.__cycleGpu.draws};
  window.__cycleOrbit=sample;
  const frame=(now)=>{
    if(!sample.active)return;
    sample.frames.push(now-sample.last);
    sample.drawCalls.push(window.__cycleGpu.draws-sample.drawBase);
    sample.last=now;sample.drawBase=window.__cycleGpu.draws;
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
});
await page.mouse.down();
// Keep the camera moving for 100 steps, at least 40 ms apart. rAF intervals
// measure browser presentation cadence during interaction, not GPU time.
const orbitStarted=performance.now();
for(let i=0;i<100;i++){
  const angle=i*Math.PI/25;
  await page.mouse.move(550+90*Math.sin(angle),430+55*(1-Math.cos(angle)));
  await page.waitForTimeout(40);
}
await page.mouse.up();
const orbit=await page.evaluate(()=>{
  const sample=window.__cycleOrbit;
  sample.active=false;
  const summarize=(values)=>{
    const sorted=values.slice(2).sort((a,b)=>a-b);
    const at=(q)=>sorted.length ? sorted[Math.min(sorted.length-1,Math.ceil(sorted.length*q)-1)] : null;
    return {samples:sorted.length,p50:at(0.5),p95:at(0.95),max:at(1)};
  };
  return {frameIntervalsMs:summarize(sample.frames),drawCallsPerFrame:summarize(sample.drawCalls),rawFrameIntervalsMs:sample.frames,rawDrawCallsPerFrame:sample.drawCalls};
});
orbit.durationMs=performance.now()-orbitStarted;
await page.waitForTimeout(350);
snapshots.push(await collect('repeated-after-final-orbit'));
if(animationMs>0 || editFixture){
  await page.getByRole('button',{name:'Exit orbit',exact:true}).click();
}

let animation=null;
if(animationMs>0){
  await page.getByRole('tab',{name:'Animation',exact:true}).click();
  const before=await collect('repeated-before-animation');
  await page.getByRole('button',{name:'Play animation',exact:true}).first().click();
  await page.evaluate(()=>{
    const sample={frames:[],active:true,last:performance.now(),draws:window.__cycleGpu.draws};
    window.__cycleAnimation=sample;
    const frame=now=>{if(!sample.active)return;sample.frames.push(now-sample.last);sample.last=now;requestAnimationFrame(frame)};
    requestAnimationFrame(frame);
  });
  await page.waitForTimeout(animationMs);
  await page.getByRole('button',{name:'Pause animation',exact:true}).first().click();
  const frames=await page.evaluate(()=>{const sample=window.__cycleAnimation;sample.active=false;return {frames:sample.frames.slice(2),draws:window.__cycleGpu.draws-sample.draws}});
  const after=await collect('repeated-after-animation');
  const sorted=frames.frames.slice().sort((a,b)=>a-b);
  const percentile=q=>sorted[Math.min(sorted.length-1,Math.max(0,Math.ceil(sorted.length*q)-1))]??null;
  animation={durationMs:animationMs,frameIntervalsMs:{samples:sorted.length,p50:percentile(.5),p95:percentile(.95),max:percentile(1)},draws:frames.draws,before,after};
  snapshots.push(after);
}

const edits=[];
if(editFixture){
  for(let i=0;i<editCycles;i++){
    const previousRevision=await page.evaluate(()=>window.__cadMeshCost?.meshRevision);
    if(!previousRevision)throw new Error('The client must expose the published mesh revision for same-file edits');
    const variant=i%2===0;
    const started=performance.now();
    publishEditBytes(variant?editFixture.replacement:editFixture.original);
    await page.waitForFunction(({previous,minimumLevel})=>{
      const cost=window.__cadMeshCost;
      const entries=window.__cadSceneSync?.entries || [];
      const scene=entries[entries.length-1];
      const lod=window.__cadViewportLod?.();
      return cost?.final===true && cost.meshRevision && cost.meshRevision!==previous &&
        cost.loadedComponents===cost.totalComponents && scene?.records===cost.occurrenceCount && scene.atMs>=Math.floor(cost.at) &&
        (minimumLevel===0 || (lod?.belowMinimum===0 && !lod.busy && !lod.pendingEvaluation));
    },{previous:previousRevision,minimumLevel},{timeout:30000});
    const readyAt=performance.now();
    process.stderr.write(`complete edit ${i+1}\n`);
    await page.waitForTimeout(900);
    const snapshot=await collect(`edit-${i+1}-${variant?'variant':'original'}`);
    edits.push({cycle:i+1,variant,throughFinalPublicationMs:readyAt-started,snapshot});
  }
}

const badResponses=await Promise.all(badResponseTasks);
const result={
  startedAt,
  servedClientProof,
  browserVersion:context.browser()?.version() || null,
  runtimeFingerprintAtStart,
  runtimeFingerprintAtEnd: viewerRuntimeFingerprint(),
  generatedAt:new Date().toISOString(),
  loadTimings,
  orbit,
  animation,
  edits,
  firstPick:{method:firstPickMethod,selectorsBefore,selectorsAfter},
  snapshots,
  pageErrors:errors,
  badResponses,
  requestFailures:failed,
  assertions:{
    repeatedInstancing:snapshots[0].probe?.surfaceInstanceSets===2 && snapshots[0].probe?.surfaceInstances===24,
    lazyInitially:selectorsBefore===0,
    firstDemandLoaded:selectorsAfter>selectorsBefore,
    noPageErrors:errors.length===0 && badResponses.length===0,
    noUnexpectedRequestFailures:failed.every(value=>value.startsWith('net::ERR_ABORTED ')),
    noLimitations:snapshots.every(s=>s.limitation==null),
  }
};
const repeated=snapshots.filter(s=>s.file===repeatedFile);
result.repeatedPlateau={
  gpuLiveBytes:repeated.map(s=>s.gpu.liveBytes),
  gpuLiveBufferCount:repeated.map(s=>s.gpu.liveBufferCount),
  heapUsed:repeated.map(s=>s.heap?.used),
  probeOwned:repeated.map(s=>s.probe?.memoryPolicy?.estimatedOwnedBytes),
  surfaceSets:repeated.map(s=>s.probe?.surfaceInstanceSets),
  deletes:repeated.map(s=>s.gpu.deletes)
};
const returned=repeated.filter(s=>s.label.startsWith('cycle-'));
result.assertions.gpuPlateau=returned.length===3 && new Set(returned.map(s=>s.gpu.liveBytes)).size===1 && new Set(returned.map(s=>s.gpu.liveBufferCount)).size===1;
result.assertions.workersReclaimed=snapshots.every(s=>(s.probe?.memoryPolicy?.retainedByCategory?.workerResidentEstimated || 0)===0);
if(minimumLevel>0)result.assertions.minimumDetail=snapshots.every(s=>s.lod?.minimumLevel===minimumLevel && s.lod.belowMinimum===0);
if(animation){
  result.assertions.animationFrames=animation.frameIntervalsMs.samples>10 && animation.draws>10;
  result.assertions.animationGpuPlateau=animation.before.gpu.liveBytes===animation.after.gpu.liveBytes && animation.before.gpu.liveBufferCount===animation.after.gpu.liveBufferCount;
}
if(edits.length){
  const fixtureSamples=[true,false].map(variant=>edits.filter(edit=>edit.variant===variant).map(edit=>edit.snapshot));
  result.assertions.editGpuPlateau=fixtureSamples.every(samples=>
    samples.length>1 &&
    new Set(samples.map(s=>s.gpu.liveBytes)).size===1 &&
    new Set(samples.map(s=>s.gpu.liveBufferCount)).size===1
  );
  result.assertions.editWorkersReclaimed=edits.every(edit=>(edit.snapshot.probe?.memoryPolicy?.retainedByCategory?.workerResidentEstimated||0)===0);
  result.editPlateau={kind:'saved STEP byte replacement in the same tab; source execution excluded',target:editFixture.target,variant:editFixture.variant,fixtureIdentity:edits.map(edit=>edit.variant?'variant':'original'),heapUsed:edits.map(edit=>edit.snapshot.heap?.used),ownedBytes:edits.map(edit=>edit.snapshot.probe?.memoryPolicy?.estimatedOwnedBytes),gpuBytes:edits.map(edit=>edit.snapshot.gpu.liveBytes),gpuBufferCounts:edits.map(edit=>edit.snapshot.gpu.liveBufferCount)};
}
result.environment={node:process.version,platform:process.platform,arch:process.arch,cpu:os.cpus()[0]?.model,totalMemoryBytes:os.totalmem(),revision,runtimeChangesAtStart:runtimeChanges,runtimeChangesAtEnd:git('status','--porcelain','--','packages/core/src','packages/ui/src','apps/web/src','packages/cadgen/src/cadgen'),url:base,file:repeatedFile,other:otherFile,browserCache:'fresh profile initially; same profile for switches',tessellationCache:'preexisting server cache; neither cleared nor controlled by this harness',plateauInteraction:'initial selection preserved across tab switches; pointer parked outside viewport content',viewport:{width:1400,height:900},angle:'metal',lod:'default',minimumLevel};
fs.mkdirSync(path.dirname(path.resolve(args.out)),{recursive:true});
fs.writeFileSync(args.out,JSON.stringify(result,null,2)+'\n');
if (!Object.values(result.assertions).every(Boolean)) process.exitCode=1;
console.log(JSON.stringify(result,null,2));
await cdp.detach().catch(()=>{});
} catch(error) {
  const failure={error:String(error),pageErrors:errors,badResponses:await Promise.all(badResponseTasks),requestFailures:failed,url:page?.url(),body:await page?.locator('body').innerText().catch(()=>null),html:await page?.content().catch(()=>null)};
  fs.mkdirSync(path.dirname(path.resolve(args.out)),{recursive:true});
  fs.writeFileSync(path.resolve(args.out)+'.failure.json',JSON.stringify(failure,null,2)+'\n');
  await page?.screenshot({path:path.resolve(args.out)+'.failure.png'}).catch(()=>{});
  throw error;
} finally {
if(editFixture){publishEditBytes(editFixture.original);fs.utimesSync(editFixture.target,editFixture.stat.atime,editFixture.stat.mtime)}
await context.close();fs.rmSync(profile,{recursive:true,force:true});
}
