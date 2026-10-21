# -*- coding: utf-8 -*-
"""
Guards for the .env configuration files.

- .env.CONFIG.EXAMPLE must equal the version generated from config.py
  (catches accidental commits of a locally edited EXAMPLE).
- Uncommenting every line of the EXAMPLE must reproduce the defaults of config.py.
- Every key in a tracked .env.CONFIG.* profile must belong to a field in config.py
  (catches typos / renamed parameters that would otherwise be ignored silently).
"""

import re
import unittest
from pathlib import Path

from districtgenerator.data_handling import generate_env_example as gen

DATA_DIR = gen.EXAMPLE_PATH.parent
KEY_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=")


class TestEnvConfig(unittest.TestCase):

    def test_example_is_up_to_date(self):
        current = gen.EXAMPLE_PATH.read_text(encoding="utf-8")
        self.assertEqual(
            current, gen.render(),
            "\n.env.CONFIG.EXAMPLE differs from config.py. It is generated and must not be edited by hand.\n"
            "If config.py changed, run: python -m districtgenerator.data_handling.generate_env_example\n"
            "If you only wanted to change values for yourself, put them into your own .env.CONFIG file "
            "and restore the EXAMPLE with: git restore districtgenerator/data/.env.CONFIG.EXAMPLE")

    def test_example_roundtrip_equals_defaults(self):
        from districtgenerator.data_handling import config as c

        active = "\n".join(re.sub(r"^# ([A-Z0-9_]+=)", r"\1", line) for line in gen.render().splitlines())
        tmp = DATA_DIR / ".env.CONFIG._ROUNDTRIP_TEST"
        tmp.write_text(active, encoding="utf-8")
        try:
            loaded = c.load_global_config(tmp.name)
        finally:
            tmp.unlink()

        for section in c.GlobalConfig.model_fields:
            cfg = getattr(loaded, section)
            default = type(cfg)(_env_file=None)
            self.assertEqual(cfg.__dict__, default.__dict__, f"Round trip differs in section '{section}'")

    def test_unprefixed_env_names_are_unique(self):
        """Classes without prefix read the same file: a name used twice would set both."""
        seen = {}
        for class_name, (_, prefix, fields) in gen.collect_fields().items():
            if prefix:
                continue
            for f in fields:
                self.assertNotIn(f.env_name, seen,
                                 f"{f.env_name} is defined in {seen.get(f.env_name)} and {class_name}")
                seen[f.env_name] = class_name

    def test_profiles_only_use_known_keys(self):
        known = {f.env_name for _, _, fields in gen.collect_fields().values() for f in fields}
        import subprocess
        try:
            tracked = subprocess.run(["git", "ls-files", "--", str(DATA_DIR)], capture_output=True,
                                     text=True, check=True, cwd=DATA_DIR).stdout.splitlines()
            tracked_names = {Path(p).name for p in tracked}
        except (OSError, subprocess.CalledProcessError):
            tracked_names = None   # no git available: check all files
        profiles = [p for p in DATA_DIR.glob(".env.CONFIG*")
                    if p != gen.EXAMPLE_PATH and p.name != ".env.CONFIG"
                    and (tracked_names is None or p.name in tracked_names)]
        for profile in profiles:
            with self.subTest(profile=profile.name):
                unknown = []
                for line in profile.read_text(encoding="utf-8").splitlines():
                    m = KEY_RE.match(line)
                    if m and m.group(1).upper() not in known:
                        unknown.append(m.group(1))
                self.assertEqual(unknown, [], f"Unknown keys in {profile.name} (would be ignored silently)")


if __name__ == "__main__":
    unittest.main()
