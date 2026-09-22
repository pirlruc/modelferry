"""Stickiness of GitLab gradual rollouts."""

from model_fetcher.providers.gitlab.rollout import _murmur3_32, rollout_matches


def test_murmurhash3_matches_the_unleash_vector() -> None:
    """The x86 32-bit hash of ``hello`` matches MurmurHash3 seed 0."""
    assert _murmur3_32(b"hello") == 613153351


def test_rollout_is_stable_and_splits_users() -> None:
    """The same user stays in one bucket, and 50 percent does not include everyone."""
    strategy = {
        "name": "gradualRolloutUserId",
        "parameters": {"percentage": "50", "groupId": "model_route"},
    }
    first = rollout_matches(strategy, {"user_id": "alice"})
    assert rollout_matches(strategy, {"user_id": "alice"}) is first
    included = {rollout_matches(strategy, {"user_id": f"user-{index}"}) for index in range(80)}
    assert included == {False, True}
    assert rollout_matches(strategy, {}) is False
