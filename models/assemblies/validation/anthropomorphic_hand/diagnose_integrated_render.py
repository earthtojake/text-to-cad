"""Diagnostic wrapper around the unchanged supported JSON snapshot job."""
import os,sys,asyncio,traceback
os.environ['DEBUG']='pw:browser'
from cadgen.snapshot_core import BatchSnapshotRenderer
start_original=BatchSnapshotRenderer.start
render_original=BatchSnapshotRenderer.render
async def start(self):
    await start_original(self)
    print('DIAGNOSTIC assetserver',self.asset_server.base_url if self.asset_server else 'CDP fallback',flush=True)
    self.page.on('crash',lambda *_:print('DIAGNOSTIC PAGE CRASH',flush=True))
    self.page.on('pageerror',lambda error:print('DIAGNOSTIC PAGE ERROR',error,flush=True))
    self.page.on('console',lambda message:print('BROWSER',message.type,message.text,flush=True) if message.type in ('error','warning') else None)
    await self.page.evaluate("""() => {
      const original=window.fetch;
      window.fetch=function(url,options){
        const bytes=options?.body?.byteLength || options?.body?.length || 0;
        if(bytes>8*1024*1024) console.warn('DIAGNOSTIC FETCH BODY',String(url),bytes);
        if(bytes>32*1024*1024 && String(url).includes('__tess_cache')) {
          console.warn('DIAGNOSTIC SKIP OVERSIZE OPTIONAL CACHE WRITE',String(url),bytes);
          return Promise.reject(new Error('Diagnostic cache-write transport guard'));
        }
        return original.call(this,url,options);
      };
    }""")
async def render(self,job):
    try:return await render_original(self,job)
    except BaseException:
        transport=self.playwright._impl_obj._connection._transport
        process=getattr(transport,'_proc',None)
        print('DIAGNOSTIC driver pid',getattr(process,'pid',None),'returncode',getattr(process,'returncode',None),flush=True)
        traceback.print_exc();raise
BatchSnapshotRenderer.start=start
BatchSnapshotRenderer.render=render
from cadgen.cli.step_snapshot import main
sys.exit(main(['--job','models/assemblies/src/anthropomorphic_hand/integrated_render_job.json']))
