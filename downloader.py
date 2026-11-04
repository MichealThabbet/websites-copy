import argparse,hashlib,json,time,mimetypes,sys,os
from pathlib import Path
from urllib.parse import urlparse,urljoin,urldefrag
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup
EXT={'.pdf','.jpg','.jpeg','.png','.tif','.tiff','.webp','.doc','.docx','.xls','.xlsx','.epub','.djvu','.txt','.xml','.json','.zip','.mp3','.mp4','.m4a','.wav','.ogg','.webm'}
class Downloader:
 def __init__(self,a):
  self.a=a;self.out=Path('downloads');self.out.mkdir(exist_ok=True);self.log=[];self.seen=set();self.rules={};self.count=0;self.attempts=0;self.skipped=0
  self.s=requests.Session();self.s.headers['User-Agent']='HeritageDownloader/1.0'
  # Do not retry blocking or rate-limit responses.
  self.last_request={};self.final_url=None
 def get(self,u):
  for _ in range(8):
   p=urlparse(u)
   if p.username or p.password:raise ValueError('Credentials in URLs are not allowed')
   if p.scheme not in ('https','http'):raise ValueError('HTTP(S) required')
   root=f'{p.scheme}://{p.netloc}'
   if root in getattr(self.a,'authorized_origin',[]):
    self.rules[root]=RobotFileParser();self.rules[root].parse([])
   if root not in self.rules:
    rp=RobotFileParser(root+'/robots.txt')
    # Robots retrieval must use the same proxy, TLS trust and timeout as downloads.
    self.rules[root]=rp
    with self.s.get(root+'/robots.txt',timeout=(15,30),stream=True,allow_redirects=False) as rr:
     if rr.status_code==404:rp.parse([])
     elif rr.status_code==200:
      body=bytearray()
      for chunk in rr.iter_content(65536):
       body.extend(chunk)
       if len(body)>512*1024:raise ValueError('robots size limit')
      rp.parse(body.decode('utf-8',errors='replace').splitlines())
     else:raise ValueError('robots unavailable or denied: '+str(rr.status_code))
   if not self.rules[root].can_fetch('HeritageDownloader',u):raise ValueError('robots denied')
   delay=max(2,self.rules[root].crawl_delay('HeritageDownloader') or 0)
   time.sleep(max(0,delay-(time.monotonic()-self.last_request.get(root,0))))
   self.last_request[root]=time.monotonic();r=self.s.get(u,timeout=(15,90),stream=True,allow_redirects=False)
   if r.is_redirect:
    u=urljoin(u,r.headers['Location']);r.close();continue
   try:r.raise_for_status()
   except Exception:r.close();raise
   self.final_url=u;return r
  raise ValueError('Redirect limit')
 def read(self,u):
  with self.get(u) as r:
   data=bytearray()
   for c in r.iter_content(65536):
    data.extend(c)
    if len(data)>8*1024*1024:raise ValueError('Metadata size limit')
   return bytes(data),r.headers.get('Content-Type','')
 def save(self,u):
  if self.attempts>=self.a.max_files or 'file:'+u in self.seen:return
  self.seen.add('file:'+u)
  if self.skipped<getattr(self.a,'skip_files',0):
   self.skipped+=1;return
  self.attempts+=1
  tmp=None
  try:
   with self.get(u) as r:
    ext=Path(urlparse(u).path).suffix.lower()
    if ext not in EXT:ext=mimetypes.guess_extension(r.headers.get('Content-Type','').split(';')[0]) or '.bin'
    name=hashlib.sha256(u.encode()).hexdigest()[:24]+ext;dest=self.out/name;tmp=dest.with_suffix(dest.suffix+'.part');h=hashlib.sha256();n=0
    with tmp.open('wb') as f:
     for ch in r.iter_content(65536):
      n+=len(ch)
      if n>self.a.max_mb*1024*1024:raise ValueError('File size limit')
      f.write(ch);h.update(ch)
    tmp.replace(dest);self.count+=1;self.log.append(dict(url=u,file=name,bytes=n,sha256=h.hexdigest(),rights='UNREVIEWED'))
  except Exception as e:
   if tmp:tmp.unlink(missing_ok=True)
   self.log.append(dict(url=u,error=str(e)))
 def crawl(self,start):
  queue=[(start,0)];pages=0
  while queue and pages<self.a.max_pages and self.attempts<self.a.max_files:
   u,d=queue.pop(0);u=urldefrag(u)[0]
   if u in self.seen:continue
   self.seen.add(u);pages+=1
   try:
    data,typ=self.read(u);base=self.final_url or u
    if 'html' not in typ:self.save(base);continue
    soup=BeautifulSoup(data,'html.parser')
    containers=soup.select(self.a.selector) if getattr(self.a,'selector',None) else [soup]
    for tag in [tag for container in containers for tag in container.select('a[href],img[src],audio[src],video[src],source[src]')]:
     v=urldefrag(urljoin(base,tag.get('href') or tag.get('src')))[0]
     if urlparse(v).scheme not in ('http','https'):continue
     suffix=Path(urlparse(v).path).suffix.lower()
     if suffix in EXT or tag.name in ('img','audio','video','source'):
      if not getattr(self.a,'extensions',None) or suffix in self.a.extensions.split(','):self.save(v)
     elif d<self.a.depth and urlparse(v).netloc==urlparse(start).netloc:queue.append((v,d+1))
   except Exception as e:self.log.append(dict(url=u,error=str(e)))
 def iiif(self,u):
  data,_=self.read(u);base=self.final_url or u;m=json.loads(data)
  def images(x):
   if isinstance(x,list):
    for a in x:yield from images(a)
   elif isinstance(x,dict):
    if x.get('type')=='Image' or x.get('@type')=='dctypes:Image':
     v=x.get('id') or x.get('@id')
     if v:yield v
    for k,v in x.items():
     if k not in ('service','thumbnail'):yield from images(v)
  for v in dict.fromkeys(images(m)):self.save(urljoin(base,v))
 def finish(self):
  errors=sum('error' in entry for entry in self.log)
  summary=f'Downloaded: {self.count}; failed: {errors}; skipped from earlier batches: {self.skipped}; bytes: {sum(e.get("bytes",0) for e in self.log)}'
  print(summary,flush=True)
  if os.environ.get('GITHUB_STEP_SUMMARY'):
   with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as report:report.write('## Download results\n\n'+summary+'\n')
  (self.out/'manifest.json').write_text(json.dumps(self.log,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('url');p.add_argument('--mode',choices=['file','page','iiif'],default='page');p.add_argument('--max-files',type=int,default=40);p.add_argument('--max-pages',type=int,default=20);p.add_argument('--max-mb',type=int,default=50);p.add_argument('--depth',type=int,default=1);p.add_argument('--skip-files',type=int,default=0,help='Skip this many distinct discovered resources from earlier batches');p.add_argument('--authorized-origin',action='append',default=[],help='Exact origin with explicit owner permission; skips robots only on this origin');p.add_argument('--selector',help='CSS selector containing relevant page content');p.add_argument('--extensions',help='Comma-separated file suffixes, e.g. .pdf');a=p.parse_args()
 if min(a.max_files,a.max_pages,a.max_mb)<=0 or min(a.depth,a.skip_files)<0:p.error('Invalid limits')
 t=Downloader(a)
 try:
  if a.mode=='file':t.save(a.url)
  elif a.mode=='iiif':t.iiif(a.url)
  else:t.crawl(a.url)
 except Exception as e:t.log.append(dict(url=a.url,error=str(e)))
 finally:t.finish()
 if any('error' in item for item in t.log):sys.exit(1)
 if not t.count:
  print('No downloadable resources found',file=sys.stderr);sys.exit(1)
