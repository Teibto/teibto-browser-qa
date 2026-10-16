#!/usr/bin/env python3
"""Qualify a compatible BrowserSkill pair using only an existing shared session.

Loopback fixtures only. Never starts/stops a session or changes the browser profile.
Port 8931 is required by the canonical fixture flows. See self-test/README.md.
"""
import argparse
import os,sys,json,time,subprocess,threading,http.server,functools
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--session', required=True)
args=parser.parse_args()
ROOT=args.root.resolve()
SID=args.session
sys.path.insert(0,str(ROOT/'scripts'))
from bsk_lease import SessionLease
os.environ['BSK_AUTO_START']='0'
out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',8931),functools.partial(Quiet,directory=str(ROOT/'self-test/engine2')))
threading.Thread(target=server.serve_forever,daemon=True).start()
def cli(args,pin=True):
 command=['bsk',*args,'--json']
 if pin:command+=['--session',SID,'--tab-id',tab]
 p=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=45,env=os.environ)
 if p.returncode:raise RuntimeError(p.stderr[:600]+p.stdout[:600])
 return json.loads(p.stdout)
checks=[];tab=None
try:
 with SessionLease(SID):
  initial=cli(['status'],False)
  created=cli(['tab','create','--session',SID,'--no-active','--url','about:blank'],False)
  tab=str(created.get('tab_id') or created.get('id'))
  for n in range(20):
   cli(['navigate','http://127.0.0.1:8931/dialog-page.html'])
   for kind,expected in [('alert','returned'),('confirm','true'),('prompt','"default-text"'),('leave','left')]:
    clicked=cli(['click','#btn-'+kind])
    reports=[x.get('handled') for x in clicked.get('dialogs',[])]
    deadline=time.monotonic()+8
    while True:
     actual=cli(['evaluate',f'document.getElementById("r-{kind}")?.textContent']).get('value')
     if actual==expected or time.monotonic()>deadline:break
     time.sleep(.15)
    check={'round':n+1,'kind':kind,'reports':reports,'actual':actual,'expected':expected,'pass':reports==['accepted'] and actual==expected}
    checks.append(check)
    if not check['pass']:raise AssertionError(check)
   live=cli(['evaluate','1+1']).get('value')==2
   checks.append({'round':n+1,'kind':'liveness','pass':live})
   assert live
   print('round',n+1,'passed',flush=True)
  final=cli(['status'],False)
  assert final['pid']==initial['pid']
  (out/'native-dialogs.json').write_text(json.dumps({'session':SID,'status':initial,'checks':checks,'daemonPidUnchanged':True},indent=2),encoding='utf-8')
finally:
 if tab:
  with SessionLease(SID):cli(['tab','close',tab,'--session',SID],False)
 server.shutdown()
