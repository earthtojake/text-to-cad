"""A text-only host opens the engine's page: the model's own, `/<id>`, registered by the launch."""
import unittest
from unittest.mock import patch
from cadgen.mcp.browser import ViewerUnavailable, viewer_url


class ViewerUrlTest(unittest.TestCase):
    def test_a_model_is_launched_into_the_one_page_without_starting_another_server(self):
        page = 'http://localhost:123/6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab?token=t'
        with patch('cadgen.mcp.browser.request', return_value={'url': page}) as request:
            self.assertEqual(viewer_url('/parts/a #1.step', cwd='/models'), page)
            request.assert_called_once_with({'op': 'viewer', 'start': '/models', 'files': ['/parts/a #1.step']})

    def test_engine_failure_is_reported(self):
        with patch('cadgen.mcp.browser.request', return_value={'failed': 'missing client'}):
            with self.assertRaisesRegex(ViewerUnavailable, 'missing client'):
                viewer_url()


if __name__ == '__main__':
    unittest.main()
