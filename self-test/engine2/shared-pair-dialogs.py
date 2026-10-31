#!/usr/bin/env python3
"""Qualify a compatible BrowserSkill pair using only an existing shared session.

Loopback fixtures only. Never starts/stops a session or changes the browser profile.
Port 8931 is required by the canonical fixture flows. See self-test/README.md.

Up to 0.3.x bsk accepted every native dialog itself and reported it in the click result.
From protocol 1.5 (0.4.0) the click is suspended with `dialog_pending` until the agent decides;
this harness then accepts (the prompt keeps its default), collects the ORIGINAL operation with
`operation await`, and never repeats the click. Page actions carry a `cooperate sync` context.
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
import bsk_coop
os.environ['BSK_AUTO_START']='0'
out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',8931),functools.partial(Quiet,directory=str(ROOT/'self-test/engine2')))
threading.Thread(target=server.serve_forever,daemon=True).start()
def raw(argv,pin=True):
 command=['bsk',*argv]+([] if '--json' in argv else ['--json'])+([] if argv[0]=='status' else ['--session',SID])
 if pin and tab:command+=['--tab-id',tab]
 p=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=45,env=os.environ)
 return p.returncode,p.stdout,p.stderr
def parse(code,stdout,stderr):
 try:return json.loads(stdout or stderr)
 except ValueError:return {'raw':(stdout or stderr)[:600],'exit_code':code}
def cli(argv,pin=True):
 if pin or bsk_coop.needs_context(argv):
  code,o,e=bsk_coop.dispatch(lambda a:raw(a,pin or a[0]=='cooperate'),argv)
 else:
  code,o,e=raw(argv,False)
 if code:raise RuntimeError((e or o)[:600])
 return json.loads(o)
def click_and_decide(kind):
 """Click once; return how bsk reported the dialog: auto-accepted (<=0.3) or decided by us (0.4)."""
 code,o,e=bsk_coop.dispatch(lambda a:raw(a),['click','--selector','#btn-'+kind])
 result=parse(code,o,e)
 if code==0:
  return {'path':'auto','reports':[x.get('handled') for x in result.get('dialogs',[])],'self_revoked':bool(result.get('self_revoked'))}
 data=result.get('data') or {}
 if data.get('reason')!='dialog_pending':raise RuntimeError(json.dumps(result)[:600])
 decisions=[];operation=data.get('operation_id');state=None
 while data.get('reason')=='dialog_pending' or data.get('dialog'):
  dialog=data.get('dialog') or {}
  decided=parse(*raw(['dialog','accept',str(dialog.get('id'))],False))
  decisions.append({'type':dialog.get('type'),'handled':(decided.get('dialog') or {}).get('handled')})
  awaited=parse(*raw(['operation','await',str(operation)],False))
  state=awaited.get('state')
  data=(awaited.get('data') or {}) if awaited.get('code')=='dialog_pending' else {}
 return {'path':'decided','reports':[d['handled'] for d in decisions],'types':[d['type'] for d in decisions],'await':state}
checks=[];tab=None
try:
 with SessionLease(SID):
  initial=cli(['status'],False)
  created=cli(['tab','create','--no-active','--url','about:blank'],False)
  tab=str(created.get('tab_id') or created.get('id'))
  for n in range(20):
   cli(['navigate','http://127.0.0.1:8931/dialog-page.html'])
   for kind,expected,dtype in [('alert','returned','alert'),('confirm','true','confirm'),('prompt','"default-text"','prompt'),('leave','left','beforeunload')]:
    report=click_and_decide(kind)
    deadline=time.monotonic()+8
    while True:
     try:actual=cli(['evaluate',f'document.getElementById("r-{kind}")?.textContent']).get('value')
     except RuntimeError:actual=None      # the page may still be navigating after beforeunload
     if actual==expected or time.monotonic()>deadline:break
     time.sleep(.15)
    reported_ok=report['reports']==['accepted'] and (report['path']=='auto' or report['types']==[dtype])
    check={'round':n+1,'kind':kind,**report,'actual':actual,'expected':expected,'pass':reported_ok and actual==expected}
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
  with SessionLease(SID):
   try:cli(['tab','close',tab],False)
   except RuntimeError as exc:print('tab close failed:',exc,file=sys.stderr)
 server.shutdown()
