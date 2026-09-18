import { cadResourceCacheKey } from "@hardcore/core/client";
import { resolveSurfaceComponents } from "./surfaceResolution.js";
import { useEffect, useRef, useState } from 'react';
import { loadPackageDescriptor } from '../components/workbench/hooks/packageDescriptorCache.js';
import { completedPackages, completedPackageRevision } from '../render/completedPackageCache.js';
import { completedModelingRecognition, modelingRecognitionKey } from './modelingRecognitionCache.js';
const EMPTY_RESULTS = {};

/** Expanded occurrences request recognition; repeated instances share completed component metadata. */
export function useModelingRecognition(meshUrl, enabled, { client, entry, requestedOccurrenceIds = [] } = {}) {
  const resources=client?.resources;
  if (!resources) throw new TypeError("Modeling recognition requires CAD resources");
  const [document,setDocument]=useState(null),[results,setResults]=useState({}),[error,setError]=useState('');
  const [retry,setRetry]=useState(0);
  const cache=useRef(new Map());
  const recognition=useRef(null);
  const entryRef=useRef(entry);entryRef.current=entry;
  const entryRevision=completedPackageRevision(entry);
  const resourceScope=cadResourceCacheKey(resources, "");
  const documentKey=JSON.stringify([meshUrl,entryRevision,resourceScope]);
  const descriptor=document?.key===documentKey ? document.value : null;
  // Stable across presentation renders; an empty frontier loads only the descriptor.
  const requestedKey=JSON.stringify([...new Set(requestedOccurrenceIds)].sort());
  useEffect(()=>{
    cache.current.clear();setResults({});setDocument(null);setError('');
  },[documentKey]);
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
    // This scope survives expansion changes. Only its current component owns
    // a worker; changing the requested set updates the remaining queue.
    let disposed=false,active=null,pending=[],accepted=null;
    const stop=job=>{job.worker?.terminate();job.worker=null;clearTimeout(job.timer);};
    const cancelActive=()=>{
      if(!active)return;
      const job=active;active=null;
      job.controller.abort();job.finish?.(null);stop(job);
    };
    const dispose=()=>{disposed=true;cancelActive();};
    async function recognize() {
      if(disposed || active)return;
      const id=pending.pop();
      if(id===undefined)return;
      const job={id,controller:new AbortController(),worker:null,timer:null,finish:null};
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
            const finish=value=>{if(settled)return;settled=true;job.finish=null;stop(job);resolve(value);};
            job.finish=finish;
            if(!surf){finish({error:'Exact geometry is unavailable for this part.'});return;}
            try {
              const worker=new Worker(new URL('./modelingTree.worker.js',import.meta.url),{type:'module'});
              job.worker=worker;
              job.timer=setTimeout(()=>finish({error:'Recognition timed out for this part.'}),10000);
              worker.onmessage=event=>finish(event.data);
              worker.onerror=()=>finish({error:'Could not recognize this part.'});
              resources.workerTicket(surf,{signal,maxBytes:16*1024*1024}).then(resource=>{
                if(signal.aborted || job.worker!==worker)return;
                try { worker.postMessage({resource},resource.kind==='bytes' ? [resource.bytes] : []); }
                catch(error) { finish({error:error.message}); }
              },error=>finish({error:error.message}));
            }catch{finish({error:'Could not start recognition.'});}
          });
          if(signal.aborted || disposed)return;
          completedModelingRecognition.set(key,result);
        }
        cache.current.set(id,result);
        setResults(current=>({...current,[id]:result}));
      }catch(error){
        if(!signal.aborted && !disposed){
          const result={error:error.message};
          cache.current.set(id,result);setResults(current=>({...current,[id]:result}));
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
  },[enabled,descriptor,meshUrl,entryRevision,client,resources,resourceScope]);
  // Run after scope setup even when its document changes with the same frontier.
  // Expansion and retry update demand without disposing still-requested work.
  useEffect(()=>{
    recognition.current?.update(requestedKey);
  },[enabled,descriptor,meshUrl,entryRevision,client,resources,resourceScope,requestedKey,retry]);
  const retryFailed=()=>{
    for(const [id,result] of cache.current)if(result.error)cache.current.delete(id);
    setResults(Object.fromEntries(cache.current));setRetry(n=>n+1);
  };
  return {descriptor,results:descriptor ? results : EMPTY_RESULTS,error,retryFailed};
}
