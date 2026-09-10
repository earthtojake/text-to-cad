import { useEffect, useRef, useState } from 'react';
import { resolvePackageAssetUrl } from '@hardcore/core/client';
const EMPTY_RESULTS = {};

/** One worker at a time; completed components survive tab switches and repeated instances. */
export function useModelingRecognition(meshUrl, enabled) {
  const [document,setDocument]=useState(null),[results,setResults]=useState({}),[error,setError]=useState('');
  const [retry,setRetry]=useState(0);
  const cache=useRef(new Map());
  const descriptor=document?.url===meshUrl ? document.value : null;
  useEffect(()=>{
    cache.current.clear();setResults({});setDocument(null);setError('');
  },[meshUrl]);
  useEffect(()=>{
    if(!enabled || !meshUrl || descriptor)return;
    const controller=new AbortController();setError('');
    fetch(resolvePackageAssetUrl(meshUrl,'assembly.json'),{signal:controller.signal})
      .then(r=>{if(!r.ok)throw new Error('Geometry is unavailable.');return r.json();})
      .then(value=>{
        if(controller.signal.aborted)return;
        if(!value.components || !value.occurrences?.length)throw new Error('This file has no supported STEP geometry.');
        setDocument({url:meshUrl,value});
      }).catch(e=>{if(!controller.signal.aborted)setError(e.message);});
    return ()=>controller.abort();
  },[enabled,meshUrl,descriptor,retry]);
  useEffect(()=>{
    if(!enabled || !descriptor)return;
    let cancelled=false,worker=null,timer;
    const stop=()=>{worker?.terminate();worker=null;clearTimeout(timer);};
    async function recognize() {
      // Component identity is shared; face references are scoped to occurrences in the UI.
      const components=[...new Set(descriptor.occurrences.map(o=>o.component))];
      for(const id of components) {
        if(cancelled)return;
        if(cache.current.has(id))continue;
        const surf=descriptor.components[id]?.surf;
        const result=await new Promise(resolve=>{
          let settled=false;
          const finish=value=>{if(settled || cancelled)return;settled=true;stop();resolve(value);};
          if(!surf){finish({error:'Exact geometry is unavailable for this part.'});return;}
          try {
            worker=new Worker(new URL('./modelingTree.worker.js',import.meta.url),{type:'module'});
            timer=setTimeout(()=>finish({error:'Recognition timed out for this part.'}),10000);
            worker.onmessage=event=>finish(event.data);
            worker.onerror=()=>finish({error:'Could not recognize this part.'});
            worker.postMessage({url:resolvePackageAssetUrl(meshUrl,surf)});
          }catch{finish({error:'Could not start recognition.'});}
        });
        if(cancelled)return;
        cache.current.set(id,result);
        setResults(current=>({...current,[id]:result}));
      }
    }
    void recognize();
    return ()=>{cancelled=true;stop();};
  },[enabled,descriptor,meshUrl,retry]);
  const retryFailed=()=>{
    for(const [id,result] of cache.current)if(result.error)cache.current.delete(id);
    setResults(Object.fromEntries(cache.current));setRetry(n=>n+1);
  };
  return {descriptor,results:descriptor ? results : EMPTY_RESULTS,error,retryFailed};
}
