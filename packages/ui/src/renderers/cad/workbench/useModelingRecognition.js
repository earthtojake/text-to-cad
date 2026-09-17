import { cadResourceCacheKey } from "@hardcore/core/client";
import { resolveSurfaceComponents } from "./surfaceResolution.js";
import { useEffect, useRef, useState } from 'react';
import { loadPackageDescriptor } from '../components/workbench/hooks/packageDescriptorCache.js';
import { completedPackages, completedPackageRevision } from '../render/completedPackageCache.js';
import { completedModelingRecognition, modelingRecognitionKey } from './modelingRecognitionCache.js';
const EMPTY_RESULTS = {};

/** One worker at a time; completed components survive tab switches and repeated instances. */
export function useModelingRecognition(meshUrl, enabled, { client, entry } = {}) {
  const resources=client?.resources;
  if (!resources) throw new TypeError("Modeling recognition requires CAD resources");
  const [document,setDocument]=useState(null),[results,setResults]=useState({}),[error,setError]=useState('');
  const [retry,setRetry]=useState(0);
  const cache=useRef(new Map());
  const entryRef=useRef(entry);entryRef.current=entry;
  const entryRevision=completedPackageRevision(entry);
  const resourceScope=cadResourceCacheKey(resources, "");
  const documentKey=JSON.stringify([meshUrl,entryRevision,resourceScope]);
  const descriptor=document?.key===documentKey ? document.value : null;
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
    let cancelled=false,worker=null,timer;
    const controller = new AbortController();
    const stop=()=>{worker?.terminate();worker=null;clearTimeout(timer);};
    const resourceSignal=resources.signal;
    const cancel=()=>{cancelled=true;controller.abort();stop();};
    resourceSignal?.addEventListener('abort',cancel,{once:true});
    if(resourceSignal?.aborted)cancel();
    async function recognize() {
      // Component identity is shared; face references are scoped to occurrences in the UI.
      const accepted=completedPackages.peekComponentIdentities(client,entryRef.current,{descriptor});
      const components=[...new Set(descriptor.occurrences.map(o=>o.component))];
      for(const id of components) {
        if(cancelled)return;
        if(cache.current.has(id))continue;
        const component=descriptor.components[id];
        let identity=accepted?.[id] || component;
        let surf=component?.surf ? resources.resolveDependency(meshUrl, component.surf, {kind:"package"}) : "";
        const known=completedModelingRecognition.get(modelingRecognitionKey(identity,surf,{resources}));
        if(known){cache.current.set(id,known);setResults(current=>({...current,[id]:known}));continue;}
        if (!surf && component?.surfaceInput && client) {
          try {
            identity=(await resolveSurfaceComponents(descriptor, [{ cid:id, surfaceInput:component.surfaceInput, surfaceObject:component.surfaceObject }], { client, signal:controller.signal })).get(id);
            surf=identity?.surfUrl || "";
          }
          catch (error) { if (cancelled) return; cache.current.set(id,{error:error.message}); setResults(current=>({...current,[id]:{error:error.message}})); continue; }
        }
        if(cancelled)return;
        const key=modelingRecognitionKey(identity,surf,{resources});
        const completed=completedModelingRecognition.get(key);
        if(completed){cache.current.set(id,completed);setResults(current=>({...current,[id]:completed}));continue;}
        const result=await new Promise(resolve=>{
          let settled=false;
          const finish=value=>{if(settled || cancelled)return;settled=true;stop();resolve(value);};
          if(!surf){finish({error:'Exact geometry is unavailable for this part.'});return;}
          try {
            worker=new Worker(new URL('./modelingTree.worker.js',import.meta.url),{type:'module'});
            timer=setTimeout(()=>finish({error:'Recognition timed out for this part.'}),10000);
            worker.onmessage=event=>finish(event.data);
            worker.onerror=()=>finish({error:'Could not recognize this part.'});
            const target=worker;
            const send=resource=>{if(!cancelled && worker===target)target.postMessage({resource},resource.kind==='bytes' ? [resource.bytes] : []);};
            resources.workerTicket(surf,{signal:controller.signal,maxBytes:16*1024*1024}).then(send,error=>finish({error:error.message}));
          }catch{finish({error:'Could not start recognition.'});}
        });
        if(cancelled)return;
        completedModelingRecognition.set(key,result);
        cache.current.set(id,result);
        setResults(current=>({...current,[id]:result}));
      }
    }
    void recognize();
    return ()=>{resourceSignal?.removeEventListener("abort",cancel);cancel();};
  },[enabled,descriptor,meshUrl,entryRevision,retry,client,resources]);
  const retryFailed=()=>{
    for(const [id,result] of cache.current)if(result.error)cache.current.delete(id);
    setResults(Object.fromEntries(cache.current));setRetry(n=>n+1);
  };
  return {descriptor,results:descriptor ? results : EMPTY_RESULTS,error,retryFailed};
}
