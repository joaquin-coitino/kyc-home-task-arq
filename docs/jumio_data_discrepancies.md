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

## 2. liveness_UNDETERMINED in usability_decision_details
- 278 rows have `liveness_UNDETERMINED` in `usability_decision_details` with `usability_decision=WARNING`
- Most likely explanation: since Usability covers both ID and Selfie credentials, this reflects the **selfie credential** failing usability with a liveness-undetermined result — not a misrouting bug
- Consistent with these rows also having `liveness_decision=REJECTED` with the same label, suggesting the selfie usability failure cascades into the Liveness capability
- Alternative explanation: an API/label change between 2023 and current docs
- To confirm: would need to check whether the API response separates usability results by credential type (ID vs Selfie)

## 3. Overall PASSED with non-PASSED individual checks

### 3a. decision_type ≠ decision_label for 1 user
- 1 row has `decision_type=PASSED` (KYC_Summary) but `decision_label=REJECTED` (KYC_Details)
- All individual checks passed except `liveness_decision=REJECTED` (LIVENESS_UNDETERMINED)
- The two datasets are inconsistent for this user — one of them is wrong

### 3b. similarity=REJECTED (NO_MATCH) but decision_type=APPROVED
- 1 user has `similarity_decision=REJECTED` with `NO_MATCH` but `decision_type=APPROVED`
- Original `decision_label=APPROVED` — this was a deliberate manual override
- A human approved someone whose selfie did not match their ID document
- Requires confirmation that this was an intentional compliance decision with proper documentation

### 3c. liveness=REJECTED (LIVENESS_UNDETERMINED) but decision_type=PASSED
- 2 users have `liveness_decision=REJECTED` with `LIVENESS_UNDETERMINED` but passed overall
- May reflect a deliberate policy to treat LIVENESS_UNDETERMINED as non-blocking (unlike hard spoofing signals like ID_USED_AS_SELFIE) — needs confirmation

### 3d. usability=NOT_EXECUTED (NOT_UPLOADED) but all checks passed and decision_type=PASSED
- 201 users have `usability_decision=NOT_EXECUTED` with detail `NOT_UPLOADED`, yet extraction, image checks, liveness, and similarity all return PASSED
- If no image was uploaded, it is unclear how downstream checks could have passed
- May indicate a different workflow (e.g. NFC, digital identity) where usability is not required for the document credential — needs clarification with Jumio

## 4. Watchlist WARNING = ALERT
- Per docs, Watchlist WARNING label is ALERT meaning user was found on a sanctions/PEP watchlist
- 69 users triggered this — all received overall PASSED
- No separate details column in our dataset to confirm ALERT label

## 5. Non-standard decision_label values
- `OK` (8 rows) and `APPROVED` (4 rows) in decision_label — should be PASSED
- `PASSES` (3 rows) in image_checks, extraction, data_checks decisions — typo for PASSED
- `PASSED` (1 row) in usability_decision_details — should be OK
