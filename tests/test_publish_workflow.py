from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ci_runs_supported_pythons_and_distribution_cli_gates():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert 'python-version: ["3.10", "3.11", "3.12"]' in workflow
    for command in (
        "chatpost --version",
        "chatpost --tree",
        "chatpost --tree-brief",
        "python -m build",
        "python -m twine check dist/*",
        '"$RUNNER_TEMP/chatpost-wheel/bin/python" -m pip install dist/*.whl',
        "mkdocs build --strict",
    ):
        assert command in workflow


def test_public_docs_expose_full_and_brief_tree_commands():
    checked = (
        ROOT / "README.md",
        ROOT / "README.en.md",
        ROOT / "docs" / "index.md",
        ROOT / "docs" / "index.en.md",
        ROOT / "docs" / "quickstart.md",
        ROOT / "docs" / "quickstart.en.md",
        ROOT / "docs" / "cli-tree.md",
        ROOT / "docs" / "cli-tree.en.md",
        ROOT / "tests" / "cli-tests" / "README.md",
    )
    for path in checked:
        text = path.read_text(encoding="utf-8")
        assert "chatpost --tree" in text, path
        assert "chatpost --tree-brief" in text, path


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
    assert "git fetch --no-tags origin main:refs/remotes/origin/main" in workflow
    assert "git merge-base --is-ancestor \"${GITHUB_SHA}\" refs/remotes/origin/main" in workflow
    assert ("git fetch origin main " + "--tags") not in workflow
    assert ("git fetch origin master " + "--tags") not in workflow
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert ("PYPI" + "_API" + "_TOKEN") not in workflow
    assert ("TWINE" + "_PASSWORD") not in workflow
    assert ("secrets" + ".PYPI") not in workflow
    assert ("environment" + ": pypi") not in workflow


def test_preview_workflow_uses_site_url_and_fetches_gh_pages():
    workflow = (ROOT / ".github" / "workflows" / "preview.yaml").read_text(encoding="utf-8")

    assert "git fetch origin gh-pages --depth=1 || true" in workflow
    assert "mike deploy dev --push --update-aliases --allow-empty" in workflow
    assert "Path(\"mkdocs.yml\")" in workflow
    assert "CHATARCH_PREVIEW_URL" in workflow
    assert "https://arch.gh.wzhecnu.cn/${repo}/dev/" not in workflow
    assert ("github" + ".io") not in workflow
