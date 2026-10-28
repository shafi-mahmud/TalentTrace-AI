"""Offline secret allowlist and Compose isolation regression; no model/SMTP/network I/O."""
import importlib.util,json,os,subprocess,tempfile,unittest
from pathlib import Path
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('configure_groq',ROOT/'docker/configure_groq.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class GroqProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.cache=self.root/'models--BAAI--bge-small-en-v1.5';s=self.cache/'snapshots'/'offline';s.mkdir(parents=True)
        for name in ('config.json','tokenizer.json','model.safetensors','modules.json'):(s/name).write_text('synthetic')
        self.source=self.root/'source.env';self.source.write_text('GROQ_API_KEY=synthetic-key\nLLM_MODEL=synthetic-model\nDATABASE_URL=private-old-database\nASSEMBLYAI_API_KEY=not-authorized\n')
        self.target=self.root/'private'
    def create(self):module.create_configuration(self.source,self.cache,self.target)
    def test_allowlist_and_no_overwrite(self):
        self.create();v=dotenv_values(self.target/'groq.env')
        self.assertEqual(set(v),{'GROQ_API_KEY','LLM_MODEL'})
        self.assertEqual(v['GROQ_API_KEY'],'synthetic-key')
        before=(self.target/'groq.env').read_bytes()
        with self.assertRaises(FileExistsError):self.create()
        self.assertEqual((self.target/'groq.env').read_bytes(),before)
    def test_incomplete_assets_fail_before_configuration(self):
        (self.cache/'snapshots/offline/model.safetensors').unlink()
        with self.assertRaises(ValueError):self.create()
        self.assertFalse(self.target.exists())
    def test_explicit_private_telegram_opt_in_is_not_overridden(self):
        self.create()
        env=self.target/'groq.env'
        env.write_text(env.read_text()+'TELEGRAM_PUBLISHING_ENABLED=true\nTELEGRAM_BOT_TOKEN=synthetic-not-a-real-token\nTELEGRAM_CHANNEL_ID=-100000000001\n')
        result=subprocess.run(['docker','compose','--env-file',str(self.target/'compose.env'),'-f','compose.yaml','-f','compose.groq.yaml','config','--format','json'],cwd=ROOT,capture_output=True,text=True,check=True)
        backend=json.loads(result.stdout)['services']['backend']
        self.assertEqual(backend['environment']['TELEGRAM_PUBLISHING_ENABLED'],'true')
        self.assertEqual(backend['environment']['TELEGRAM_BOT_TOKEN'],'synthetic-not-a-real-token')
        self.assertEqual(set(backend['networks']),{'private','groq_egress'})
    def test_opt_in_compose_preserves_private_database_and_disabled_services(self):
        self.create()
        args=['docker','compose','--env-file',str(self.target/'compose.env'),'-f','compose.yaml','-f','compose.groq.yaml','config','--format','json']
        result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,check=True)
        c=json.loads(result.stdout);b=c['services']['backend'];d=c['services']['db']
        self.assertEqual(set(b['networks']),{'private','groq_egress'})
        self.assertEqual(set(d['networks']),{'private'});self.assertNotIn('ports',d)
        self.assertTrue(c['networks']['private']['internal'])
        self.assertEqual(b['environment']['GROQ_API_KEY'],'synthetic-key')
        self.assertNotIn('ASSEMBLYAI_API_KEY',b['environment'])
        self.assertNotIn('TELEGRAM_PUBLISHING_ENABLED',b['environment'])
        self.assertNotIn('TELEGRAM_BOT_TOKEN',b['environment'])
        for key in ('LIVEKIT_SYNTHETIC_DEMO_ENABLED','INTERVIEW_COPILOT_ENABLED','TRANSCRIPT_STORAGE_ENABLED','INTERVIEW_EMAIL_ENABLED','FACE_WORKFLOW_ENABLED','ASSEMBLYAI_SYNTHETIC_ENABLED'):
            self.assertEqual(b['environment'][key],'false')
        self.assertTrue(any(v.get('read_only') and v['target'].startswith('/models/') for v in b['volumes']))
        self.assertEqual(c['services']['frontend']['ports'][0]['host_ip'],'127.0.0.1')

if __name__=='__main__':unittest.main()
