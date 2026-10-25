"""Pure 1:1 cosine arithmetic; no identity claim, search or model invocation."""
import math


def cosine_similarity(reference, probe):
    if len(reference)!=128 or len(probe)!=128 or not all(math.isfinite(v) for v in (*reference,*probe)):
        raise ValueError("Invalid feature contract.")
    norm_a=math.sqrt(math.fsum(v*v for v in reference))
    norm_b=math.sqrt(math.fsum(v*v for v in probe))
    if min(norm_a,norm_b)<=1e-8 or not math.isfinite(norm_a*norm_b):
        raise ValueError("Invalid feature contract.")
    return max(-1.,min(1.,math.fsum(a*b for a,b in zip(reference,probe))/(norm_a*norm_b)))
