## Change under review
$change_summary

## Findings from deterministic analysis
$findings

## Evidence
$evidence

## Task
Write exactly one entry in "finding_notes" for each finding above, using its exact id ($finding_ids).
Then add at most $max_risks entries to "additional_risks", only for problems the findings above do not already cover. An empty list is a good answer when nothing else is clearly supported by the evidence.
Allowed evidence IDs: $evidence_ids
Allowed categories for additional risks: $categories
Finish with "overall_assessment": two sentences on the riskiest aspect of this change.
