"""Unleash ``gradualRolloutUserId`` stickiness.

GitLab serves this strategy through the Unleash client API. The bucket is the
same one the Unleash client uses: MurmurHash3 x86 32 of ``groupId:userId``,
then ``(hash % 100) + 1``. A user is included when that value is less than or
equal to the percentage.
"""

from typing import Any

_MASK = 0xFFFFFFFF
_C1 = 0xCC9E2D51
_C2 = 0x1B873593


def rollout_matches(strategy: dict[str, Any], context: dict[str, Any]) -> bool:
    """Return whether ``user_id`` falls inside the strategy percentage.

    Args:
        strategy: Strategy object. ``parameters.percentage`` and
            ``parameters.groupId`` are read when present.
        context: Evaluation context. ``user_id`` is the stickiness key.

    Returns:
        True when the user is inside the rollout. Missing users and a
        non-positive percentage are outside it.
    """
    user_id = context.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        return False

    parameters = strategy.get("parameters")
    mapping = parameters if isinstance(parameters, dict) else {}
    percentage = _percentage(mapping.get("percentage"))
    if percentage <= 0:
        return False

    group_id = mapping.get("groupId")
    group = group_id if isinstance(group_id, str) else ""
    return _bucket(user_id, group) <= percentage


def _percentage(value: Any) -> int:
    """Return a rollout percentage clamped to ``0..100``.

    Args:
        value: Raw parameter. GitLab sends this as a string.

    Returns:
        The percentage, or ``0`` when the value is not an integer.
    """
    if isinstance(value, bool) or not isinstance(value, int | str):
        return 0

    try:
        number = int(value)
    except ValueError:
        return 0

    if number > 100:
        return 100

    return max(number, 0)


def _bucket(user_id: str, group_id: str) -> int:
    """Return the 1-based stickiness bucket for one user.

    Args:
        user_id: Stickiness key.
        group_id: Unleash group id. Empty when the strategy omits it.

    Returns:
        An integer in ``1..100``.
    """
    material = f"{group_id}:{user_id}".encode()
    return (_murmur3_32(material) % 100) + 1


def _murmur3_32(data: bytes) -> int:
    """Hash ``data`` with MurmurHash3 x86 32 and seed 0.

    Args:
        data: Bytes to hash.

    Returns:
        An unsigned 32-bit digest.
    """
    state = _mix_tail(_mix_blocks(data), data)
    return _finalize(state, len(data))


def _mix_blocks(data: bytes) -> int:
    """Mix every complete 4-byte block.

    Args:
        data: Bytes to hash.

    Returns:
        The intermediate hash state.
    """
    state = 0
    for offset in range(0, len(data) - len(data) % 4, 4):
        block = int.from_bytes(data[offset : offset + 4], "little")
        state = _mix(state, _scramble(block))

    return state


def _mix_tail(state: int, data: bytes) -> int:
    """Mix the trailing 1 to 3 bytes.

    Args:
        state: Hash state after the full blocks.
        data: Original bytes.

    Returns:
        The state including the tail.
    """
    tail = data[len(data) - (len(data) % 4) :]
    if not tail:
        return state

    return _mix_tail_bytes(state, tail)


def _mix_tail_bytes(state: int, tail: bytes) -> int:
    """Scramble a non-empty tail into ``state``.

    Args:
        state: Hash state after the full blocks.
        tail: One to three trailing bytes.

    Returns:
        The updated state.
    """
    block = tail[0]
    if len(tail) >= 2:
        block ^= tail[1] << 8

    if len(tail) == 3:
        block ^= tail[2] << 16

    return state ^ _scramble(block)


def _scramble(block: int) -> int:
    """Apply the MurmurHash3 block scramble.

    Args:
        block: A 32-bit value.

    Returns:
        The scrambled value.
    """
    block = (block * _C1) & _MASK
    block = ((block << 15) | (block >> 17)) & _MASK
    return (block * _C2) & _MASK


def _mix(state: int, block: int) -> int:
    """Fold one scrambled block into the state.

    Args:
        state: Current hash state.
        block: Scrambled block.

    Returns:
        The updated state.
    """
    state ^= block
    state = ((state << 13) | (state >> 19)) & _MASK
    return (state * 5 + 0xE6546B64) & _MASK


def _finalize(state: int, length: int) -> int:
    """Finalize a MurmurHash3 32-bit digest.

    Args:
        state: Hash state after the body.
        length: Number of input bytes.

    Returns:
        The unsigned digest.
    """
    state = (state ^ length) & _MASK
    state ^= state >> 16
    state = (state * 0x85EBCA6B) & _MASK
    state ^= state >> 13
    state = (state * 0xC2B2AE35) & _MASK
    return state ^ (state >> 16)
