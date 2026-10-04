"""Exercise runner access selection without a Kubernetes cluster or real sudo."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/resolve-kubectl.sh"


class KubectlResolverTests(unittest.TestCase):
    def run_case(self, direct, sudo, client_name="kubectl"):
        with tempfile.TemporaryDirectory(prefix="ope resolver ") as tmp:
            root = Path(tmp)
            config = root / "config with spaces.yaml"
            config.write_text("fixture")
            env_file = root / "github-env"
            log = root / "args"
            client = root / client_name
            client.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$MOCK_ARGS"\n'
                              'if [[ "${MOCK_ROOT:-0}" == 1 ]]; then exit "$MOCK_SUDO"; fi\n'
                              'exit "$MOCK_DIRECT"\n')
            fake_sudo = root / "sudo"
            fake_sudo.write_text('#!/bin/bash\n[[ "$1" == -n && "$2" == -- ]] || exit 90\n'
                                 'shift 2\nexport MOCK_ROOT=1\nexec "$@"\n')
            client.chmod(0o700)
            fake_sudo.chmod(0o700)
            env = dict(os.environ, PATH=f"{root}:/usr/bin:/bin", KUBECONFIG=str(config),
                       RUNNER_TEMP=tmp, GITHUB_ENV=str(env_file), MOCK_ARGS=str(log),
                       MOCK_DIRECT=str(direct), MOCK_SUDO=str(sudo))
            result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
            if direct == 0 or sudo == 0:
                self.assertEqual(result.returncode, 0, result.stderr)
                wrapper = env_file.read_text().strip().split("=", 1)[1]
                invoked = subprocess.run([wrapper, "get", "pods", "a b"], env=env)
                self.assertEqual(invoked.returncode, 0)
                expected = (["kubectl"] if client_name == "k3s" else [])
                expected += [f"--kubeconfig={config}", "get", "pods", "a b"]
                self.assertEqual(log.read_text().splitlines(), expected)
                self.assertEqual(config.read_text(), "fixture")
            else:
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(env_file.exists())
                self.assertFalse((root / "ope-kubectl").exists())

    def test_direct_access(self):
        self.run_case(0, 1)

    def test_existing_sudo_access(self):
        self.run_case(1, 0)

    def test_no_authorized_access_fails_closed(self):
        self.run_case(1, 1)

    def test_k3s_fallback_preserves_arguments(self):
        self.run_case(1, 0, "k3s")
