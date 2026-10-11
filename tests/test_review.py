"""Reading-priority regressions: real archive cases plus contextual contrasts."""
import json
from pathlib import Path
import tempfile
import unittest

from adams_for_projects.cli import _top_topics_no_repeats
from adams_for_projects.exporter import write_run_artifact
from adams_for_projects.review import classify_title
from adams_for_projects.scoring import score_title, doc_bonus


class ReviewTests(unittest.TestCase):
    def test_saved_document_cases(self):
        cases = json.loads((Path(__file__).with_name('review_cases.json')).read_text())
        for case in cases:
            with self.subTest(accession=case['accession'], title=case['title']):
                review = classify_title(case['title'])
                self.assertEqual(review['priority'], case['priority'])
                self.assertEqual(review['document_type'], case['document_type'])
                self.assertEqual(review['version'], '2.0.0')
                self.assertEqual(review['basis'], 'title')
                self.assertTrue(review['reasons'])
                self.assertEqual(review, classify_title(case['title'].upper()))

    def test_contextual_contrasts(self):
        cases = [
            ('Notice of Violation and Proposed Imposition of Civil Penalty', 'HIGH'),
            ('Administrative Order for Enforcement', 'HIGH'),
            ('Notice of Public Meeting about Confirmatory Orders', 'BACKGROUND'),
            ('Inspection Procedure for Enforcement Orders', 'BACKGROUND'),
            ('U.S. Customs and Border Protection', 'BACKGROUND'),
            ('New Order Environmental Services NRC Form 532 Acknowledgement of Receipt', 'BACKGROUND'),
            ('Non-Proprietary Report', 'BACKGROUND'),
            ('Decommissioning Trust Fund Shortfall Notification', 'HIGH'),
            ('Annual Decommissioning Trust Fund Status Report: No Shortfall', 'MEDIUM'),
            ('Notice of Availability of Draft Environmental Assessment', 'MEDIUM'),
            ('Draft Environmental Assessment and Draft Finding of No Significant Impact', 'MEDIUM'),
            ('Final Environmental Assessment and Finding of No Significant Impact', 'HIGH'),
            ('Application for Order Approving Transfer of Licenses', 'MEDIUM'),
            ('Order Approving Transfer of Licenses', 'HIGH'),
            ('STC Issuance of Proposed Rule for Decommissioning', 'MEDIUM'),
            ('Final Rule for Decommissioning', 'HIGH'),
            ('Public Meeting on the Final Rule for Decommissioning', 'BACKGROUND'),
            ('Training on Loss of Offsite Power', 'BACKGROUND'),
            ('Report: No Loss of Safety Function', 'BACKGROUND'),
            ('Licensee Event Report: No Loss of Safety Function', 'HIGH'),
            ('OMB Supporting Statement for Notices of Enforcement Discretion', 'BACKGROUND'),
            ('Order Granting Motion to Exceed the Page Limit for New Contention', 'BACKGROUND'),
            ('Brief in Support of Appeal of Memorandum and Order (Ruling on Hearing Requests)', 'MEDIUM'),
            ('Memorandum and Order (Denying Motion for Summary Disposition and Establishing New Schedule)', 'HIGH'),
        ]
        for title, priority in cases:
            with self.subTest(title=title):
                self.assertEqual(classify_title(title)['priority'], priority)

    def test_themes_do_not_stack_rank(self):
        original = classify_title('Request for an Exemption')
        expanded = classify_title('Request for an Exemption: Risk-Informed, Performance-Based Licensing, Spent Fuel, Decommissioning Trust Fund')
        self.assertEqual(original['rank_score'], expanded['rank_score'])
        self.assertGreater(len(expanded['themes']), len(original['themes']))

    def test_non_proprietary_negation_and_explicit_redaction(self):
        for title in ('Non-Proprietary Report', 'Nonproprietary Report', 'Not Proprietary Report'):
            self.assertNotIn('Information access', classify_title(title)['themes'])
        self.assertIn('Information access', classify_title('Redacted Non-Proprietary Report')['themes'])
        self.assertIn('Information access', classify_title('Proprietary Report')['themes'])

    def test_selection_prefers_event_over_reference(self):
        titles = [
            'IP 92702 Follow-Up on Traditional Enforcement Actions Including Confirmatory Action Letters and Orders',
            'Perry Licensee Event Report: Generator Inoperable due to Failed Cable',
            'Notice of Violation and Proposed Civil Penalty',
        ]
        docs = [{'DocumentTitle': title, 'AccessionNumber': f'ML26001A00{i}'} for i, title in enumerate(titles)]
        topics = _top_topics_no_repeats(docs, 2)
        self.assertEqual([t['best_doc']['DocumentTitle'] for t in topics], titles[1:])
        for t in topics:
            score, hits = score_title(t['best_doc']['DocumentTitle'])
            self.assertEqual(t['best_score'], score + doc_bonus(t['best_doc']['DocumentTitle']))
            self.assertEqual(t['best_hits'], hits)

    def test_representative_and_related_membership(self):
        docs = [
            {'DocumentTitle': 'Application for license transfer EPID L-2026-LLM-0001', 'AccessionNumber': 'ML26001A001'},
            {'DocumentTitle': 'Order Approving Transfer of Licenses EPID L-2026-LLM-0001', 'AccessionNumber': 'ML26001A002'},
            {'DocumentTitle': 'Cover letter EPID L-2026-LLM-0001', 'AccessionNumber': 'ML26001A003'},
            {'DocumentTitle': 'Notice of Violation', 'AccessionNumber': 'ML26001A004'},
        ]
        topics = _top_topics_no_repeats(docs, 2)
        grouped = next(t for t in topics if len(t['accessions']) == 3)
        self.assertEqual(grouped['best_doc']['AccessionNumber'], 'ML26001A002')
        self.assertEqual(grouped['accessions'], ['ML26001A001', 'ML26001A002', 'ML26001A003'])
        self.assertEqual(topics, _top_topics_no_repeats(list(reversed(docs)), 2))
        self.assertEqual(_top_topics_no_repeats(docs, 0), [])

    def test_export_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            p = write_run_artifact(export_dir=directory, tool_name='adams-for-projects', version='0.2.0', mode='recent', requested_date='2026-10-11', used_date='2026-10-09', max_pages=10, page_size=100, fallback_days=7, docs_total_for_used_date=127, topics=[])
            artifact = json.loads(p.read_text())
            self.assertEqual(artifact['review_metadata']['selection_method'], 'review_priority')
            self.assertEqual(artifact['review_metadata']['assessed_at_utc'], artifact['generated_at'])
            self.assertFalse(artifact['interpretation']['priority_is_official'])
            self.assertEqual(artifact['interpretation']['score_method'], 'legacy_title_keyword_heuristic')
            self.assertEqual(artifact, json.loads((p.parent/'latest.run.json').read_text()))


if __name__ == '__main__':
    unittest.main()
