"""Offline single-response boundary regressions; never contact Google."""
import copy,hashlib,unittest
from urllib.parse import urlparse,parse_qs
from app.services.google_single_application import *

CONFIG=dict(form_id='synthetic_form',job_reference='TT-JOB-49C51587C3524024',candidate_name='Amina Test Candidate',
 job_question_id='job',consent_question_id='consent',cv_question_id='cv',expected_consent='I consent',upload_folder_id='folder')
def page():
 def text(key,value):return {'questionId':key,'textAnswers':{'answers':[{'value':value}]}}
 return {'responses':[{'responseId':'approved_new','createTime':'2026-10-28T07:12:47Z','lastSubmittedTime':'2026-10-28T07:12:47Z',
  'answers':{'name':text('name','Amina Test Candidate'),'job':text('job',CONFIG['job_reference']),
   'consent':text('consent','I consent'),'cv':{'questionId':'cv','fileUploadAnswers':{'answers':[{'fileId':'one_file','mimeType':'application/pdf'}]}}}}]}
def metadata(data=b'%PDF-synthetic'):
 return dict(id='one_file',mimeType='application/pdf',size=str(len(data)),trashed=False,parents=['folder'],
 capabilities={'canDownload':True},md5Checksum=hashlib.md5(data,usedforsecurity=False).hexdigest())
class SingleResponseTests(unittest.TestCase):
 def test_one_filtered_request_no_page_token(self):
  q=parse_qs(urlparse(responses_url('synthetic_form')).query)
  self.assertEqual(q['pageSize'],['1']);self.assertEqual(q['filter'],['timestamp > 2026-10-16T00:00:00Z']);self.assertNotIn('pageToken',q)
 def test_only_response_and_stable_duplicate_key(self):
  a=select_response(page(),CONFIG);b=select_response(copy.deepcopy(page()),CONFIG)
  self.assertEqual(a[1],b[1]);self.assertEqual(a[2],'one_file')
 def test_ambiguity_never_returns_first(self):
  for p in [{},{'responses':[]},{'responses':page()['responses']*2},page()|{'nextPageToken':'next'},page()|{'nextPageToken':''}]:
   with self.assertRaises(SingleApplicationError):select_response(p,CONFIG)
 def test_historical_updated_response_still_rejected(self):
  p=page();p['responses'][0]['createTime']='2026-10-15T12:00:00Z'
  with self.assertRaisesRegex(SingleApplicationError,'outside_approved_window'):select_response(p,CONFIG)
 def test_wrong_job_or_consent_or_identity(self):
  for k,v in [('job','TT-JOB-AAAAAAAAAAAAAAAA'),('consent','No'),('name','Other synthetic candidate')]:
   p=page();p['responses'][0]['answers'][k]['textAnswers']['answers'][0]['value']=v
   with self.assertRaises(SingleApplicationError):select_response(p,CONFIG)
 def test_one_upload_and_safe_identity(self):
  for change in ['multiple','unsafe','mime']:
   p=page();files=p['responses'][0]['answers']['cv']['fileUploadAnswers']['answers']
   if change=='multiple':files.append(dict(files[0]))
   elif change=='unsafe':files[0]['fileId']='../unrelated'
   else:files[0]['mimeType']='text/html'
   with self.assertRaises(SingleApplicationError):select_response(p,CONFIG)
 def test_file_integrity_and_folder_scope(self):
  data=b'%PDF-synthetic';m=metadata(data)
  self.assertEqual(validate_metadata(m,'one_file','application/pdf','folder'),len(data))
  self.assertEqual(validate_bytes(data,m,'application/pdf'),hashlib.sha256(data).hexdigest())
  for patch in [{'id':'other_file'},{'parents':['unrelated']},{'trashed':True},{'size':'999999999'},{'md5Checksum':'bad'}]:
   with self.assertRaises(SingleApplicationError):validate_metadata(m|patch,'one_file','application/pdf','folder')
  with self.assertRaises(SingleApplicationError):validate_bytes(b'%PDF-changed',m,'application/pdf')
 def test_matching_hash_does_not_allow_wrong_signature(self):
  m=metadata(b'HTML payload')
  with self.assertRaises(SingleApplicationError):validate_bytes(b'HTML payload',m,'application/pdf')
 def test_distinct_response_has_distinct_key(self):
  p=page();p['responses'][0]['responseId']='other_new'
  self.assertNotEqual(select_response(page(),CONFIG)[1],select_response(p,CONFIG)[1])
if __name__=='__main__':unittest.main()
