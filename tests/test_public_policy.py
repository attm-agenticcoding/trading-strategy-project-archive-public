import unittest
from scripts.check_public import scan_bytes, validate_url


class PublicBoundaryTests(unittest.TestCase):
    def test_local_identity_and_opaque_ids_are_rejected(self):
        examples = [b"/" + b"Users/" + b"example/research", b"app" + b"gprj_" + b"a" * 32,
                    b'"source_' + b'session":{}']
        for value in examples:
            with self.assertRaises(ValueError):
                scan_bytes(value)

    def test_credential_and_notification_candidates_are_rejected(self):
        for value in [b"gh" + b"p_" + b"A" * 30, b"https://ntfy" + b".sh/example-topic"]:
            with self.assertRaises(ValueError):
                scan_bytes(value)

    def test_signed_queries_and_embedded_credentials_are_rejected(self):
        for value in ["https://example.org/?" + "token=example", "https://" + "user:" + "password@" + "example.org/"]:
            with self.assertRaises(ValueError):
                validate_url(value)

    def test_ordinary_original_analysis_and_public_links_are_accepted(self):
        scan_bytes("原创分析与数值结果。".encode())
        validate_url("https://x.com/example/status/123")
