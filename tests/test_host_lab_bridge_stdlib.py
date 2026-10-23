"""Run the existing 17 Loadmaster host-bridge tests without installing pytest.

This is a stdlib adapter, not a replacement test suite. It runs the original
pytest test functions and fixtures unchanged, providing only the two pytest
features used by this particular module: fixture() and raises().

Run from Executor-Stage:
    python3 -m unittest discover -s tests -p 'test_host_lab_bridge_stdlib.py' -v

Synthetic inputs only. No real GPIO, cartridge mounts, or production services.
"""
from contextlib import closing
import importlib.util
import inspect
from pathlib import Path
import sys
import tempfile
import types
import unittest


class BridgeHostTests(unittest.TestCase):
    """Methods are loaded from adjacent unmodified pytest test module."""


def _load_original_tests():
    pytest_stub = types.ModuleType('pytest')
    pytest_stub.fixture = lambda fn: fn

    def raises(expected, match=None):
        checker = unittest.TestCase()
        if match is not None:
            return checker.assertRaisesRegex(expected, match)
        return checker.assertRaises(expected)

    pytest_stub.raises = raises
    # Avoid importing the unrelated host bootstrap/hardware dependency tree:
    # load the actual host polling modules from this checkout directly.
    host_package = 'truepanel.host'
    if host_package not in sys.modules:
        host = types.ModuleType(host_package)
        host.__path__ = [str(Path(__file__).resolve().parent.parent / 'truepanel' / 'host')]
        host.__package__ = host_package
        sys.modules[host_package] = host

    original = sys.modules.get('pytest')
    sys.modules['pytest'] = pytest_stub
    try:
        original_path = Path(__file__).with_name('test_host_lab_bridge.py')
        spec = importlib.util.spec_from_file_location('_original_host_bridge_tests', original_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f'Could not load {original_path}')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if original is None:
            del sys.modules['pytest']
        else:
            sys.modules['pytest'] = original


def _make_test(fn, fixture):
    def test(self):
        with tempfile.TemporaryDirectory(prefix='loadmaster-host-unittest-') as tmp:
            if fixture == 'tmp_path':
                fn(Path(tmp))
            elif fixture == 'rig':
                with closing(original_tests.rig()) as rig_generator:
                    rig = next(rig_generator)
                    fn(rig)
            else:
                self.fail(f'Unsupported fixture: {fixture}')
    test.__doc__ = f'Original pytest test: {fn.__name__}'
    return test


original_tests = _load_original_tests()
original = {
    name: func for name, func in vars(original_tests).items()
    if name.startswith('test_') and inspect.isfunction(func)
}
if len(original) != 17:
    raise RuntimeError(f'Expected exactly 17 original bridge tests, found {len(original)}')
for name, func in original.items():
    params = list(inspect.signature(func).parameters)
    if len(params) != 1:
        raise RuntimeError(f'Unsupported test signature {name}{params}')
    setattr(BridgeHostTests, name, _make_test(func, params[0]))
