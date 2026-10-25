"""No downloads/inference: readiness bounds, finite metrics and cleanup contracts."""
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest
from app.integrations.face.metrics import cosine_similarity
spec=importlib.util.spec_from_file_location('face_readiness',Path(__file__).resolve().parents[1]/'scripts'/'face_cpu_readiness.py')
readiness=importlib.util.module_from_spec(spec);spec.loader.exec_module(readiness)


def test_fixed_official_binary_contracts():
    models=readiness.OFFICIAL_MODELS
    assert len(models)==2 and models['face_detection_yunet_2023mar.onnx'][1]==232589
    assert models['face_recognition_sface_2021dec.onnx'][1]==38696353
    assert all(len(digest)==64 and size>200000 for digest,size in models.values())

@pytest.mark.parametrize('fail',[False,True])
def test_owned_fixture_cleanup_on_normal_and_interrupted_work(fail):
    with TemporaryDirectory(prefix='tt-face-cleanup-') as directory:
        root=Path(directory);existing=root/'preexisting.png';existing.write_bytes(b'leave alone')
        try:
            with readiness.temporary_fixtures(root) as write:
                a=write('owned',b'artificial geometry')
                assert a.exists() and a.stat().st_mode & 0o077==0
                with pytest.raises(FileExistsError):write('preexisting',b'never overwrite')
                if fail:raise RuntimeError('synthetic failure')
        except RuntimeError:assert fail
        assert not (root/'owned.png').exists()
        assert existing.read_bytes()==b'leave alone'


def test_nonignored_output_root_fails_before_loading():
    with TemporaryDirectory(prefix='tt-face-root-') as root:
        with pytest.raises(RuntimeError,match='ignored project data'):readiness.approved_root(Path(root))


def test_real_and_simulated_features_share_finite_cosine_contract():
    a=[1.]+[0.]*127;b=[0.,1.]+[0.]*126
    assert cosine_similarity(a,a)==1 and cosine_similarity(a,b)==0
    for invalid in ([0.]*128,[float('nan')]*128,[float('inf')]*128,[1.]*127):
        with pytest.raises(ValueError):cosine_similarity(a,invalid)
