"""Bounded one-request comparisons; no final held-out population or tuning."""

from dataclasses import dataclass, replace
from fractions import Fraction as Q
from time import perf_counter_ns

from iaa.enclosure import inside, separated, step, terminal
from iaa.plant import SensorFaults, flow, observe
from iaa.types import StateBox, primitive
from sa02.estimator import Observer
from sa02.intervals import interval
from sa02.model import FaultHypothesis, HistorySegment, SensorContract

from .model import Context, RequestLedger, Timing
from .policy import decide, dispatch


def clean_sensors():
    return SensorContract(
        hypotheses=(FaultHypothesis("no_bias", (interval(0),) * 4),), initial_splits=0
    )


@dataclass(frozen=True)
class Case:
    name: str
    prior_centre: tuple = (0, -40, 0, 0)
    prior_radii: tuple = (Q(1, 100), Q(4, 5), Q(1, 10000), Q(1, 10000))
    actual_initial: tuple = (0, Q(-203, 5), 0, 0)
    timing: Timing = Timing()
    broad_faults: bool = False
    drop_requested: bool = False
    actual_range_delay_ms: int = 40
    actual_bearing_delay_ms: int = 70
    range_bias_m: float = 0.0
    budget_mj: int = 500
    max_nodes: int = 255
    warm_packets: bool = False

    def initial_box(self):
        box = StateBox.around(self.prior_centre, self.prior_radii)
        if not box.contains(self.actual_initial):
            raise ValueError("Development truth outside declared initial box")
        return box


def cases():
    return (
        Case("alongtrack_ambiguity"),
        Case(
            "radial_ambiguity",
            prior_radii=(Q(4, 5), Q(1, 100), Q(1, 10000), Q(1, 10000)),
            actual_initial=(Q(3, 5), -40, 0, 0),
        ),
        Case("shared_bias_ambiguity", broad_faults=True),
        Case(
            "already_goal_eligible",
            prior_radii=(Q(1, 100),) * 2 + (Q(1, 10000),) * 2,
            actual_initial=(0, -40, 0, 0),
        ),
        Case(
            "existing_action_adequate",
            prior_centre=(0, -45, 0, 0),
            prior_radii=(Q(1, 2), Q(1, 2), Q(1, 10000), Q(1, 10000)),
            actual_initial=(0, -45, 0, 0),
        ),
        Case(
            "velocity_ambiguity",
            prior_radii=(Q(1, 100), Q(4, 5), Q(1, 10000), Q(1, 5)),
            actual_initial=(0, Q(-203, 5), 0, Q(1, 10)),
        ),
        Case("declared_late_range", timing=Timing(range_delay_ms=600), actual_range_delay_ms=600),
        Case("missing_requested_observation", drop_requested=True),
        Case("underestimated_range_delay", actual_range_delay_ms=600),
        Case(
            "unsafe_wait",
            prior_centre=(0, Q(-3003, 100), 0, Q(1, 4)),
            prior_radii=(Q(1, 100000),) * 4,
            actual_initial=(0, Q(-3003, 100), 0, Q(1, 4)),
        ),
        Case("model_work_budget_exhaustion", budget_mj=2),
        Case("partition_budget_exhaustion", max_nodes=3),
        Case("unmodelled_range_bias", range_bias_m=0.5, actual_initial=(0, Q(-197, 5), 0, 0)),
    )


def prepare(case):
    sensors = SensorContract(initial_splits=0) if case.broad_faults else clean_sensors()
    obs = Observer(case.initial_box(), sensors)
    packets = observe(case.actual_initial, 0, 0, SensorFaults())[0] if case.warm_packets else ()
    estimate = obs.update(
        packets, (HistorySegment(0, case.timing.now_ms, (0, 0)),), case.timing.now_ms
    )
    return Context(
        estimate, sensors, case.timing, resource_mj=case.budget_mj, max_nodes=case.max_nodes
    )


def run(case, method):
    context = prepare(case)
    start = perf_counter_ns()
    policy = decide(context, method)
    planner_ns = perf_counter_ns() - start
    certificate = policy["certificate"]
    requested = certificate["channel"] if certificate else None
    receipts = ()
    request_status = "not_requested"
    if requested:
        ledger = RequestLedger(context.resource_mj)
        request_status = ledger.reserve(
            "sa03-" + context.identity()[:16] + "-" + requested,
            context.timing.now_ms + context.timing.planner_model_ms,
            context.timing.apply_ms,
            policy["modeled_cost_mj"],
        )
        if request_status != "reserved":
            raise RuntimeError("Decision/dispatch resource accounting conflict")
    acquisition = flow(case.actual_initial, (0, 0), case.timing.acquire_ms / 1000)
    if requested and not case.drop_requested:
        faults = SensorFaults(
            start_ms=0,
            end_ms=10000,
            range_bias_m=case.range_bias_m,
            range_delay_ms=case.actual_range_delay_ms,
            bearing_delay_ms=case.actual_bearing_delay_ms,
        )
        pair, _ = observe(acquisition, case.timing.acquire_ms, 1, faults)
        receipts = tuple(
            replace(
                p,
                value=round(p.value, 12),
                packet_id="sa03-" + context.identity()[:16] + "-" + requested,
            )
            for p in pair
            if p.channel == requested
        )
    start = perf_counter_ns()
    dispatched = dispatch(context, policy, receipts, case.timing.apply_ms)
    recheck_ns = perf_counter_ns() - start
    truth = tuple(case.actual_initial)
    evaluation = StateBox.around(truth, (0, 0, 0, 0))
    safe = True
    dwell = 0
    max_dwell = 0
    traces = []
    before = after = None
    for t in range(0, case.timing.end_ms + 1, 10):
        if t:
            u = (
                dispatched["action"]
                if case.timing.apply_ms <= t - 10 < case.timing.apply_ms + 500
                else (0, 0)
            )
            truth = flow(truth, u, 0.01)
            evaluation, tube = step(evaluation, u, 10, (Q(1), Q(1)), Q(0))
            safe &= inside(tube) and separated(tube)
            dwell = dwell + 10 if terminal(tube) else 0
            max_dwell = max(max_dwell, dwell)
        if t == case.timing.apply_ms:
            before = truth
        if t == case.timing.apply_ms + 500:
            after = truth
        if t % 100 == 0:
            traces.append(
                dict(
                    at_ms=t,
                    state=tuple(round(v, 12) for v in truth),
                    evaluation_only=True,
                    continuous_containment_to_here=bool(safe),
                )
            )
    numeric_delta = sum(
        (after[j] - target) ** 2 - (before[j] - target) ** 2 for j, target in enumerate((0, -40))
    )
    assumptions = (
        case.range_bias_m == 0
        and case.actual_range_delay_ms <= case.timing.range_delay_ms
        and case.actual_bearing_delay_ms <= case.timing.bearing_delay_ms
    )
    summary = dict(
        case=case.name,
        method=method,
        policy_status=policy["status"],
        requested_channel=requested,
        operations=policy["operations"],
        modeled_cost_mj=policy["modeled_cost_mj"],
        all_reading_useful=bool(certificate and certificate["all_reading_useful"]),
        all_outcome_protection=bool(certificate and certificate["all_outcome_protection"]),
        realized_dispatch=dispatched,
        request_reservation=request_status,
        numeric_application_state_in_selected_hull=(
            dispatched["checked_application_hull"].contains(before)
            if dispatched["credited"]
            else None
        ),
        realized_numeric_task_change_m2=round(numeric_delta, 12),
        continuous_realized_containment=bool(safe),
        goal_dwell_lower_ms=max_dwell,
        mission_dwell_proved=max_dwell >= 2000,
        configured_observation_assumptions_satisfied=assumptions,
        simulation_only=True,
        hardware_energy_measured=False,
        real_time_feasible=False,
    )
    evidence = dict(
        context=primitive(context),
        policy=primitive(policy),
        receipts=primitive(receipts),
        dispatch=primitive(dispatched),
        trace=traces,
    )
    timing = dict(
        case=case.name,
        method=method,
        planner_ns=planner_ns,
        selected_tree_recheck_ns=recheck_ns,
        exceeds_50ms_planner_model=planner_ns > 50000000,
        host_only=True,
        target_processor=False,
    )
    return summary, evidence, timing
