import pytest
from pydantic_core import PydanticUndefined

from agent.models import GraphicResult, ProgressStep, SummaryResult
from agent.runtime_contract import (
    RuntimeInfographicsPayload,
    RuntimeProgressStep,
    RuntimeSummaryPayload,
    convert_model,
)


@pytest.mark.unit
def test_default_values_parity():
    # Helper to retrieve Pydantic model field default values (supporting default or default_factory)
    def get_field_default(field_info):
        if field_info.default is not PydanticUndefined:
            return field_info.default
        if field_info.default_factory is not None:
            return field_info.default_factory()
        return PydanticUndefined

    # Assert exact field name set equality across model twin pairs to guard against drift
    assert set(SummaryResult.model_fields) == set(RuntimeSummaryPayload.model_fields), (
        f"SummaryResult/RuntimeSummaryPayload field keys mismatch: {set(SummaryResult.model_fields) ^ set(RuntimeSummaryPayload.model_fields)}"
    )

    assert set(GraphicResult.model_fields) == set(
        RuntimeInfographicsPayload.model_fields
    ), (
        f"GraphicResult/RuntimeInfographicsPayload field keys mismatch: {set(GraphicResult.model_fields) ^ set(RuntimeInfographicsPayload.model_fields)}"
    )

    assert set(ProgressStep.model_fields) == set(RuntimeProgressStep.model_fields), (
        f"ProgressStep/RuntimeProgressStep field keys mismatch: {set(ProgressStep.model_fields) ^ set(RuntimeProgressStep.model_fields)}"
    )

    # 1. Compare defaults directly for ProgressStep vs RuntimeProgressStep
    for field_name, field_info in ProgressStep.model_fields.items():
        if field_name in RuntimeProgressStep.model_fields:
            domain_default = get_field_default(field_info)
            runtime_default = get_field_default(
                RuntimeProgressStep.model_fields[field_name]
            )
            if domain_default is not PydanticUndefined:
                assert domain_default == runtime_default, (
                    f"ProgressStep.{field_name} default mismatch: {domain_default} != {runtime_default}"
                )

    # 2. Compare defaults directly for SummaryResult vs RuntimeSummaryPayload
    for field_name, field_info in SummaryResult.model_fields.items():
        if field_name in RuntimeSummaryPayload.model_fields:
            domain_default = get_field_default(field_info)
            runtime_default = get_field_default(
                RuntimeSummaryPayload.model_fields[field_name]
            )
            # Note: required-vs-empty list/string defaults on the wire (summary_lines, key_points, article_text)
            # are intentional lenient defaults and are skipped in default comparison.
            if domain_default is not PydanticUndefined:
                assert domain_default == runtime_default, (
                    f"SummaryResult.{field_name} default mismatch: {domain_default} != {runtime_default}"
                )

    # 3. Compare defaults directly for GraphicResult vs RuntimeInfographicsPayload
    for field_name, field_info in GraphicResult.model_fields.items():
        if field_name in RuntimeInfographicsPayload.model_fields:
            domain_default = get_field_default(field_info)
            runtime_default = get_field_default(
                RuntimeInfographicsPayload.model_fields[field_name]
            )
            # Note: visual_plan is required in domain but has list default factory on wire, which is skipped.
            if domain_default is not PydanticUndefined:
                assert domain_default == runtime_default, (
                    f"GraphicResult.{field_name} default mismatch: {domain_default} != {runtime_default}"
                )


@pytest.mark.unit
def test_lossless_round_trip_defaults():
    # Verify defaults are safely preserved in round-trips
    # 1. SummaryResult defaults round-trip
    summary = SummaryResult(
        session_id="dummy",
        url="dummy",
        title="dummy",
        summary_lines=["dummy"],
        key_points=["dummy"],
        article_text="dummy",
    )
    assert summary.text_backend == "unknown"

    payload_s = convert_model(summary, RuntimeSummaryPayload)
    assert payload_s.text_backend == "unknown"

    restored_s = convert_model(payload_s, SummaryResult)
    assert restored_s.text_backend == "unknown"
    assert restored_s.model_dump() == summary.model_dump()

    # 2. GraphicResult defaults round-trip
    graphic = GraphicResult(
        session_id="dummy",
        visual_plan=["dummy"],
        artifact_path="dummy",
    )
    assert graphic.visual_style == "business"

    payload_g = convert_model(graphic, RuntimeInfographicsPayload)
    assert payload_g.visual_style == "business"

    restored_g = convert_model(payload_g, GraphicResult)
    assert restored_g.visual_style == "business"
    assert restored_g.model_dump() == graphic.model_dump()
