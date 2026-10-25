"""Offline numeric lifecycle proof; deliberately not a face-model acceptance test."""
import argparse
import asyncio
import json
from uuid import uuid4
from app.services.face_demo import Binding,FaceDemoStore


async def demo():
    store=FaceDemoStore()
    scope=Binding(*(uuid4() for _ in range(6)),session_digest='synthetic-session',criteria_revision=1)
    try:
        from uuid import UUID
        run=UUID(store.consent(scope)['run_id'])
        store.enroll(scope,run,'vector-a-reference')
        same=store.compare(scope,run,'vector-a-probe')
        different=store.compare(scope,run,'vector-b-probe')
        return {'mode':'simulated_vectors','model_used':None,'same_artificial_identity':same,
                'different_artificial_identity':different,'real_biometric_acceptance':'BLOCKED'}
    finally:
        store.clear()
        assert not store.entries


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthetic-only',action='store_true',required=True)
    parser.parse_args()
    print(json.dumps(asyncio.run(demo()),indent=2))
