"""Static checks on the state machine definition (no AWS needed)."""

import json
import re
from pathlib import Path

import pytest

from handlers import reserve_stock
from shared.config import MARKETPLACES

ROOT = Path(__file__).resolve().parents[1]
ASL_PATH = ROOT / "statemachine" / "order_flow.asl.json"
TEMPLATE_PATH = ROOT / "template.yaml"


@pytest.fixture(scope="module")
def asl():
    return json.loads(ASL_PATH.read_text(encoding="utf-8"))


def _walk_scopes(states: dict):
    """Yield every States dict (top level and each Parallel branch)."""
    yield states
    for s in states.values():
        for branch in s.get("Branches", []):
            yield from _walk_scopes(branch["States"])


def _all_states(states: dict):
    for scope in _walk_scopes(states):
        yield from scope.items()


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def _template_substitutions() -> set[str]:
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    block = re.search(r"DefinitionSubstitutions:\n((?:\s{8,}\w+:.*\n)+)", text)
    assert block, "DefinitionSubstitutions block not found in template.yaml"
    return set(re.findall(r"^\s+(\w+):", block.group(1), re.M))


def test_uses_jsonata(asl):
    assert asl["QueryLanguage"] == "JSONata"


def test_every_transition_target_exists_in_its_scope(asl):
    for scope in _walk_scopes(asl["States"]):
        names = set(scope)
        for name, state in scope.items():
            targets = [state.get("Next"), state.get("Default")]
            targets += [c.get("Next") for c in state.get("Choices", [])]
            targets += [c.get("Next") for c in state.get("Catch", [])]
            for t in filter(None, targets):
                assert t in names, f"{name} -> {t} does not exist"


def test_start_states_exist(asl):
    assert asl["StartAt"] in asl["States"]
    for _, state in _all_states(asl["States"]):
        for branch in state.get("Branches", []):
            assert branch["StartAt"] in branch["States"]


def test_every_state_is_reachable(asl):
    states = asl["States"]
    seen, todo = set(), [asl["StartAt"]]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        s = states[name]
        todo += [x for x in [s.get("Next"), s.get("Default")] if x]
        todo += [c["Next"] for c in s.get("Choices", []) + s.get("Catch", [])]
    assert seen == set(states)


def test_substitutions_match_template(asl):
    used = set(re.findall(r"\$\{(\w+)\}", ASL_PATH.read_text(encoding="utf-8")))
    assert used == _template_substitutions()


def test_no_substitution_syntax_inside_jsonata(asl):
    for s in _strings(asl):
        if s.startswith("{%"):
            assert s.endswith("%}"), s
            assert "${" not in s, f"SAM would try to substitute inside JSONata: {s}"


def test_parallel_has_one_branch_per_marketplace(asl):
    branches = asl["States"]["PushToMarketplaces"]["Branches"]
    mps = []
    for b in branches:
        (state,) = b["States"].values()
        assert state["Arguments"]["FunctionName"] == "${PushMarketplaceFunctionArn}"
        mps.append(state["Arguments"]["Payload"]["marketplace_id"])
    assert sorted(mps) == sorted(MARKETPLACES)


def test_catch_names_match_lambda_exception_classes(asl):
    caught = asl["States"]["ReserveStock"]["Catch"][0]["ErrorEquals"]
    for name in caught:
        assert issubclass(getattr(reserve_stock, name), Exception)
    retried = asl["States"]["ReserveStock"]["Retry"][0]["ErrorEquals"]
    assert "TransientError" in retried and hasattr(reserve_stock, "TransientError")


def test_every_task_has_a_retry(asl):
    for name, state in _all_states(asl["States"]):
        if state["Type"] == "Task":
            assert state.get("Retry"), f"{name} has no Retry"


def test_rejected_orders_are_visible_in_get_orders(asl):
    item = asl["States"]["RecordRejection"]["Arguments"]["Item"]
    assert item["gsi_pk"] == {"S": "ORDERS"}
    assert "created_at" in item and item["status"] == {"S": "REJECTED"}


def test_stores_are_updated_before_the_currency_conversion(asl):
    # Stock goes out first; the FX call (an outside feed) can never delay it.
    states = asl["States"]
    assert states["ReserveStock"]["Next"] == "PushToMarketplaces"
    assert states["PushToMarketplaces"]["Next"] == "ConvertToUSD"
    assert states["ConvertToUSD"]["Next"] == "IsStockLow"
    branch_args = json.dumps([b["States"] for b in states["PushToMarketplaces"]["Branches"]])
    assert "$fx" not in branch_args, "the store push must not depend on the conversion"


def test_fx_failure_does_not_fail_the_order(asl):
    (catch,) = asl["States"]["ConvertToUSD"]["Catch"]
    assert catch["ErrorEquals"] == ["States.ALL"]
    assert catch["Next"] == "IsStockLow"
    fx = catch["Assign"]["fx"]
    assert fx["fx_source"] == "fallback_error"
    # Unconverted amounts keep their own currency label; they are never called USD.
    assert fx["base_currency"] == "{% $order.currency %}"
    assert set(fx) == {"base_currency", "base_price", "base_total", "fx_rate", "fx_source", "fx_date"}


def test_reserve_stock_never_retries_business_errors(asl):
    retried = {e for r in asl["States"]["ReserveStock"]["Retry"] for e in r["ErrorEquals"]}
    assert not retried & {"States.ALL", "States.TaskFailed", "InsufficientStock", "UnknownSku"}


def test_idempotent_states_retry_task_failures(asl):
    for name in ("RaiseLowStockAlert", "FinalizeOrder", "RecordRejection"):
        retried = {e for r in asl["States"][name]["Retry"] for e in r["ErrorEquals"]}
        assert "States.TaskFailed" in retried, name


def test_execution_has_a_timeout(asl):
    assert 0 < asl["TimeoutSeconds"] <= 900


def test_rejection_path_ends_in_fail(asl):
    assert asl["States"]["RecordRejection"]["Next"] == "OversellPrevented"
    assert asl["States"]["OversellPrevented"]["Type"] == "Fail"
