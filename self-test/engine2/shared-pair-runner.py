#!/usr/bin/env python3
"""Qualify a compatible BrowserSkill pair using only an existing shared session.

Loopback fixtures only. Never starts/stops a session or changes the browser profile.
Port 8931 is required by the canonical fixture flows. See self-test/README.md.
"""
import argparse
import os,sys,json,subprocess,threading,http.server,functools,concurrent.futures
from pathlib import Path
from PIL import Image
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--session', required=True)
args=parser.parse_args()
ROOT=args.root.resolve()
SID=args.session
OUT=args.out.resolve();OUT.mkdir(parents=True,exist_ok=True)
os.environ['BSK_AUTO_START']='0'
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',8931),functools.partial(Quiet,directory=str(ROOT/'self-test/engine2')))
threading.Thread(target=server.serve_forever,daemon=True).start()
def run(name,flow,worker=None):
 dest=OUT/name
 args=[sys.executable,'-X','utf8',str(ROOT/'scripts/flow-runner.py'),'--engine','bsk','--bsk-session',SID,'--flow',str(ROOT/'self-test/engine2'/flow),'--out',str(dest),'--stdout','summary']
 if worker:args+=['--vars-json',json.dumps({'worker':worker,'base_url':'http://127.0.0.1:8931'})]
 p=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',env=os.environ,timeout=180)
 (OUT/(name+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
 result={'name':name,'exit':p.returncode,'summary':p.stdout.strip().splitlines()[-1] if p.stdout.strip() else p.stderr[:500]}
 assert p.returncode==0,result
 events=[json.loads(x) for x in (dest/'run-log.jsonl').read_text(encoding='utf-8').splitlines()]
 if flow=='flow-confirm.yaml':assert any('"answer":"dismiss"' in json.dumps(x,separators=(',',':')) for x in events)
 if worker:
  expected={'A':(192,57,43),'B':(39,174,96),'C':(41,128,185)}[worker]
  shots=list((dest/'shots').glob('*.png'));assert len(shots)==2
  for shot in shots:
   im=Image.open(shot).convert('RGB');assert im.getpixel((10,10))==expected,(name,shot,im.getpixel((10,10)))
  result['screenshotOwnerVerified']=worker
 print(name,'PASS',flush=True)
 return result
try:
 results=[run('read','flow-read.yaml'),run('confirm','flow-confirm.yaml')]
 for round in range(2):
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
   results+=list(pool.map(lambda w:run(f'contention-{round}-{w}','flow-own.yaml',w),['A','B','C']))
 (OUT/'runner-shared-proof.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
finally:server.shutdown()
