"""素材月报缓存与断点。配置: CREATIVE_CACHE_DIR, CREATIVE_HISTORY_SCAN。
Usage: import creative_cache_runtime as runtime
Example: CREATIVE_CACHE_DIR=/var/data/creative-cache gunicorn app:app --threads 4
不保存凭证；持久性取决于配置目录是否挂载持久磁盘。
"""
import os, json, time, hashlib, tempfile, threading
from pathlib import Path
from datetime import datetime, timezone
ROOT = Path(os.getenv('CREATIVE_CACHE_DIR', '/tmp/pesoloan-creative-cache'))
LOCK = threading.Lock()
TASKS = {}
VERSION = 'month-v2'

def stamp(): return datetime.now(timezone.utc).isoformat()
def path(key):
 ROOT.mkdir(parents=True, exist_ok=True)
 return ROOT / (hashlib.sha256((VERSION + key).encode()).hexdigest() + '.json')
def read(key, ttl=86400):
 try:
  data=json.loads(path(key).read_text(encoding='utf-8'))
  if time.time()-data['saved_at']<=ttl: return data['value']
 except (OSError, ValueError, KeyError): pass
 return None
def save(key, value):
 p=path(key)
 fd, tmp=tempfile.mkstemp(dir=ROOT, suffix='.tmp')
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as f:
   json.dump({'saved_at':time.time(),'value':value},f,ensure_ascii=False)
  os.replace(tmp,p)
 finally:
  if os.path.exists(tmp): os.unlink(tmp)
def checkpoint(month, label, fn, args):
 # 不保存函数参数或认证信息，只保存媒体业务结果。
 key='source:'+month+':'+label+':'+hashlib.sha256(repr(args).encode()).hexdigest()
 hit=read(key)
 if hit is not None: return hit
 value=fn(*args)
 failed=(isinstance(value,tuple) and len(value)==2 and bool(value[1])) or (isinstance(value,list) and any(isinstance(x,dict) and x.get('source_status')=='error' for x in value))
 if not failed: save(key,value)
 return value

def status(month):
 with LOCK:
  s=dict(TASKS.get(month) or read('status:'+month,7*86400) or {'status':'not_started'})
  alive=bool(TASKS.get(month,{}).get('_alive'))
 s.pop('_alive',None)
 cached=read('result:'+month)
 if cached:
  s['status']='partial' if cached.get('errors') else 'completed'
 elif s.get('status')=='collecting' and not alive:
  s['status']='interrupted'; s['error']='实例重启中断，已保存成功账户的检查点；再次打开可继续。'
 s['cached']=cached is not None
 s['storage']='configured_directory' if os.getenv('CREATIVE_CACHE_DIR') else 'ephemeral_disk'
 return s

def _work(month, fn):
 try:
  result=fn(month)
  save('result:'+month,result)
  s={'status':'partial' if result.get('errors') else 'completed','finished_at':stamp(),'error':None,'source_errors':len(result.get('errors',[]))}
 except Exception as e:
  # 不输出媒体响应/请求URL，避免认证信息进入状态。
  s={'status':'failed','finished_at':stamp(),'error':'采集失败：'+type(e).__name__}
 with LOCK:
  old=TASKS.get(month,{})
  s['started_at']=old.get('started_at'); s['progress']=old.get('progress')
  TASKS[month]=s
 save('status:'+month,s)

def launch(month, fn):
 with LOCK:
  if TASKS.get(month,{}).get('_alive'): return False
  s={'status':'collecting','started_at':stamp(),'finished_at':None,'error':None,'progress':{'done':0,'total':0},'_alive':True}
  TASKS[month]=s
  save('status:'+month,{k:v for k,v in s.items() if k!='_alive'})
  threading.Thread(target=_work,args=(month,fn),daemon=True,name='creative-'+month).start()
 return True

def progress(month, done, total, source):
 with LOCK:
  s=TASKS.setdefault(month,{})
  s['progress']={'done':done,'total':total,'last_source':source}
  clean={k:v for k,v in s.items() if k!='_alive'}
 save('status:'+month,clean)
