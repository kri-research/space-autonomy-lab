"""Exact analytic counterexamples, separate from the spacecraft plant."""

from fractions import Fraction as Q

from iaa.types import rational


def timing_case(b, v, authority, limit, acquired, latency, error=0, horizon=2):
    """Symmetric q=+/-b, qdot=+/-v; zero wait, sign observation, maximum braking.

    This specialization has qddot=u, no disturbance and exact two-state knowledge.
    It neither uses nor establishes HCW recovery or operational sensor tolerances.
    """
    b, v, authority, limit, acquired, latency, error, horizon = map(
        rational, (b, v, authority, limit, acquired, latency, error, horizon)
    )
    if not (
        0 <= b <= limit
        and v > 0
        and authority > 0
        and acquired >= 0
        and latency >= 0
        and error >= 0
        and horizon > 0
    ):
        raise ValueError("Invalid scalar timing contract")
    apply = acquired + latency
    latest_apply = (limit - b - v * v / (2 * authority)) / v
    latest_acquire = latest_apply - latency
    distinguishable = error < b + v * acquired
    wait_inside = b + v * apply <= limit
    recovery = distinguishable and apply <= latest_apply
    # Summing the two endpoint inequalities cancels the shared held input.
    obstruction = b + v * horizon > limit
    return dict(
        latest_application_s=latest_apply,
        latest_acquisition_s=latest_acquire,
        actual_application_s=apply,
        distinguishable_for_all_readings=distinguishable,
        waiting_containment=wait_inside,
        braking_recovery=recovery,
        maximum_absolute_position_after_braking=b + v * apply + v * v / (2 * authority),
        no_common_constant_command_through_horizon=obstruction,
        scalar_only=True,
        spacecraft_recovery=False,
    )


def examples():
    base = dict(
        b=Q(7, 10),
        v=Q(1, 5),
        authority=Q(2, 5),
        limit=1,
        acquired=Q(3, 4),
        latency=Q(1, 4),
        error=Q(1, 100),
        horizon=2,
    )
    cases = []
    for name, changes in (
        ("timely_information", {}),
        ("latest_useful_boundary", {"acquired": 1}),
        ("information_too_late", {"acquired": Q(5, 4)}),
        ("unsafe_wait", {"acquired": Q(3, 2)}),
        ("overlapping_readings_leave_opposite_commands", {"error": 1}),
        ("existing_held_action_adequate", {"horizon": 1}),
    ):
        params = base | changes
        cases.append(dict(name=name, input=params, result=timing_case(**params)))
    # Exact labelled finite hypotheses: a sensor resolves a nuisance label only.
    states = (
        (Q(-7, 10), Q(-1, 5), 0),
        (Q(-7, 10), Q(-1, 5), 1),
        (Q(7, 10), Q(1, 5), 0),
        (Q(7, 10), Q(1, 5), 1),
    )
    cases.append(
        dict(
            name="uncertainty_reduction_without_action_gain",
            hypotheses_before=states,
            observation_classes=((0, 2), (1, 3)),
            example_braking_actions=((Q(2, 5),), (Q(2, 5),), (Q(-2, 5),), (Q(-2, 5),)),
            conclusion="Each observation halves hypotheses but keeps conflicting actions",
        )
    )
    return cases
