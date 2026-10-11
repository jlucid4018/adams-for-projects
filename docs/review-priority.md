# Review priority, version 2.0.0

The collector now ranks reading priority using document context in its title. This is independent editorial triage, not an NRC severity level or a determination of safety, wrongdoing, or current operating conditions. Posting dates may differ from the dates discussed in a record. Full documents still need to be opened.

`review.py` is a dependency-free, deterministic implementation. Each topic has `review.version`, `basis`, `priority`, `document_type`, `reasons`, `themes`, and `rank_score`. One matching contextual rule supplies the rank. Themes are labels and never add points; repeating related terminology cannot inflate priority. The rank is an ordering aid, not a measured risk or calibrated probability.

- **High** (rank 70–96): named event reports, specific equipment/operating conditions, actual enforcement matters, substantive decisions, final environmental findings, and adopted regulatory changes.
- **Medium** (rank 40–68): applications, exemptions and enforcement-related requests, financial status reports, inspections without stated findings, technical reviews, public participation, and substantive follow-up.
- **Background** (rank below 40): routine notices, scheduling, procurement, procedures, forms, editorial corrections, and titles with insufficient context.

Document role takes precedence over terminology quoted in a subject. Draft findings are distinct from final findings; an application for an order is distinct from an issued order. Generic `order` and `Non-Proprietary` do not create enforcement or withholding claims. A periodic trust-fund report does not imply a shortfall. Substantive notices and administrative enforcement orders remain eligible; the previous broad noise filter is no longer used in selection.

All existing `score`, `severity`, `hits`, and `angle` fields remain as legacy comparison data from the unchanged scorer. They do not drive current representatives, ordering, or explanations. `interpretation` identifies both methods. `review_metadata.selection_method` is `review_priority` for new collector runs; downstream reassessments of old saved shortlists must identify their legacy selection origin instead. Existing artifacts must not be rewritten to imply this classifier originally selected them.

Related topics keep all accession memberships before the shortlist is truncated. This preserves source links within the existing EPID/NEI/project grouping; it does not claim that every document in a family is equivalent.

## Validation and limitations

Run `PYTHONPATH=src python -m unittest discover -s tests -v` after installing the package dependencies. The fixture includes 29 real retained records, contextual counterexamples, representative/selection tests, preservation of legacy calculations, theme non-stacking, and export method metadata.

The initial replay assessed all 799 retained topic appearances from 163 dated snapshots. Those records were selected by the old method. This is a regression corpus, not an unbiased sample, and cannot establish missed-record rates or precision/recall over the complete NRC intake. New runs classify the full retrieved metadata before selecting topics, but only their selected topics appear in the public feed. Unknown titles remain explicitly unclassified rather than receiving invented explanations. Further changes should retain the original source records and bump the review version.
