"""Bounded observation scalars; never pass an unchecked string to Fraction."""

import math
import re
from fractions import Fraction

MAX_BITS = 512
MAX_MAGNITUDE = 10**9
GRAMMAR = re.compile(r"[+-]?[0-9]{1,80}(?:/[0-9]{1,80}|\.[0-9]{1,30})?\Z")


def _checked_pair(numerator, denominator):
    if denominator <= 0:
        raise ValueError("Observation denominator must be positive")
    common = math.gcd(numerator, denominator)
    n, d = numerator // common, denominator // common
    if max(n.bit_length(), d.bit_length()) > MAX_BITS or abs(n) > MAX_MAGNITUDE * d:
        raise ValueError("Observation magnitude or bit-size limit")
    return n, d


def observation_value(value):
    """Preserve built-in int/float values; normalize supported strings exactly.

    String parsing is length/grammar bounded before int, powers or Fraction.
    A finite built-in float has a bounded short decimal representation, so its
    temporary integer pair is bounded independently of any external exponent.
    No Fraction is constructed until the normalized pair passes the limits.
    """
    if type(value) is int:
        if value.bit_length() > MAX_BITS or abs(value) > MAX_MAGNITUDE:
            raise ValueError("Observation integer limit")
        return value
    if type(value) is float:
        if not math.isfinite(value) or abs(value) > MAX_MAGNITUDE:
            raise ValueError("Observation finite-float magnitude limit")
        text = repr(value).lower()
        mantissa, _, exponent = text.partition("e")
        fractional_digits = len(mantissa.partition(".")[2])
        n = int(mantissa.replace(".", ""))
        scale = fractional_digits - (int(exponent) if exponent else 0)
        if abs(scale) > 350:
            raise ValueError("Unsupported machine-float representation")
        n, d = (n, 10**scale) if scale >= 0 else (n * 10 ** (-scale), 1)
        _checked_pair(n, d)
        return value
    if type(value) is Fraction:
        if max(value.numerator.bit_length(), value.denominator.bit_length()) > MAX_BITS:
            raise ValueError("Observation rational limit")
        # The resulting packet must also be readable under the same wire grammar.
        value = str(value)
    if type(value) is not str or len(value) > 162 or GRAMMAR.fullmatch(value) is None:
        raise ValueError("Unsupported observation scalar type or spelling")
    if "/" in value:
        numerator, denominator = value.split("/")
        n, d = int(numerator), int(denominator)
    elif "." in value:
        integer, fractional = value.split(".")
        n, d = int(integer + fractional), 10 ** len(fractional)
    else:
        n, d = int(value), 1
    n, d = _checked_pair(n, d)
    return Fraction(n, d)


def preflight_snapshot(snapshot):
    """Bound raw Python observation values before JSON/dataclass conversion."""
    if type(snapshot) is not dict:
        raise ValueError("Snapshot object required")
    packets = snapshot.get("packets")
    if type(packets) is not list or len(packets) > 128:
        raise ValueError("Packet count/type limit")
    for packet in packets:
        if type(packet) is not dict or "value" not in packet:
            raise ValueError("Observation object required")
        observation_value(packet["value"])
