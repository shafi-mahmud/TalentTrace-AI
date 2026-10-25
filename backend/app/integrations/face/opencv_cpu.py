"""Optional OpenCV 4.x YuNet/SFace CPU adapter for approved, pinned artificial PNGs.

Not wired to HTTP/camera input. Models and OpenCV must be separately approved and
provisioned; neither is installed or downloaded by this module.
"""
import hashlib
import math
from pathlib import Path
import re
import struct


class FaceSampleError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def pinned_bytes(path: Path, expected_sha256: str, limit: int) -> bytes:
    if (not re.fullmatch(r"[a-f0-9]{64}", expected_sha256) or path.is_symlink()
            or not path.is_file() or not 0 < path.stat().st_size <= limit):
        raise FaceSampleError("artifact_unavailable")
    data = path.read_bytes()
    if len(data) > limit or hashlib.sha256(data).hexdigest() != expected_sha256:
        raise FaceSampleError("artifact_changed")
    return data


def png_dimensions(data):
    # Bound allocation before decoding. Approved fixtures are PNG only, not arbitrary uploads.
    if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[8:16] != b"\x00\x00\x00\rIHDR":
        raise FaceSampleError("corrupt_sample")
    width, height = struct.unpack(">II", data[16:24])
    if not 160 <= width <= 1920 or not 160 <= height <= 1920:
        raise FaceSampleError("sample_size")
    return width, height


def checked_detection(faces, width, height):
    if faces is None or len(faces) == 0:
        raise FaceSampleError("no_face")
    if len(faces) != 1:
        raise FaceSampleError("multiple_faces")
    face = tuple(float(v) for v in faces[0])
    if len(face) != 15 or not all(math.isfinite(v) for v in face):
        raise FaceSampleError("invalid_detection")
    x, y, w, h = face[:4]
    if (face[14] < .9 or min(w, h) < 80 or w*h < width*height*.08
            or x < 0 or y < 0 or x+w > width or y+h > height):
        raise FaceSampleError("face_quality")
    points = list(zip(face[4:14:2], face[5:14:2]))
    if any(not x <= px <= x+w or not y <= py <= y+h for px, py in points):
        raise FaceSampleError("face_quality")
    a, b, nose, mouth_a, mouth_b = points
    eye_distance = math.dist(a, b)
    if (eye_distance < 20 or abs(a[1]-b[1]) > eye_distance*.27
            or abs(nose[0]-(a[0]+b[0])/2) > eye_distance*.3
            or not max(a[1],b[1]) < nose[1] < min(mouth_a[1],mouth_b[1])):
        raise FaceSampleError("face_pose")
    return face


class OpenCvCpuRecognizer:
    """YuNet 2023mar + unquantized SFace 2021dec, OpenCV >=4.8,<5 only."""
    def __init__(self, detector_path, detector_sha256, recognizer_path, recognizer_sha256):
        if Path(detector_path).name != "face_detection_yunet_2023mar.onnx" or Path(recognizer_path).name != "face_recognition_sface_2021dec.onnx":
            raise FaceSampleError("unsupported_model_variant")
        pinned_bytes(Path(detector_path), detector_sha256, 2*1024*1024)
        pinned_bytes(Path(recognizer_path), recognizer_sha256, 50*1024*1024)
        try:
            import cv2
            import numpy as np
            version = tuple(int(n) for n in cv2.__version__.split('.')[:2])
            if not (4,8) <= version < (5,0):
                raise ValueError()
            self.cv, self.np = cv2, np
            self.detector = cv2.FaceDetectorYN.create(str(detector_path), "", (320,320), .6, .3, 5000,
                cv2.dnn.DNN_BACKEND_OPENCV, cv2.dnn.DNN_TARGET_CPU)
            self.recognizer = cv2.FaceRecognizerSF.create(str(recognizer_path), "",
                cv2.dnn.DNN_BACKEND_OPENCV, cv2.dnn.DNN_TARGET_CPU)
        except Exception:
            raise FaceSampleError("opencv_or_models_unavailable") from None

    def extract_approved_png(self, path, expected_sha256):
        data = pinned_bytes(Path(path), expected_sha256, 2*1024*1024)
        width, height = png_dimensions(data)
        cv, np = self.cv, self.np
        try:
            image = cv.imdecode(np.frombuffer(data, dtype=np.uint8), cv.IMREAD_COLOR)
            if image is None or image.shape != (height,width,3):
                raise FaceSampleError("corrupt_sample")
            self.detector.setInputSize((width,height))
            _, faces = self.detector.detect(image)
            face = checked_detection(faces, width, height)
            x,y,w,h = (int(v) for v in face[:4])
            gray = cv.cvtColor(image[y:y+h,x:x+w],cv.COLOR_BGR2GRAY)
            if not 40 <= float(gray.mean()) <= 215 or float(gray.std()) < 20 or float(cv.Laplacian(gray,cv.CV_64F).var()) < 60:
                raise FaceSampleError("lighting_or_blur")
            aligned = self.recognizer.alignCrop(image,np.asarray(face,dtype=np.float32))
            vector = self.recognizer.feature(aligned).reshape(-1)
            if len(vector) != 128 or not np.isfinite(vector).all() or float(np.linalg.norm(vector)) <= 1e-8:
                raise FaceSampleError("invalid_embedding")
            return tuple(float(v) for v in vector)
        except FaceSampleError:
            raise
        except Exception:
            raise FaceSampleError("recognition_unavailable") from None
