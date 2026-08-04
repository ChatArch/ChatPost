from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_publish_workflow_is_tag_only_and_cannot_bypass_version_gate():
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" not in workflow
    assert "tags:" in workflow
    assert '"v*"' in workflow
    assert "if: github.event_name == 'push'" not in workflow
    assert "RELEASE_TAG: ${{ steps.meta.outputs.tag }}" in workflow
    assert 'if [ "${GITHUB_REF_NAME}" != "${RELEASE_TAG}" ]; then' in workflow