# Publishing to PyPI

Releases use PyPI Trusted Publishing through `.github/workflows/release.yml`. GitHub receives
a short-lived credential for the `tradevodata` project; there is no long-lived PyPI token to
store or rotate.

## One-time PyPI setup

In the existing `tradevodata` project's **Publishing** settings, add a GitHub Actions trusted
publisher with these exact values:

- Owner: `christianpichichero-max`
- Repository: `tradevodata-py`
- Workflow: `release.yml`
- Environment: `pypi`

The GitHub `pypi` environment must also exist before a release is dispatched.

## Release checklist

1. Bump `version` in `pyproject.toml` and `__version__` in
   `src/tradevodata/__init__.py`; keep them identical.
2. Merge the change to `main` after the Python client CI passes.
3. Publish a GitHub release tagged `v<version>` from that exact `main` commit.
4. Confirm the **Publish Python package** workflow passed.
5. Verify the release from a clean environment:

   ```bash
   python3 -m venv /tmp/tradevodata-release-check
   /tmp/tradevodata-release-check/bin/pip install tradevodata
   /tmp/tradevodata-release-check/bin/python -c \
     "import tradevodata as tv; print(tv.__version__)"
   ```

The workflow reruns the full test suite, builds both artifacts, validates their metadata,
then passes only those artifacts to the minimally privileged publishing job. PyPI refuses
overwriting an existing version, so every release needs a new version number.
