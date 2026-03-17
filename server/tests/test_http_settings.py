"""Test HTTP settings parsing and derived runtime flags."""

import unittest
from pathlib import Path
from unittest import mock

from fishtest.http.settings import (
    HTMX_INPUT_CHANGED_DELAY_MS,
    PERSISTENT_UI_COOKIE_MAX_AGE_SECONDS,
    TASK_SEMAPHORE_SIZE,
    THREADPOOL_TOKENS,
    AppSettings,
    default_static_dir,
    env_int,
)

DEFAULT_ENV_VALUE = 17
INVALID_ENV_VALUE = "not-an-int"
CUSTOM_STATIC_DIR = "/tmp/fishtest-static"
CUSTOM_OPENAPI_URL = "/openapi.json"


class SettingsContractTests(unittest.TestCase):
    def test_env_int_uses_default_for_blank_or_invalid_values(self):
        with mock.patch.dict("os.environ", {"FISHTEST_SAMPLE_INT": ""}, clear=False):
            self.assertEqual(
                env_int("FISHTEST_SAMPLE_INT", default=DEFAULT_ENV_VALUE),
                DEFAULT_ENV_VALUE,
            )

        with mock.patch.dict(
            "os.environ",
            {"FISHTEST_SAMPLE_INT": INVALID_ENV_VALUE},
            clear=False,
        ):
            self.assertEqual(
                env_int("FISHTEST_SAMPLE_INT", default=DEFAULT_ENV_VALUE),
                DEFAULT_ENV_VALUE,
            )

    def test_default_static_dir_uses_env_override(self):
        with mock.patch.dict(
            "os.environ",
            {"FISHTEST_STATIC_DIR": CUSTOM_STATIC_DIR},
            clear=False,
        ):
            self.assertEqual(default_static_dir(), Path(CUSTOM_STATIC_DIR))

    def test_default_static_dir_defaults_to_package_static_directory(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            static_dir = default_static_dir()

        self.assertEqual(static_dir.name, "static")
        self.assertEqual(static_dir.parent.name, "fishtest")

    def test_app_settings_from_env_reads_openapi_url(self):
        with mock.patch.dict(
            "os.environ",
            {
                "FISHTEST_PORT": "8001",
                "FISHTEST_PRIMARY_PORT": "8000",
                "OPENAPI_URL": CUSTOM_OPENAPI_URL,
            },
            clear=True,
        ):
            settings = AppSettings.from_env()

        self.assertEqual(settings.port, 8001)
        self.assertEqual(settings.primary_port, 8000)
        self.assertFalse(settings.is_primary_instance)
        self.assertEqual(settings.openapi_url, CUSTOM_OPENAPI_URL)

    def test_runtime_limits_keep_headroom_for_http_work(self):
        self.assertGreater(THREADPOOL_TOKENS, TASK_SEMAPHORE_SIZE)
        self.assertGreater(HTMX_INPUT_CHANGED_DELAY_MS, 0)
        self.assertGreater(PERSISTENT_UI_COOKIE_MAX_AGE_SECONDS, 0)
