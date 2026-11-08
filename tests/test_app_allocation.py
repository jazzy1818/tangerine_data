"""Exercise the analyst workflow through Streamlit's real script runner."""

from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class AllocationDashboardTests(unittest.TestCase):
    def test_unquantified_judge_event_keeps_analysis_running(self):
        root = Path(__file__).resolve().parents[1]
        with patch('gemini_advisor.HAVE_GOOGLE_GENAI', False):
            app = AppTest.from_file(str(root / 'app.py'), default_timeout=120).run()
            self.assertFalse(app.exception)
            before = {item.label: item.value for item in app.metric}
            app.text_input(key='judge_event').set_value('Divorce without financial amounts').run()
            self.assertFalse(app.exception)
            after = {item.label: item.value for item in app.metric}
            self.assertEqual(before['Month 6 Closing Balance'], after['Month 6 Closing Balance'])
            self.assertTrue(any('quantified effects only' in message.value for message in app.warning))
            self.assertTrue(any('SHOCK_UNDER_SPECIFIED' in str(item.value) for item in app.markdown))

    def test_opportunity_and_shock_are_visible_without_customer_questions(self):
        root = Path(__file__).resolve().parents[1]
        # The allocation review is local; an optional API credential must not
        # make this integration check send any requests to an external advisor.
        with patch('gemini_advisor.HAVE_GOOGLE_GENAI', False):
            app = AppTest.from_file(str(root / 'app.py'), default_timeout=120).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.tabs), 5)
            app.number_input(key='account_selector').set_value(49082).run()
            self.assertFalse(app.exception)
            metrics = {item.label: item.value for item in app.metric}
            self.assertNotEqual(metrics['Normal monthly allocation (conditional)'], '$0.00')
            app.slider(key='slider_income_mult').set_value(.55)
            app.slider(key='slider_bills_increase').set_value(.15)
            app.number_input(key='slider_repair_cost').set_value(100000.0)
            app.run()
            self.assertFalse(app.exception)
            metrics = {item.label: item.value for item in app.metric}
            self.assertEqual(metrics['Selected shock monthly allocation'], '$0.00')
            self.assertTrue(any('reducing or pausing' in message.value for message in app.warning))
            self.assertTrue(any('UNVERIFIED' in str(item.value) for item in app.markdown))


if __name__ == '__main__':
    unittest.main()
