"""Two bounded retries only for explicitly rejected, short-reset Groq 429s."""
import asyncio
import math
from groq import RateLimitError
from app.integrations.llm.diagnostics import logger, rate_limit_metadata


async def screening_completion(client, stage, **arguments):
    waited=0
    for attempt in range(3):
        try:
            return await client.chat.completions.create(**arguments)
        except RateLimitError as error:
            delay,quota,limit=rate_limit_metadata(error)
            # No guessing, long/day-limit retries, timeout retries or validation retries.
            if attempt==2 or delay is None or delay>59 or quota in {"tpd","rpd"}:
                raise
            wait=max(math.ceil(delay)+1,2**(attempt+1))
            if waited+wait>60:
                raise
            waited+=wait
            logger.warning("talenttrace_stage stage=%s category=rate_limit_backoff attempt=%s wait_seconds=%s quota=%s token_limit=%s",stage,attempt+1,wait,quota,limit)
            await asyncio.sleep(wait)
