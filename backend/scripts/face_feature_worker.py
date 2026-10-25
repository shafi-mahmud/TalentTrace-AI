"""One server-selected artificial sample -> actual model feature; stdout is private IPC."""
import hashlib,json,os,sys
from pathlib import Path
from tempfile import TemporaryDirectory
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
from face_cpu_readiness import draw_identity,OFFICIAL_MODELS,available_mib
if available_mib()<1200:raise SystemExit(2)
import cv2 as cv
import numpy as np
from app.integrations.face.opencv_cpu import OpenCvCpuRecognizer
cv.setNumThreads(1);cv.ocl.setUseOpenCL(False)
request=json.loads(sys.stdin.buffer.read(1024));identity=request['identity'];probe=request['probe']
if identity not in ('a','c') or type(probe) is not bool:raise SystemExit(2)
root=Path(sys.argv[1]);temporary=Path(sys.argv[2]);names=list(OFFICIAL_MODELS)
engine=OpenCvCpuRecognizer(root/names[0],OFFICIAL_MODELS[names[0]][0],root/names[1],OFFICIAL_MODELS[names[1]][0])
image=draw_identity(cv,np,identity)
if probe:image=cv.convertScaleAbs(image,alpha=1,beta=1)
ok,data=cv.imencode('.png',image)
if not ok:raise SystemExit(2)
raw=data.tobytes();digest=hashlib.sha256(raw).hexdigest()
with TemporaryDirectory(prefix='synthetic-face-',dir=temporary) as folder:
    p=Path(folder)/'sample.png'
    with p.open('xb') as stream:p.chmod(0o600);stream.write(raw)
    feature=engine.extract_approved_png(p,digest)
print(json.dumps({'feature':feature,'provenance':{'model':'sface_2021dec','detector':'yunet_2023mar','sample_sha256':digest,
    'source':'server_generated_geometry','identity':identity,'models':OFFICIAL_MODELS}},allow_nan=False))
