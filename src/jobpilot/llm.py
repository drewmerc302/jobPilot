import anthropic
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from jobpilot.db import Database
from jobpilot.pricing import estimate_cost

llm_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((anthropic.APIError, anthropic.APIConnectionError)),
    reraise=True,
)


def call(
    client: anthropic.Anthropic,
    db: Database,
    action_type: str,
    *,
    run_id: int | None = None,
    job_id: str | None = None,
    **kwargs,
) -> anthropic.types.Message:
    """Instrumented wrapper around client.messages.create(). Records cost to DB."""
    response = client.messages.create(**kwargs)
    cost = estimate_cost(
        kwargs["model"], response.usage.input_tokens, response.usage.output_tokens
    )
    db.record_cost_event(
        action_type=action_type,
        model=kwargs["model"],
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        estimated_cost=cost,
        run_id=run_id,
        job_id=job_id,
    )
    return response
