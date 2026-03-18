---
name: Jumio data vs documentation discrepancies
description: Known discrepancies between the KYC dataset values and official Jumio documentation labels
type: reference
---

# Dataset vs Jumio Docs Discrepancies

## 1. liveness_UNDETERMINED (naming bug)
- **In data:** `liveness_UNDETERMINED` (lowercase prefix)
- **Per docs:** `LIVENESS_UNDETERMINED` (all caps)
- Affects: 965 rows in liveness_decision_details, 278 rows in usability_decision_details
- Indicates a data pipeline bug where the check name is prepended in lowercase

## 2. liveness_UNDETERMINED in usability_decision_details (misrouting bug)
- 278 rows have `liveness_UNDETERMINED` in `usability_decision_details`
- This is NOT a valid usability label per docs
- These rows have usability_decision=WARNING and liveness_decision=REJECTED
- The selfie usability failure reason is being written into the ID usability column — pipeline bug

## 3. Watchlist WARNING = ALERT
- Per docs, Watchlist WARNING label is ALERT meaning user was found on a sanctions/PEP watchlist
- 69 users triggered this — all received overall PASSED
- No separate details column in our dataset to confirm ALERT label

## 4. Non-standard decision_label values
- `OK` (8 rows) and `APPROVED` (4 rows) in decision_label — should be PASSED
- `PASSES` (3 rows) in image_checks, extraction, data_checks decisions — typo for PASSED
- `PASSED` (1 row) in usability_decision_details — should be OK
