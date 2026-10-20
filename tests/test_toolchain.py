import stat
import unittest
import zipfile

from tools.toolchain import archive_path


class CompilerArchiveTests(unittest.TestCase):
    def test_rejects_traversal_and_platform_path_tricks(self):
        for name in ["../acts.exe", "acts/../../outside", "/acts/file", "C:/acts/file", "acts\\..\\outside", "unrelated/file"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                archive_path(zipfile.ZipInfo(name))

    def test_rejects_symbolic_links(self):
        member = zipfile.ZipInfo("acts/bin/acts.exe")
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaises(ValueError):
            archive_path(member)

    def test_accepts_expected_layout(self):
        self.assertEqual(archive_path(zipfile.ZipInfo("acts/bin/acts.exe")).as_posix(), "acts/bin/acts.exe")


if __name__ == "__main__":
    unittest.main()
