from __future__ import annotations

import unittest

from wintoolbox.services.apps import split_windows_command


class UninstallCommandTests(unittest.TestCase):
    def test_quoted_path_with_spaces(self) -> None:
        executable, parameters = split_windows_command(
            '"C:\\Program Files (x86)\\WindowsInstallationAssistant\\Windows10UpgraderApp.exe" '
            "/SunValley /ForceUninstall"
        )
        self.assertEqual(
            executable,
            r"C:\Program Files (x86)\WindowsInstallationAssistant\Windows10UpgraderApp.exe",
        )
        self.assertEqual(parameters, "/SunValley /ForceUninstall")

    def test_msi_command(self) -> None:
        executable, parameters = split_windows_command(
            "MsiExec.exe /X{80F4CF9F-3D45-4126-8CFE-39245641D9AB}"
        )
        self.assertEqual(executable, "MsiExec.exe")
        self.assertEqual(parameters, "/X{80F4CF9F-3D45-4126-8CFE-39245641D9AB}")

    def test_no_parameters(self) -> None:
        executable, parameters = split_windows_command(
            '"C:\\soft\\WizTree\\unins000.exe"'
        )
        self.assertEqual(executable, r"C:\soft\WizTree\unins000.exe")
        self.assertEqual(parameters, "")

    def test_empty_command_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            split_windows_command("  ")


if __name__ == "__main__":
    unittest.main()
