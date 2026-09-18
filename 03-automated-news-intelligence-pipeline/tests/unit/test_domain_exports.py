from importlib import import_module

import pytest

import app.domain as domain

EXPECTED_EXPORTS = {
    "DeliveryAttempt": "app.domain.delivery",
    "DeliveryStatus": "app.domain.enums",
    "Digest": "app.domain.digest",
    "DigestItem": "app.domain.digest",
    "DigestStatus": "app.domain.enums",
    "DigestTag": "app.domain.enums",
    "DomainError": "app.domain.exceptions",
    "ErrorCode": "app.domain.enums",
    "FeedFetch": "app.domain.feed_fetch",
    "FeedFetchStatus": "app.domain.enums",
    "IgnoreReason": "app.domain.enums",
    "InvalidStateTransitionError": "app.domain.exceptions",
    "NewsItem": "app.domain.entities",
    "NewsItemStatus": "app.domain.enums",
    "PipelineRun": "app.domain.pipeline",
    "PipelineRunStatus": "app.domain.enums",
    "Source": "app.domain.entities",
    "TriggerType": "app.domain.enums",
    "ensure_digest_transition": "app.domain.state_machine",
    "ensure_news_item_transition": "app.domain.state_machine",
    "ensure_pipeline_run_transition": "app.domain.state_machine",
}


def test_domain_exports_match_public_contract() -> None:
    assert set(domain.__all__) == set(EXPECTED_EXPORTS)


def test_domain_exports_have_no_duplicates() -> None:
    assert len(domain.__all__) == len(set(domain.__all__))


@pytest.mark.parametrize(
    ("name", "module_name"),
    list(EXPECTED_EXPORTS.items()),
)
def test_domain_export_matches_implementation(
    name: str,
    module_name: str,
) -> None:
    implementation_module = import_module(module_name)

    assert getattr(domain, name) is getattr(implementation_module, name)


@pytest.mark.parametrize("name", list(EXPECTED_EXPORTS))
def test_domain_export_has_docstring(name: str) -> None:
    assert getattr(domain, name).__doc__, name
