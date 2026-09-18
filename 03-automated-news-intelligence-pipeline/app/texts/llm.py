"""LLM client error messages."""

LLM_TIMEOUT = "OpenAI request timed out."
LLM_RATE_LIMITED = "OpenAI rate limit exceeded."
LLM_REQUEST_FAILED = "OpenAI request failed."
LLM_INVALID_OUTPUT = "OpenAI returned output that failed schema validation."
LLM_POST_VALIDATION_FAILED = "Model digest output failed post-validation."
LLM_FIXTURE_MISSING = "Demo LLM fixture could not be loaded."
