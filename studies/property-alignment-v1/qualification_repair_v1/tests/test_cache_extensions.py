"""Cache reuse with timing and actuation bounds; no protected inputs."""

from fractions import Fraction as Q
from candidate.information import Hypothesis, InformationSet
from candidate.certify import execution_schedule
from adjudication.flow import Model, propagate_schedule
from qualification_repair_v1.core import _queue_arcs, _QueueCache, _continuation


def test_queue_reuse_preserves_exact_arcs_with_uncertainty():
    h = Hypothesis(
        (Q("-.01"), Q("-60.01"), Q("-.001"), Q("-.001")),
        (Q(".01"), Q("-59.99"), Q(".001"), Q(".001")),
    )
    for age, delay in ((0, 0), (1, 0), (0, 1), (1, 1)):
        for eta in ((Q(1), Q(1)), (Q(1, 2), Q(1)), (Q(0), Q(1))):
            info = InformationSet(
                (h,),
                age=age,
                delay=delay,
                queue=tuple((Q(".002"), Q("-.001")) for _ in range(age + delay)),
                effectiveness=eta,
                disturbance=Q("0.00001"),
            )
            queue, final = _queue_arcs(info, h)
            cache = _QueueCache(info.identity(), h, final)
            for action in ((0, 0), (Q("-.019"), 0)):
                tail = _continuation(info, cache, action)
                full = propagate_schedule(
                    Model("hcw"), h.enclosure(), execution_schedule(info, action)
                )
                assert queue + tail == tuple(full)


def test_taylor_point_enclosure_is_nested_in_surrounding_range():
    h = Hypothesis((Q("4.99"), -50, Q("-.001"), Q("-.001")), (Q("5.01"), -50, Q(".001"), Q(".001")))
    arcs = propagate_schedule(Model("hcw"), h.enclosure(), [(0, Q(1, 4), (Q(".005"), Q("-.005")))])
    arc = arcs[0]
    for i in range(8):
        for j in range(i + 1, 9):
            a, b = Q(i, 32), Q(j, 32)
            whole = arc.range(a, b)
            assert all(whole.contains(arc.point(t)) for t in (a, (a + b) / 2, b))
