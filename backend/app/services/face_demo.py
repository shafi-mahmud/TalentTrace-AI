"""Synthetic-vector-only enrollment lifecycle; never accepts a face, image or embedding."""
import asyncio
from array import array
from dataclasses import dataclass
from app.integrations.face.metrics import cosine_similarity
import time
from uuid import UUID, uuid4
from fastapi import HTTPException

CONSENT_VERSION = "face-synthetic-demo-v1"
CONSENT_WORDING = (
    "Optional synthetic face-verification demonstration. Only built-in artificial numeric "
    "identities are used; no camera or real biometric collection is enabled. "
    "Consent is separate from captions, transcript storage and assistant processing. "
    "Temporary demo references expire within five minutes and can be withdrawn at any time. "
    "Similarity is not identity proof or liveness verification and does not determine hiring. "
    "Decline or request manual document/in-person review without biometric processing. "
    "Real biometric enrollment and longer retention are not approved or implemented."
)


@dataclass(frozen=True, repr=False)
class Binding:
    recruiter_id: UUID
    job_id: UUID
    batch_id: UUID
    upload_id: UUID
    interview_id: UUID
    invitation_id: UUID
    session_digest: str
    criteria_revision: int


@dataclass(repr=False)
class Entry:
    binding: Binding
    run_id: UUID
    expires: float
    timer: object = None
    reference: array | None = None
    result: dict | None = None


def synthetic_vector(fixture):
    # Intentionally not face embeddings or any claim of model accuracy.
    vectors = {
        "vector-a-reference": (1.,0.), "vector-a-probe": (1.,.01),
        "vector-b-reference": (0.,1.), "vector-b-probe": (.01,1.),
    }
    if fixture not in vectors:
        raise HTTPException(422,"Only built-in synthetic fixtures are permitted.")
    return array('f', (*vectors[fixture], *(0. for _ in range(126))))


def similarity(reference, probe):
    score = cosine_similarity(reference,probe)
    # OpenCV's example threshold is illustrative, not calibrated to this population.
    assessment = "inconclusive" if abs(score-.363)<.05 else "above_demo_threshold" if score>=.363 else "below_demo_threshold"
    return {"mode":"simulated_vectors","model_used":None,"similarity":round(score,6),
        "assessment":assessment,"identity_verified":False,"liveness_checked":False,"demonstration_only":True}


class FaceDemoStore:
    """Max 16 references, fixed 5-minute lifetime, no file/DB persistence or search."""
    def __init__(self, clock=time.monotonic):
        self.entries = {}
        self.clock = clock

    def remove(self, interview_id, run_id=None):
        entry = self.entries.get(interview_id)
        if entry is None or (run_id is not None and entry.run_id != run_id):
            return
        self.entries.pop(interview_id)
        if entry.timer:entry.timer.cancel()
        if entry.reference is not None:
            for i in range(len(entry.reference)):entry.reference[i]=0
            entry.reference = None
        entry.result = None

    def clear(self):
        for key in list(self.entries):self.remove(key)

    def checked(self, binding, run_id):
        entry = self.entries.get(binding.interview_id)
        if entry and (entry.binding != binding or entry.expires <= self.clock()):
            self.remove(binding.interview_id);entry=None
        if entry is None or entry.run_id != run_id:
            raise HTTPException(409,"Synthetic consent expired or unavailable.")
        return entry

    def consent(self, binding):
        for key, entry in list(self.entries.items()):
            if entry.expires <= self.clock():self.remove(key)
        if binding.interview_id in self.entries:
            entry = self.entries[binding.interview_id]
            if entry.binding == binding:
                raise HTTPException(409,"Synthetic demo already active. Withdraw before a new consent.")
            self.remove(binding.interview_id)
        if len(self.entries)>=16:raise HTTPException(503,"Synthetic demo capacity unavailable.")
        run_id=uuid4()
        entry=Entry(binding,run_id,self.clock()+300)
        entry.timer=asyncio.get_running_loop().call_later(300,self.remove,binding.interview_id,run_id)
        self.entries[binding.interview_id]=entry
        return {"run_id":str(run_id),"state":"consented","expires_in":300,"mode":"simulated_vectors"}

    def enroll(self,binding,run_id,fixture):
        entry=self.checked(binding,run_id)
        if entry.reference is not None:raise HTTPException(409,"Reference already enrolled.")
        entry.reference=synthetic_vector(fixture)
        return {"state":"enrolled","mode":"simulated_vectors","model_used":None}

    def compare(self,binding,run_id,fixture):
        entry=self.checked(binding,run_id)
        if entry.reference is None:raise HTTPException(409,"Enroll the selected reference first.")
        probe=synthetic_vector(fixture)
        try:entry.result=similarity(entry.reference,probe)
        finally:
            for i in range(len(probe)):probe[i]=0
        return dict(entry.result)

    def view(self,binding,run_id):
        entry=self.checked(binding,run_id)
        return {"state":"compared" if entry.result else "enrolled" if entry.reference is not None else "consented",
                "result":dict(entry.result) if entry.result else None,"mode":"simulated_vectors"}
