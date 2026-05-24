import subprocess
import sys
import textwrap


def test_asr_service_treats_sounddevice_oserror_as_optional_dependency():
    script = textwrap.dedent(
        """
        import importlib.abc
        import sys

        class _SounddeviceLoader(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "sounddevice":
                    raise OSError("PortAudio library not found")
                return None

        sys.meta_path.insert(0, _SounddeviceLoader())

        import app.services.asr_service as asr_service

        assert asr_service.sd is None
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
