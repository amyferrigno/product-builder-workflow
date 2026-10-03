# bad-prd

A run-folder-shaped fixture (`01-extraction.json`, `02-problem.md`, `prd.md`) copied from `clean-meeting` and then broken on purpose. Everything else in the PRD is valid, so `scripts/validate_prd.py` names exactly two problems:

1. Section 3 contains an unsupported number (`9137`): it appears nowhere in `01-extraction.json`.
2. `REQ-003` in section 12 has no Given/When/Then acceptance criteria.

Expected: `validate_prd.py` exits 1 and prints `Unsupported number '9137' in section 3` and `Requirement REQ-003: acceptance criteria missing: Given, When, Then`.
