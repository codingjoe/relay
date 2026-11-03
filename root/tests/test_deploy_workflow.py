import os
import shutil
import subprocess
from pathlib import Path

import yaml

DEPLOY_WORKFLOW = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deploy.yml"
)

# kubectl parses these flags before it reaches the cluster, so a stub that
# applies the same rule catches the combination without a server.
STUB_KUBECTL = """\
#!/usr/bin/env bash
all=""
selector=""
for arg in "$@"; do
    case "$arg" in
        --all) all=1 ;;
        --field-selector=*) selector=1 ;;
    esac
done
if [ -n "$all" ] && [ -n "$selector" ]; then
    echo "error: setting 'all' parameter but found a non empty selector." >&2
    exit 1
fi
exit 0
"""


def run_step(name, tmp_path):
    """Execute a deploy step with a stub kubectl on PATH."""
    steps = yaml.safe_load(DEPLOY_WORKFLOW.read_text())["jobs"]["deploy"]["steps"]
    step = next(step for step in steps if step.get("name") == name)

    kubectl = tmp_path / "kubectl"
    kubectl.write_text(STUB_KUBECTL)
    kubectl.chmod(0o755)
    bash = shutil.which("bash")
    assert bash

    return subprocess.run(  # noqa: S603
        [bash, "-e", "-c", step["run"]],
        capture_output=True,
        check=False,
        env=os.environ | {"PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"},
        text=True,
    )


def test_prune_failed_pods__survives_the_kubectl_flag_rules(tmp_path):
    result = run_step("Drop failed pods from earlier releases", tmp_path)

    assert result.returncode == 0, result.stderr
