"""Call original frozen methods, retaining their different mathematical obligations."""

from fractions import Fraction as Q
from .protocol import validate_request, normalized, check_action


def prepare(req):
    validate_request(req)
    if req["domain"] == "cart":
        from transfer_cart_v1.schema import validate

        value = validate(req["payload"])
        return value, Q(value["delay"]), Q(value["authority"])
    from evaluation.runner import _information

    info = _information(req["payload"])
    return info, Q(info.application_time), info.authority


def decide_prepared(req, value):
    if req["domain"] == "cart":
        from transfer_cart_v1.policies import decide

        return decide(value, req["method"], budget_s=1.0)
    from candidate.certify import decide

    return decide(value, budget_s=1.0)


def validate_prediction(req, prediction, authority):
    result = normalized(prediction, req["domain"])
    if result["status"] == "prefix" and not check_action(result["action"], authority):
        raise ValueError("Returned action exceeds exact authority")
    return result


def verify_fixed(req, prediction):
    """Optional offline check, outside measured service. Not a new policy trial."""
    value, _, _ = prepare(req)
    label = normalized(prediction, req["domain"])["status"]
    if req["domain"] == "cart":
        from transfer_cart_v1.reference import action_check, dual_check

        if label == "prefix":
            return action_check(value, prediction["action"])["status"] == "contained"
        if label == "obstruction":
            return dual_check(value, prediction["details"]["obstruction"]["weights"])["proved"]
    else:
        from candidate.certify import certify_action
        from candidate.affine import recheck_certificate

        if label == "prefix":
            return (
                certify_action(value, tuple(Q(x) for x in prediction["action"]))["status"]
                == "certified_common_prefix"
            )
        if label == "obstruction":
            return recheck_certificate(value, prediction["negative"])["proved"]
    return None
