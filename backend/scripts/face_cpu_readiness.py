"""Real CPU/model readiness on locally drawn geometry only; never camera/user images.

Run in the separate approved OpenCV environment, with PYTHONPATH=backend. Artifacts
are private and ignored; JSON reports contain counts/status/timings, never images or
feature vectors. No network or downloads occur in this script.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import resource
import time

OFFICIAL_MODELS = {
    'face_detection_yunet_2023mar.onnx': ('8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4',232589),
    'face_recognition_sface_2021dec.onnx': ('0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79',38696353),
}


def available_mib():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):return int(line.split()[1])/1024
    raise RuntimeError('Memory availability unknown.')


def draw_identity(cv,np,identity):
    """Original procedural geometry, no photographic source or learned generator."""
    y,x=np.mgrid[0:512,0:512]
    image=np.full((512,512,3),(178,185,190),dtype=np.uint8)
    wide=identity=='a';rx,ry=(133,177) if wide else (115,183)
    center=(256,270);xx=(x-center[0])/rx;yy=(y-center[1])/ry
    mask=xx*xx+yy*yy<=1
    z=np.sqrt(np.clip(1-xx*xx-yy*yy,0,1))
    light=np.clip(.68+.3*z-.12*xx-.07*yy,.4,1.1)
    skin=np.array((145,183,220) if wide else (110,152,185))
    noise=np.random.default_rng(123 if wide else 456).normal(0,1.6,(512,512,1))
    shaded=np.clip(light[:,:,None]*skin+noise,0,255).astype(np.uint8)
    image[mask]=shaded[mask]
    cv.ellipse(image,(256,480),(170,80),0,0,360,(70,65,65) if wide else (100,70,50),-1)
    cv.rectangle(image,(224,410),(288,475),tuple(int(v) for v in skin*.85),-1)
    for ex in (256-rx,256+rx):cv.ellipse(image,(ex,285),(14,34),0,0,360,tuple(int(v) for v in skin*.8),-1)
    # Hair cap, independent identity geometry, eyebrows, sclera/iris/lids.
    cv.ellipse(image,(256,154),(rx+2,73 if wide else 62),0,180,360,(35,40,48) if wide else (52,45,33),-1)
    eye_y=249 if wide else 242;spacing=52 if wide else 46
    for ex in (256-spacing,256+spacing):
        cv.ellipse(image,(ex,eye_y-26),(31 if wide else 25,8),0,180,350,(45,48,53),4)
        cv.ellipse(image,(ex,eye_y),(29 if wide else 25,12),0,0,360,(214,221,225),-1)
        cv.circle(image,(ex,eye_y),10,(55,75,82) if wide else (65,54,43),-1)
        cv.circle(image,(ex,eye_y),5,(15,17,18),-1)
        cv.circle(image,(ex-3,eye_y-4),2,(245,245,245),-1)
        cv.ellipse(image,(ex,eye_y),(29 if wide else 25,12),0,180,360,(70,84,103),2)
    nose_y=315 if wide else 320
    cv.line(image,(250,265),(239 if wide else 247,nose_y),tuple(int(v) for v in skin*.66),3)
    cv.ellipse(image,(256,nose_y),(20 if wide else 14,9),0,0,180,tuple(int(v) for v in skin*.6),2)
    for ex in (245,267):cv.ellipse(image,(ex,nose_y),(4,2),0,0,360,(65,70,85),-1)
    mouth_y=365 if wide else 370
    cv.ellipse(image,(256,mouth_y),(43 if wide else 32,11),0,0,360,(89,103,150),-1)
    cv.line(image,(216 if wide else 224,mouth_y),(296 if wide else 288,mouth_y),(48,57,75),2)
    cv.ellipse(image,(256,401),(34,9),0,0,180,tuple(int(v) for v in skin*.8),2)
    return image


@contextmanager
def temporary_fixtures(directory):
    """Delete only this run's files, including after inference failure."""
    owned=[]
    def write(name,data):
        path=directory/(name+'.png')
        with path.open('xb') as stream:
            owned.append(path);path.chmod(0o600);stream.write(data)
        return path
    try:yield write
    finally:
        for path in owned:path.unlink(missing_ok=True)


def approved_root(root):
    data_root=Path(__file__).resolve().parents[2]/'data'
    if not root.is_relative_to(data_root.resolve()):
        raise RuntimeError('Test root must be inside ignored project data.')
    for directory in (root,root/'fixtures',root/'models',root/'reports'):
        if directory.is_symlink() or not directory.is_dir() or directory.stat().st_mode & 0o077:
            raise RuntimeError('Test directories must be private, existing and not symlinks.')
    if (root/'reports'/'readiness.json').exists() or (root/'fixture_manifest.json').exists():
        raise RuntimeError('Existing acceptance evidence must not be overwritten; use a fresh private run root.')


def run(root):
    approved_root(root)
    if available_mib()<1200:raise RuntimeError('Resource gate: less than 1200 MiB available.')
    os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
    import cv2 as cv
    import numpy as np
    from app.integrations.face.opencv_cpu import OpenCvCpuRecognizer,FaceSampleError,pinned_bytes
    from app.integrations.face.metrics import cosine_similarity
    cv.setNumThreads(1);cv.ocl.setUseOpenCL(False)
    for name,(digest,size) in OFFICIAL_MODELS.items():
        data=pinned_bytes(root/'models'/name,digest,size)
        if len(data)!=size or data.startswith(b'version https://git-lfs'):
            raise RuntimeError('Incomplete model or LFS pointer.')
    del data
    started=time.perf_counter()
    detector,recognizer=OFFICIAL_MODELS
    engine=OpenCvCpuRecognizer(root/'models'/detector,OFFICIAL_MODELS[detector][0],root/'models'/recognizer,OFFICIAL_MODELS[recognizer][0])
    report={'mode':'actual_cpu_models_procedural_artificial_images','opencv':cv.__version__,'numpy':np.__version__,
        'model_load_seconds':round(time.perf_counter()-started,4),'models':OFFICIAL_MODELS,'samples':{},'comparisons':{},
        'identity_verified':False,'liveness_checked':False}
    a=draw_identity(cv,np,'a');b=draw_identity(cv,np,'b')
    probe=cv.warpAffine(cv.convertScaleAbs(a,alpha=1,beta=4),np.float32([[1,0,2],[0,1,1]]),(512,512),borderMode=cv.BORDER_REFLECT)
    images={'identity-a-reference':a,'identity-a-probe':probe,'identity-b-probe':b,
        'no-face':np.full((512,512,3),128,dtype=np.uint8),'multiple-artificial-faces':np.concatenate([a,b],axis=1),
        'poor-quality':cv.convertScaleAbs(cv.GaussianBlur(a,(61,61),15),alpha=.13,beta=0)}
    root.joinpath('fixtures').mkdir(exist_ok=True,mode=0o700)
    features={};manifest={}
    with temporary_fixtures(root/'fixtures') as write_fixture:
        for name,image in images.items():
            if available_mib()<700:raise RuntimeError('Resource gate: memory pressure during inference.')
            success,encoded=cv.imencode('.png',image)
            if not success:raise RuntimeError('Synthetic PNG encoding failed.')
            raw=encoded.tobytes();path=write_fixture(name,raw)
            digest=hashlib.sha256(raw).hexdigest();manifest[name]={'sha256':digest,'source':'local deterministic geometry; no photographic input'}
            # Record real detector output separately from full quality/embedding acceptance.
            started=time.perf_counter();engine.detector.setInputSize((image.shape[1],image.shape[0]));_,faces=engine.detector.detect(image)
            detection_seconds=time.perf_counter()-started
            item={'detected_faces':0 if faces is None else len(faces),'detector_seconds':round(detection_seconds,4)}
            started=time.perf_counter()
            try:
                features[name]=engine.extract_approved_png(path,digest)
                item.update(status='feature_extracted',feature_dimensions=len(features[name]))
            except FaceSampleError as error:item.update(status='rejected',reason=error.code)
            item['full_adapter_seconds']=round(time.perf_counter()-started,4);report['samples'][name]=item
        raw=b'not a PNG image';path=write_fixture('corrupt',raw)
        try:engine.extract_approved_png(path,hashlib.sha256(raw).hexdigest())
        except FaceSampleError as error:report['samples']['corrupt']={'status':'rejected','reason':error.code}
    for name in ('identity-a-probe','identity-b-probe'):
        if 'identity-a-reference' in features and name in features:
            report['comparisons'][name]={'cosine_similarity':round(cosine_similarity(features['identity-a-reference'],features[name]),6),
                'same_artificial_identity':name=='identity-a-probe','calibrated_identity_accuracy':False}
    report['matching_status']='executed_artificial_only' if len(report['comparisons'])==2 else 'blocked_by_unsuitable_artificial_fixtures'
    report['peak_rss_mib']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2)
    report['memory_available_mib_after']=round(available_mib(),1)
    (root/'fixture_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');(root/'fixture_manifest.json').chmod(0o600)
    # Fixtures are disposable; keep provenance hashes and sanitized metadata only.
    report['temporary_fixtures_removed']=True
    features.clear()
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--synthetic-only',action='store_true',required=True)
    args=parser.parse_args()
    result=run(args.root.resolve())
    text=json.dumps(result,indent=2)+'\n'
    (args.root/'reports'/'readiness.json').write_text(text);(args.root/'reports'/'readiness.json').chmod(0o600)
    print(text)
