"""Adapter contract/quality tests use synthetic arrays and mocked OpenCV, NOT face acceptance."""
import hashlib
import struct
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as N
import numpy as np
import pytest
from app.integrations.face.opencv_cpu import FaceSampleError,OpenCvCpuRecognizer,checked_detection,pinned_bytes,png_dimensions

FACE=[50.,40.,200.,240.,100.,100.,200.,100.,150.,160.,110.,210.,190.,210.,.99]

def png(width=320,height=320):
    return b'\x89PNG\r\n\x1a\n'+b'\0\0\0\rIHDR'+struct.pack('>II',width,height)+b'\x08\x02\0\0\0'+b'crc!'

@pytest.mark.parametrize('faces,code',[(None,'no_face'),([], 'no_face'),([FACE,FACE],'multiple_faces'),([[float('nan')]*15],'invalid_detection'),([FACE[:14]],'invalid_detection'),([[0]*15],'face_quality')])
def test_absent_multiple_corrupt_detection_rejected(faces,code):
    with pytest.raises(FaceSampleError) as error:checked_detection(faces,320,320)
    assert error.value.code==code

@pytest.mark.parametrize('index,value',[(14,.85),(2,40.),(0,-1.),(6,500.),(5,40.),(8,200.)])
def test_low_confidence_small_clipped_landmarks_and_pose_rejected(index,value):
    face=FACE.copy();face[index]=value
    with pytest.raises(FaceSampleError):checked_detection([face],320,320)


def test_bounded_png_header_and_exact_one_valid_geometry():
    assert png_dimensions(png())==(320,320)
    assert checked_detection([FACE],320,320)==tuple(FACE)
    for data in [b'corrupted',png(100000,100000),png(20,20)]:
        with pytest.raises(FaceSampleError):png_dimensions(data)


def test_artifacts_must_be_approved_pinned_bounded_and_not_symlinks():
    with TemporaryDirectory(prefix='tt-face-synthetic-') as directory:
        p=Path(directory)/'artificial';p.write_bytes(b'not a face')
        digest=hashlib.sha256(p.read_bytes()).hexdigest()
        assert pinned_bytes(p,digest,100)==b'not a face'
        for digest_,limit in [('0'*64,100),(digest,2),('unapproved',100)]:
            with pytest.raises(FaceSampleError):pinned_bytes(p,digest_,limit)
        link=Path(directory)/'link';link.symlink_to(p)
        with pytest.raises(FaceSampleError):pinned_bytes(link,digest,100)
    assert not Path(directory).exists()


def artifacts(directory):
    paths=[Path(directory)/name for name in ['face_detection_yunet_2023mar.onnx','face_recognition_sface_2021dec.onnx','artificial.png']]
    for p,data in zip(paths,[b'synthetic detector stub',b'synthetic recognizer stub',png()]):p.write_bytes(data)
    return paths,[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]

@pytest.mark.parametrize('failure',['none','blur','dark','contrast','corrupt','multiple','embedding'])
def test_cpu_adapter_alignment_quality_and_feature_contract_with_fake_cv(monkeypatch,failure):
    calls=[]
    class Gray:
        def mean(self):return 10 if failure=='dark' else 120
        def std(self):return 2 if failure=='contrast' else 30
    class Detector:
        def setInputSize(self,size):calls.append(('input',size))
        def detect(self,image):return None,np.array([FACE,FACE] if failure=='multiple' else [FACE])
    class Recognizer:
        def alignCrop(self,image,face):
            calls.append(('align',len(face)));return np.zeros((112,112,3),dtype=np.uint8)
        def feature(self,aligned):return np.array([[float('nan')]*128] if failure=='embedding' else [[1.]*128])
    def detector(*args):calls.append(('detector',args[-2:]));return Detector()
    def recognizer(*args):calls.append(('recognizer',args[-2:]));return Recognizer()
    cv=N(__version__='4.10.0',FaceDetectorYN=N(create=detector),FaceRecognizerSF=N(create=recognizer),
        dnn=N(DNN_BACKEND_OPENCV=3,DNN_TARGET_CPU=0),IMREAD_COLOR=1,COLOR_BGR2GRAY=6,CV_64F=6,
        imdecode=lambda *args:None if failure=='corrupt' else np.zeros((320,320,3),dtype=np.uint8),
        cvtColor=lambda *args:Gray(),Laplacian=lambda *args:N(var=lambda:1 if failure=='blur' else 100))
    monkeypatch.setitem(sys.modules,'cv2',cv)
    with TemporaryDirectory(prefix='tt-face-synthetic-') as directory:
        paths,digests=artifacts(directory)
        engine=OpenCvCpuRecognizer(paths[0],digests[0],paths[1],digests[1])
        if failure=='none':
            assert len(engine.extract_approved_png(paths[2],digests[2]))==128
            assert ('align',15) in calls
        else:
            with pytest.raises(FaceSampleError):engine.extract_approved_png(paths[2],digests[2])
        assert ('detector',(3,0)) in calls and ('recognizer',(3,0)) in calls
    assert not Path(directory).exists()

@pytest.mark.parametrize('version',[None,'4.5.5','5.0.0'])
def test_missing_or_unsupported_opencv_fails_closed(monkeypatch,version):
    monkeypatch.setitem(sys.modules,'cv2',None if version is None else N(__version__=version))
    with TemporaryDirectory(prefix='tt-face-synthetic-') as directory:
        paths,digests=artifacts(directory)
        with pytest.raises(FaceSampleError) as error:OpenCvCpuRecognizer(paths[0],digests[0],paths[1],digests[1])
        assert error.value.code=='opencv_or_models_unavailable'
