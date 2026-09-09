import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const html = readFileSync(new URL('./index.html', import.meta.url), 'utf8');
const section = (start, end) => html.slice(html.indexOf(start), html.indexOf(end, html.indexOf(start)));
class Coordinate {
  constructor(...values) { this.values = values; }
  clone() { return new Coordinate(...this.values); }
  copy(other) { this.values = [...other.values]; return this; }
}
test('motion selection preserves the exact perspective and resets a previously played clip, synchronously', () => {
  const mesh = { isMesh: true, visible: true };
  const newRoot = { traverse: fn => fn(mesh) };
  const action = { time: 4, paused: false, reset() { this.time = 0; return this; }, play() { return this; } };
  const updates = [];
  const mixer = { stopAllAction() {}, update(dt) { updates.push(dt); } };
  const elements = Object.fromEntries(['stats','caveat','tSheaths','tShadow'].map(id => [id,{checked:false}]));
  const camera = {position:new Coordinate(2,3,4),quaternion:new Coordinate(.2,.3,.4,.8), zoom:2.1,near:.002,far:85, updateProjectionMatrix() {}};
  const controls = {target:new Coordinate(-2,.45,1),autoRotate:false};
  const oldRoot = {};
  const operations=[];
  const ready={root:newRoot,mixer,action,duration:6,cords:[{}],sheaths:[{}],internals:[{}],spinning:[],diagnostics:'ready',caveat:'morphs'};
  const c=vm.createContext({camera,controls,userMovedCamera:true,root:oldRoot,playing:true,action:{paused:false},mixer:null,duration:1,
    cords:[],sheaths:[],internals:[],spinning:[],motion:{id:'fist'},preparedMotions:new Map([['wave',ready]]),
    scene:{remove:r=>operations.push(['remove',r]),add:r=>operations.push(['add',r])},
    setPlaying(value){c.playing=value;c.action.paused=!value;},document:{getElementById:id=>elements[id]},
    cordsToggle:{checked:false},internalsToggle:{checked:true},scrub:{value:'760'},clock:{textContent:'4.00 s'},
    menu:{children:[{dataset:{id:'wave'},setAttribute(name,value){this[name]=value;}}]},
    window:{},THREE:{},renderer:{},lastBeat:2,narrate:t=>operations.push(['narrate',t]),
    fetch(){throw Error('selection must not fetch');},frame(){throw Error('selection must not reframe');}});
  const before=JSON.stringify({position:camera.position,quaternion:camera.quaternion,target:controls.target,zoom:camera.zoom,near:camera.near,far:camera.far});
  vm.runInContext(section('function capturePerspective()', 'async function prepareMotion'),c);
  vm.runInContext(section('function activateMotion(next)', 'async function start()'),c);
  assert.equal(c.activateMotion({id:'wave'}),undefined);
  assert.equal(c.root,newRoot); assert.equal(c.playing,false); assert.equal(action.time,0); assert.equal(action.paused,true);
  assert.equal(c.scrub.value,'0'); assert.equal(c.clock.textContent,'0.00 s'); assert.deepEqual(updates,[0]);
  assert.equal(JSON.stringify({position:camera.position,quaternion:camera.quaternion,target:controls.target,zoom:camera.zoom,near:camera.near,far:camera.far}),before);
  assert.equal(ready.cords[0].visible,false);assert.equal(ready.sheaths[0].visible,false);assert.equal(ready.internals[0].visible,true);
  assert.equal(c.menu.children[0]['aria-current'],'true'); assert.equal(c.userMovedCamera,true);
});
test('startup prepares every scene before exposing the controls', async () => {
  const MOTIONS=['fist','wave','pinch','signs','drive'].map(id=>({id}));
  const preparedMotions=new Map(), events=[];
  const elements={hud:{hidden:true},teach:{hidden:true}};
  const c=vm.createContext({MOTIONS,preparedMotions,controls:{autoRotate:false},bar:{style:{}},
    buildMenu(){events.push('menu');},document:{getElementById:id=>elements[id]},
    boot:{classList:{add(){events.push('ready');}},setAttribute(){}},setTimeout,
    async prepareMotion(next){
      assert.equal(elements.hud.hidden,true);assert.equal(elements.teach.hidden,true);
      await Promise.resolve();preparedMotions.set(next.id,{});events.push(next.id);
    },activateMotion(next){assert.equal(preparedMotions.size,5);events.push('activate:'+next.id);},
    fail(){assert.fail('startup must succeed');}});
  vm.runInContext(section('async function start()', 'const MARK_MATERIAL'),c);
  await c.start();
  assert.deepEqual(events,['menu','fist','wave','pinch','signs','drive','activate:fist','ready']);
  assert.equal(elements.hud.hidden,false);assert.equal(elements.teach.hidden,false);assert.equal(c.controls.autoRotate,false);
});
test('the bounded startup reader preserves binary bytes and rejects truncated responses', async () => {
  const expected=Uint8Array.from({length:2051},(_,i)=>i%256), progress=[];
  const response=()=>new Response(new ReadableStream({start(controller){
    for(let i=0;i<expected.length;i+=127)controller.enqueue(expected.slice(i,i+127));controller.close();
  }}),{headers:{'Content-Length':String(expected.length)}});
  const c=vm.createContext({fetch:async()=>response(),Uint8Array,Number});
  vm.runInContext(section('async function readMotionBytes(', 'async function prepareMotion'),c);
  assert.deepEqual(new Uint8Array(await c.readMotionBytes('fixture.glb',v=>progress.push(v))),expected);
  assert.equal(progress.at(-1),1);
  c.fetch=async()=>new Response(new Uint8Array([1,2]),{headers:{'Content-Length':'3'}});
  await assert.rejects(c.readMotionBytes('truncated.glb',()=>{}),/received 2 of 3 bytes/);
});
