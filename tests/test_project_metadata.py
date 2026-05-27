"""Regression tests for packaging metadata in pyproject.toml."""

import importlib
from pathlib import Path
import re
import tomllib


_PUBLIC_MODULE_PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _load_setuptools_config():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with pyproject_path.open("rb") as handle:
        tool = tomllib.load(handle)["tool"]
    return tool["setuptools"]


def _load_optional_dependencies():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with pyproject_path.open("rb") as handle:
        project = tomllib.load(handle)["project"]
    return project["optional-dependencies"]


def _load_package_data():
    return _load_setuptools_config()["package-data"]


def test_public_module_paths_are_documented_and_well_formed():
    """Top-level public modules must stay explicitly packaged.

    These names are importable module paths exposed by the wheel via
    [tool.setuptools].py-modules. Keep this list non-empty, syntactically
    valid, and duplicate-free so public entry points do not silently drop
    modules from packaged builds.
    """
    py_modules = _load_setuptools_config().get("py-modules")

    assert isinstance(py_modules, list), "[tool.setuptools].py-modules must be a list"
    assert py_modules, "[tool.setuptools].py-modules must document at least one public module path"

    malformed = [
        module_path
        for module_path in py_modules
        if not isinstance(module_path, str) or not _PUBLIC_MODULE_PATH_RE.fullmatch(module_path)
    ]
    assert not malformed, f"Malformed public module paths in pyproject.toml: {malformed}"

    seen = set()
    duplicates = []
    for module_path in py_modules:
        if module_path in seen:
            duplicates.append(module_path)
        seen.add(module_path)

    assert not duplicates, f"Duplicate public module paths in pyproject.toml: {duplicates}"


def test_documented_public_module_paths_are_importable():
    """Documented public modules must be safe to import as shipped APIs."""
    py_modules = _load_setuptools_config().get("py-modules")
    assert isinstance(py_modules, list), "[tool.setuptools].py-modules must be a list"

    failures = []
    for module_path in py_modules:
        try:
            importlib.import_module(module_path)
        except Exception as exc:  # pragma: no cover - assertion reports details
            failures.append(f"{module_path}: {type(exc).__name__}: {exc}")

    assert not failures, "Documented public module imports failed:\n" + "\n".join(failures)


def test_matrix_extra_not_in_all():
    """The [matrix] extra pulls `mautrix[encryption]` -> `python-olm`,
    which has Linux-only wheels and no native build path on Windows or
    modern macOS (archived libolm, C++ errors with Clang 21+).

    With matrix in [all], `uv sync --locked` on Windows tried to build
    python-olm from sdist and failed on `make`. As of 2026-05-12 the
    [matrix] extra is excluded from [all] entirely and routed through
    `tools/lazy_deps.py` (LAZY_DEPS["platform.matrix"]) — installs at
    first use, where the user is expected to have a toolchain.
    """
    optional_dependencies = _load_optional_dependencies()

    assert "matrix" in optional_dependencies, "[matrix] extra must still exist for explicit `pip install hermes-agent[matrix]`"
    # Must NOT appear in [all] in any form — neither unconditional nor
    # platform-gated. Lazy-install handles it.
    matrix_in_all = [
        dep for dep in optional_dependencies["all"]
        if "matrix" in dep
    ]
    assert not matrix_in_all, (
        "matrix must not appear in [all] — it's lazy-installed via "
        "tools/lazy_deps.py LAZY_DEPS['platform.matrix']. Found: "
        f"{matrix_in_all}"
    )


def test_lazy_installable_extras_excluded_from_all():
    """Policy (2026-05-12): every extra that has a `LAZY_DEPS` entry
    in `tools/lazy_deps.py` must be excluded from [all].

    The lazy-install system exists so one quarantined PyPI release
    (e.g. mistralai 2.4.6) can't break every fresh install. Putting a
    backend in BOTH [all] and LAZY_DEPS defeats that — fresh installs
    eager-install it and inherit whatever's broken upstream.

    If you're tempted to add an opt-in backend to [all] for "convenience,"
    add it to `LAZY_DEPS` instead so it installs at first use.
    """
    optional_dependencies = _load_optional_dependencies()

    # Hard-coded mirror of the extras that are in LAZY_DEPS as of
    # 2026-05-12. This list intentionally duplicates rather than
    # imports tools/lazy_deps.py so the test stays a contract — if
    # someone adds a new lazy-install backend, they have to update
    # this list AND verify [all] doesn't contain it.
    lazy_covered_extras = {
        "anthropic", "bedrock",
        "exa", "firecrawl", "parallel-web",
        "fal",
        "edge-tts", "tts-premium",
        "voice",  # faster-whisper / sounddevice / numpy
        "modal", "daytona",
        "messaging", "slack", "matrix", "dingtalk", "feishu",
        "honcho", "hindsight",
    }
    all_extra_specs = optional_dependencies["all"]
    for extra in lazy_covered_extras:
        offending = [
            spec for spec in all_extra_specs
            if f"hermes-agent[{extra}]" in spec
        ]
        assert not offending, (
            f"[{extra}] is in [all] but also in LAZY_DEPS. "
            f"Remove it from [all] in pyproject.toml — it lazy-installs "
            f"at first use. Found in [all]: {offending}"
        )


def test_messaging_extra_includes_qrcode_for_weixin_setup():
    optional_dependencies = _load_optional_dependencies()

    messaging_extra = optional_dependencies["messaging"]
    assert any(dep.startswith("qrcode") for dep in messaging_extra)


def test_dingtalk_extra_includes_qrcode_for_qr_auth():
    """DingTalk's QR-code device-flow auth (hermes_cli/dingtalk_auth.py)
    needs the qrcode package."""
    optional_dependencies = _load_optional_dependencies()

    dingtalk_extra = optional_dependencies["dingtalk"]
    assert any(dep.startswith("qrcode") for dep in dingtalk_extra)


def test_feishu_extra_includes_qrcode_for_qr_login():
    """Feishu's QR login flow (gateway/platforms/feishu.py) needs the
    qrcode package."""
    optional_dependencies = _load_optional_dependencies()

    feishu_extra = optional_dependencies["feishu"]
    assert any(dep.startswith("qrcode") for dep in feishu_extra)


def test_dashboard_plugin_manifests_and_assets_are_packaged():
    """Bundled dashboard plugins need their manifests and built assets in
    wheel installs so /api/dashboard/plugins can discover them outside a
    source checkout."""
    package_data = _load_package_data()
    plugin_data = package_data["plugins"]

    assert "*/dashboard/manifest.json" in plugin_data
    assert "*/dashboard/dist/*" in plugin_data
    assert "*/dashboard/dist/**/*" in plugin_data
