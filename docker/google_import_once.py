"""Explicit single-response Google import. No paging, polling, model calls or deployment.
Private selection contains form/question/folder IDs, consent text and synthetic name.
OAuth stays in LOCALAPPDATA/TalentTraceAI/GoogleOAuth. Never echo private errors.
"""
import argparse,base64,hashlib,http.cookiejar,json,os,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler,HTTPCookieProcessor
from urllib.parse import urlencode
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.google_single_application import responses_url,select_response,validate_metadata,validate_bytes,identifier,SingleApplicationError
PROJECT='tt-groq-55de9df40a4a'
BACKEND=PROJECT+'-backend-1'
REFERENCE='TT-JOB-49C51587C3524024'
SCOPES={'https://www.googleapis.com/auth/forms.body.readonly','https://www.googleapis.com/auth/forms.responses.readonly','https://www.googleapis.com/auth/drive.readonly'}
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*a,**kw):return None

def read(request,limit):
    with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=15) as r:
        value=r.read(limit+1)
    if len(value)>limit:raise SingleApplicationError('response_too_large')
    return value

def token():
    folder=Path(os.environ['LOCALAPPDATA'])/'TalentTraceAI/GoogleOAuth'
    for p in [folder/'token.json',folder/'credentials.json']:
        if p.is_symlink() or p.is_junction() or not p.is_file() or p.stat().st_size>32768:raise SingleApplicationError('credential_storage_invalid')
    v=json.loads((folder/'token.json').read_text(encoding='utf-8-sig'))
    client=json.loads((folder/'credentials.json').read_text(encoding='utf-8-sig'))['installed']
    if set(v['scopes'])!=SCOPES or v['client_id']!=client['client_id'] or v['client_secret']!=client['client_secret'] or v['token_uri']!='https://oauth2.googleapis.com/token':
        raise SingleApplicationError('oauth_approval_mismatch')
    expiry=datetime.fromisoformat(v['expiry'].replace('Z','+00:00'))
    if expiry.tzinfo is None:expiry=expiry.replace(tzinfo=timezone.utc)
    value=v['token']
    if expiry.timestamp()<=time.time()+60:
        if not v.get('refresh_token'):raise SingleApplicationError('oauth_refresh_unavailable')
        payload=urlencode({k:v[k] for k in ['client_id','client_secret','refresh_token']}|{'grant_type':'refresh_token'}).encode()
        r=json.loads(read(Request(v['token_uri'],data=payload,headers={'Content-Type':'application/x-www-form-urlencoded'}),16384))
        if r.get('scope') and set(r['scope'].split())!=SCOPES:raise SingleApplicationError('oauth_scope_mismatch')
        value=r['access_token']
    if not isinstance(value,str) or not value or any(ord(c)<=32 for c in value):raise SingleApplicationError('invalid_token')
    return value

def worker(payload):
    source=(ROOT/'backend/app/google_application_import.py').read_text(encoding='utf8')
    r=subprocess.run(['docker','exec','-i',BACKEND,'python','-c',source],input=json.dumps(payload).encode(),capture_output=True,timeout=45)
    try:result=json.loads(r.stdout)
    except Exception:raise SingleApplicationError('worker_unconfirmed') from None
    if r.returncode:raise SingleApplicationError('worker_'+str(result.get('category','unconfirmed')))
    return result

def execute(selection,directory):
    directory.mkdir(parents=True,exist_ok=True)
    info=json.loads(subprocess.check_output(['docker','inspect',BACKEND]))[0]
    if not info['State']['Running'] or info['Config']['Labels'].get('com.docker.compose.project')!=PROJECT or info['Config']['Labels'].get('com.docker.compose.service')!='backend':
        raise SingleApplicationError('wrong_backend_identity')
    if not any(m.get('Name')==PROJECT+'_application_data' and m['Destination']=='/app/data' for m in info['Mounts']):raise SingleApplicationError('wrong_storage_volume')
    config=json.loads(selection.read_text(encoding='utf-8-sig'))
    if config['job_reference']!=REFERENCE:raise SingleApplicationError('wrong_target')
    if len({config[k] for k in ['job_question_id','consent_question_id','cv_question_id']})!=3:raise SingleApplicationError('ambiguous_mapping')
    for k in ['form_id','upload_folder_id','job_question_id','consent_question_id','cv_question_id']:identifier(config[k])
    base='http://127.0.0.1:5280';origin='http://groq-20261026.localhost:5280'
    op=build_opener(ProxyHandler({}),NoRedirect(),HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.addheaders=[('Host','groq-20261026.localhost:5280'),('Origin',origin),('X-TalentTrace-Request','1')]
    def api(path,body=None):
        req=Request(base+'/api/v1/'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        with op.open(req,timeout=15) as r:return json.load(r) if r.status!=204 else None
    credentials=json.loads((ROOT/'data/groq-runtime-20261026/LOGIN.json').read_text())
    api('auth/login',credentials)
    try:
        actor=api('auth/me');jobs=api('jobs');targets=[j for j in jobs if j['job_reference']==REFERENCE]
        if len(targets)!=1 or targets[0]['revision']!=2:raise SingleApplicationError('target_revision_or_approval_mismatch')
        job=targets[0]
        def counts(j):
            x=api('jobs/'+j['id']+'/applications')
            return {'received':x['received_count'],'new':x['new_count'],'available':sum(a['available'] for a in x['applications']),'trusted':sum(a['origin']=='trusted_import' for a in x['applications'])}
        before={j['id']:counts(j) for j in jobs}
        if before[job['id']]!={'received':0,'new':0,'available':0,'trusted':0}:raise SingleApplicationError('unexpected_preimport_counts')
        source='google_form_'+hashlib.sha256(config['form_id'].encode()).hexdigest()[:24]
        binding={'source_id':source,'source_job_reference':REFERENCE,'recruiter_id':actor['id'],'target_job_id':job['id'],'target_job_reference':REFERENCE}
        worker({'action':'preflight','binding':binding})
        access=token()
        with open(directory/'intent.json','x',encoding='utf8') as f:
            json.dump({'filtered_requests_allowed':1,'cutoff':'2026-10-16T00:00:00Z','job_reference':REFERENCE,'revision':2},f);f.flush();os.fsync(f.fileno())
        def google(url,limit):return read(Request(url,headers={'Authorization':'Bearer '+access,'Accept-Encoding':'identity'}),limit)
        page=json.loads(google(responses_url(config['form_id']),256*1024))
        response,key,file_id,mime=select_response(page,config)
        url='https://www.googleapis.com/drive/v3/files/'+file_id
        meta=json.loads(google(url+'?'+urlencode({'fields':'id,mimeType,size,trashed,parents,md5Checksum,capabilities(canDownload)'}),65536))
        size=validate_metadata(meta,file_id,mime,config['upload_folder_id'])
        data=google(url+'?alt=media',size);digest=validate_bytes(data,meta,mime)
        # Revalidate current owned target after Google I/O; worker locks revision through import commit.
        result=worker({'action':'import','binding':binding,'submission_id':key,'mime':mime,'sha256':digest,
            'respondent_email':response.get('respondentEmail'),'cv_base64':base64.b64encode(data).decode()})
        after={j['id']:counts(j) for j in jobs}
        expected={'received':1,'new':1,'available':1,'trusted':1}
        verified=after[job['id']]==expected and all(after[k]==v for k,v in before.items() if k!=job['id'])
        report={'import_result':result,'target_counts':after[job['id']],'other_job_counts_unchanged':all(after[k]==v for k,v in before.items() if k!=job['id']),
            'filtered_response_requests':1,'response_identity_verified':True,'file_integrity_verified':True,'api_verification':verified,'screening':False,'browser_home_observed':False}
        (directory/'result.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        print(json.dumps(report))
    finally:
        try:api('auth/logout',{})
        except Exception:pass

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--selection',required=True,type=Path);p.add_argument('--confirm-one-synthetic-import',action='store_true');a=p.parse_args()
    d=ROOT/'data/google-one-import-20261028'
    try:
        if not a.confirm_one_synthetic_import:raise SingleApplicationError('owner_confirmation_required')
        execute(a.selection,d)
    except Exception as e:
        category=str(e) if isinstance(e,SingleApplicationError) else type(e).__name__
        d.mkdir(parents=True,exist_ok=True);(d/'stop.json').write_text(json.dumps({'state':'blocked_or_unconfirmed_no_automatic_retry','category':category}))
        print(json.dumps({'state':'BLOCKED_OR_UNCONFIRMED','category':category}));sys.exit(1)
