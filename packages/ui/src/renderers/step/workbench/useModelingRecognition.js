import { cadResourceCacheKey } from "@text-to-cad/core/client";
import { resolveSurfaceComponents } from "./surfaceResolution.js";
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { loadPackageDescriptor } from '../components/workbench/hooks/packageDescriptorCache.js';
import { completedPackages, completedPackageRevision } from '../render/completedPackageCache.js';
import { completedModelingRecognition, modelingRecognitionKey } from './modelingRecognitionCache.js';
const EMPTY_RESULTS = {};
// A frame, or this long when frames are not running (a hidden page): results never wait on one.
const FLUSH_FALLBACK_MS = 100;

/** Expanded occurrences request recognition; repeated instances share completed component metadata. */
export function useModelingRecognition(meshUrl, enabled, { client, entry, requestedOccurrenceIds = [] } = {}) {
  const resources=client?.resources;
  if (!resources) throw new TypeError("Modeling recognition requires CAD resources");
  const [document,setDocument]=useState(null),[results,setResults]=useState({}),[error,setError]=useState('');
  const [retry,setRetry]=useState(0);
  const cache=useRef(new Map());
  // Results land here and reach the tree at most once a frame: each one re-presents the tree.
  const buffer=useRef(null),flushTimer=useRef(null);
  const cancelFlush=useCallback(()=>{
    const timer=flushTimer.current;flushTimer.current=null;
    if(timer){if(timer.frame !== undefined)cancelAnimationFrame(timer.frame);clearTimeout(timer.timeout);}
  },[]);
  const flush=useCallback(()=>{
    cancelFlush();
    const batch=buffer.current;buffer.current=null;
    if(batch)setResults(current=>({...current,...batch}));
  },[cancelFlush]);
  const deliver=useCallback((id,result)=>{
    (buffer.current ||= {})[id]=result;
    if(flushTimer.current)return;
    flushTimer.current={frame:typeof requestAnimationFrame === 'function' ? requestAnimationFrame(flush) : undefined,timeout:setTimeout(flush,FLUSH_FALLBACK_MS)};
  },[flush]);
  useEffect(()=>cancelFlush,[cancelFlush]);
  const recognition=useRef(null);
  const entryRef=useRef(entry);entryRef.current=entry;
  const entryRevision=completedPackageRevision(entry);
  const resourceScope=cadResourceCacheKey(resources, "");
  const documentKey=JSON.stringify([meshUrl,entryRevision,resourceScope]);
  const descriptor=document?.key===documentKey ? document.value : null;
  // Stable across presentation renders; an empty frontier loads only the descriptor.
  const requestedKey=JSON.stringify([...new Set(requestedOccurrenceIds)].sort());
  useEffect(()=>{
    cache.current.clear();buffer.current=null;cancelFlush();setResults({});setDocument(null);setError('');
  },[documentKey,cancelFlush]);
  useEffect(()=>{
    if(!enabled || !meshUrl || descriptor)return;
    const controller=new AbortController();setError('');
    loadPackageDescriptor(meshUrl,{resources,signal:controller.signal})
      .then(value=>{
        if(controller.signal.aborted)return;
        if(!value)throw new Error('Geometry is unavailable.');
        if(!value.components || !value.occurrences?.length)throw new Error('This file has no supported STEP geometry.');
        setDocument({key:documentKey,value});
      }).catch(e=>{if(!controller.signal.aborted)setError(e.message);});
    return ()=>controller.abort();
  },[enabled,meshUrl,documentKey,descriptor,retry,resources]);
  useEffect(()=>{
    if(!enabled || !descriptor)return;
    // This scope survives expansion changes. Its one worker recognizes one component at a time
    // and is kept for the next; a component no longer wanted takes the worker down with it, since
    // its work cannot be recalled. Changing the requested set updates the remaining queue.
    let disposed=false,active=null,pending=[],accepted=null,worker=null;
    const retire=()=>{worker?.terminate();worker=null;};
    const stop=job=>{
      clearTimeout(job.timer);
      if(job.worker){job.worker.onmessage=null;job.worker.onerror=null;job.worker=null;}
    };
    const cancelActive=()=>{
      if(!active)return;
      const job=active;active=null;
      const busy=job.posted;
      job.controller.abort();job.finish?.(null);stop(job);
      if(busy)retire();
    };
    const dispose=()=>{disposed=true;cancelActive();retire();};
    async function recognize() {
      if(disposed || active)return;
      const id=pending.pop();
      if(id===undefined)return;
      const job={id,controller:new AbortController(),worker:null,timer:null,finish:null,posted:false};
      active=job;
      const signal=job.controller.signal;
      try {
        const component=descriptor.components[id];
        let identity=accepted?.[id] || component;
        let surf=component?.surf ? resources.resolveDependency(meshUrl, component.surf, {kind:"package"}) : "";
        let key=modelingRecognitionKey(identity,surf,{resources});
        let result=completedModelingRecognition.get(key);
        if(!result && !surf && component?.surfaceInput && client) {
          identity=(await resolveSurfaceComponents(descriptor, [{ cid:id, surfaceInput:component.surfaceInput, surfaceObject:component.surfaceObject }], { client, signal })).get(id);
          if(signal.aborted || disposed)return;
          surf=identity?.surfUrl || "";
          key=modelingRecognitionKey(identity,surf,{resources});
          result=completedModelingRecognition.get(key);
        }
        if(!result) {
          result=await new Promise(resolve=>{
            let settled=false;
            // A worker that timed out or failed is not trusted with the next component.
            const finish=(value,broken=false)=>{if(settled)return;settled=true;job.finish=null;stop(job);if(broken)retire();resolve(value);};
            job.finish=finish;
            if(!surf){finish({error:'Exact geometry is unavailable for this part.'});return;}
            try {
              worker ||= new Worker(new URL('./modelingTree.worker.js',import.meta.url),{type:'module'});
              const current=worker;
              job.worker=current;
              job.timer=setTimeout(()=>finish({error:'Recognition timed out for this part.'},true),10000);
              current.onmessage=event=>finish(event.data);
              current.onerror=()=>finish({error:'Could not recognize this part.'},true);
              resources.workerTicket(surf,{signal,maxBytes:16*1024*1024}).then(resource=>{
                if(signal.aborted || job.worker!==current)return;
                try { current.postMessage({resource},resource.kind==='bytes' ? [resource.bytes] : []);job.posted=true; }
                catch(error) { finish({error:error.message}); }
              },error=>finish({error:error.message}));
            }catch{finish({error:'Could not start recognition.'},true);}
          });
          if(signal.aborted || disposed)return;
          completedModelingRecognition.set(key,result);
        }
        cache.current.set(id,result);
        deliver(id,result);
      }catch(error){
        if(!signal.aborted && !disposed){
          const result={error:error.message};
          cache.current.set(id,result);deliver(id,result);
        }
      }finally{
        stop(job);job.controller.abort();
        if(active===job){active=null;queueMicrotask(()=>void recognize());}
      }
    }
    const scope={update(requestedKey){
      if(disposed)return;
      // Repeated occurrences request one component, without sharing selection IDs.
      const requested=new Set(JSON.parse(requestedKey));
      const components=[...new Set(descriptor.occurrences.filter(o=>requested.has(o.id)).map(o=>o.component))];
      accepted=components.length ? completedPackages.peekComponentIdentities(client,entryRef.current,{descriptor}) : null;
      if(active && !components.includes(active.id))cancelActive();
      pending=components.filter(id=>id!==active?.id && !cache.current.has(id)).reverse();
      void recognize();
    }};
    recognition.current=scope;
    const resourceSignal=resources.signal;
    resourceSignal?.addEventListener('abort',dispose,{once:true});
    if(resourceSignal?.aborted)dispose();
    return ()=>{
      resourceSignal?.removeEventListener('abort',dispose);dispose();
      if(recognition.current===scope)recognition.current=null;
    };
  },[enabled,descriptor,meshUrl,entryRevision,client,resources,resourceScope,deliver]);
  // Run after scope setup even when its document changes with the same frontier.
  // Expansion and retry update demand without disposing still-requested work.
  useEffect(()=>{
    recognition.current?.update(requestedKey);
  },[enabled,descriptor,meshUrl,entryRevision,client,resources,resourceScope,requestedKey,retry]);
  const retryFailed=useCallback(()=>{
    for(const [id,result] of cache.current)if(result.error)cache.current.delete(id);
    // What is still buffered is in the cache too: the snapshot carries it, failures excepted.
    buffer.current=null;cancelFlush();
    setResults(Object.fromEntries(cache.current));setRetry(n=>n+1);
  },[cancelFlush]);
  const shown=descriptor ? results : EMPTY_RESULTS;
  // One object while nothing in it changes, so the Features panel can skip a render.
  return useMemo(()=>({descriptor,results:shown,error,retryFailed}),[descriptor,shown,error,retryFailed]);
}
