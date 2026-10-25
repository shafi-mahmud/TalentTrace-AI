"""One bounded follow-up: diagnose old probes and compare a preselected mild variant.

Only procedurally generated images; no camera, user image input, retries or network.
Run with the existing isolated OpenCV Python and PYTHONPATH=backend.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import time
from face_cpu_readiness import OFFICIAL_MODELS,available_mib,approved_root,draw_identity,temporary_fixtures


def detection_checks(faces,width,height):
    """Safe diagnostic labels only; duplicates no acceptance decision or threshold override."""
    if faces is None or len(faces)!=1:return {'detected_faces':0 if faces is None else len(faces)}
    f=faces[0];x,y,w,h=(float(v) for v in f[:4])
    return {'detected_faces':1,'confidence':round(float(f[14]),7),'confidence_at_least_0_9':bool(f[14]>=.9),
        'min_size_at_least_80':min(w,h)>=80,'area_at_least_8_percent':w*h>=width*height*.08,
        'box_inside_image':x>=0 and y>=0 and x+w<=width and y+h<=height,
        'landmarks_inside_box':all(x<=px<=x+w and y<=py<=y+h for px,py in zip(f[4:14:2],f[5:14:2]))}


def run(root,prior_manifest):
    approved_root(root)
    if available_mib()<1200:raise RuntimeError('Insufficient available memory.')
    os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
    import cv2 as cv
    import numpy as np
    from app.integrations.face.opencv_cpu import OpenCvCpuRecognizer,FaceSampleError
    from app.integrations.face.metrics import cosine_similarity
    cv.setNumThreads(1);cv.ocl.setUseOpenCL(False)
    models=list(OFFICIAL_MODELS);started=time.perf_counter()
    engine=OpenCvCpuRecognizer(root/'models'/models[0],OFFICIAL_MODELS[models[0]][0],root/'models'/models[1],OFFICIAL_MODELS[models[1]][0])
    result={'model_load_seconds':round(time.perf_counter()-started,4),'samples':{},'comparisons':{},
        'transform':'one fixed +1/255 brightness step, no resampling/translation','identity_verified':False,'liveness_checked':False}
    a=draw_identity(cv,np,'a');b=draw_identity(cv,np,'b');c=draw_identity(cv,np,'c')
    old=cv.warpAffine(cv.convertScaleAbs(a,alpha=1,beta=4),np.float32([[1,0,2],[0,1,1]]),(512,512),borderMode=cv.BORDER_REFLECT)
    probe=cv.convertScaleAbs(a,alpha=1,beta=1)
    if np.array_equal(a,probe):raise RuntimeError('Probe must differ in decoded pixels.')
    images={'identity-a-reference':a,'old-a-probe':old,'old-b-probe':b,'mild-a-probe':probe,'independent-c-probe':c}
    prior=json.loads(prior_manifest.read_text());features={};manifest={}
    original_ids={'identity-a-reference':'identity-a-reference','old-a-probe':'identity-a-probe','old-b-probe':'identity-b-probe'}
    with temporary_fixtures(root/'fixtures') as write:
        for name,image in images.items():
            if available_mib()<700:raise RuntimeError('Memory pressure; attempt stopped.')
            success,encoded=cv.imencode('.png',image)
            if not success:raise RuntimeError('PNG encoding failed.')
            raw=encoded.tobytes();digest=hashlib.sha256(raw).hexdigest()
            if name in original_ids and digest!=prior[original_ids[name]]['sha256']:raise RuntimeError('Original synthetic sample changed.')
            manifest[name]={'sha256':digest,'source':'local original procedural geometry'}
            path=write(name,raw);engine.detector.setInputSize((512,512))
            _,faces=engine.detector.detect(image);item=detection_checks(faces,512,512)
            if name.startswith('old-'):
                from app.integrations.face.opencv_cpu import checked_detection
                try:checked_detection(faces,512,512);item['geometry_status']='accepted'
                except FaceSampleError as error:item.update(geometry_status='rejected',reason=error.code)
            else:
                started=time.perf_counter()
                try:
                    features[name]=engine.extract_approved_png(path,digest)
                    item.update(status='accepted',embedding_dimensions=len(features[name]))
                except FaceSampleError as error:item.update(status='rejected',reason=error.code)
                item['pipeline_seconds']=round(time.perf_counter()-started,4)
            result['samples'][name]=item
        for probe_name in ('mild-a-probe','independent-c-probe'):
            if 'identity-a-reference' in features and probe_name in features:
                result['comparisons'][probe_name]={'cosine_similarity':round(cosine_similarity(features['identity-a-reference'],features[probe_name]),8),
                    'interpretation':'transformed-image consistency only' if probe_name=='mild-a-probe' else 'different procedural design; no real-world identity accuracy claim'}
    features.clear()
    result['temporary_samples_deleted']=not any((root/'fixtures').iterdir())
    result['peak_rss_mib']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2)
    result['available_mib_after']=round(available_mib(),1)
    (root/'fixture_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');(root/'fixture_manifest.json').chmod(0o600)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--prior-manifest',type=Path,required=True)
    p.add_argument('--synthetic-only',action='store_true',required=True);args=p.parse_args()
    result=run(args.root.resolve(),args.prior_manifest)
    report=args.root/'reports'/'matching.json'
    with report.open('x') as stream:report.chmod(0o600);json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2))
