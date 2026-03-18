---
name: Jumio capability documentation
description: Decision values, labels, and dependencies for all Jumio KYC capabilities
type: reference
---

# Jumio Capabilities — Decision Labels & Dependencies

## Usability
**Dependencies:** None
**Credentials:** ID, Document, Selfie

| Decision | Label | ID | Document | Description |
|---|---|---|---|---|
| NOT_EXECUTED | TECHNICAL_ERROR | X | X | An error prevented execution. |
| NOT_EXECUTED | NOT_UPLOADED | X | X | The image was not uploaded. |
| PASSED | OK | X | X | Images are of sufficient quality to complete the transaction. |
| REJECTED | BLACK_WHITE | X | | Black and white images are not supported. |
| REJECTED | MISSING_SIGNATURE | X | | No signature detected. |
| REJECTED | MISSING_PAGE | X | | Front and back required but only one uploaded. |
| REJECTED | NOT_A_DOCUMENT | X | X | The image is not a recognized document. |
| REJECTED | BAD_QUALITY_IMAGE | X | X | Image is of insufficient quality for processing. |
| REJECTED | BLURRED | X | | Blurry image. |
| REJECTED | GLARE | X | | ID obscured by glare. |
| REJECTED | PART_OF_DOCUMENT_MISSING | X | | Part of the document excluded from the image. |
| REJECTED | PART_OF_DOCUMENT_HIDDEN | X | | Part of the ID is hidden in the uploaded image. |
| REJECTED | DAMAGED_DOCUMENT | X | | Document damaged; data or security features difficult to check. |
| REJECTED | MISSING_MANDATORY_DATAPOINTS | X | X | Key fields (First Name, Last Name, DOB) cannot be extracted. Jumio Go only. |
| REJECTED | DOCUMENT_CONTENT_NOT_SUPPORTED | | X | Document content does not conform to the type specified in the account request. |
| REJECTED | DIGITAL_COPY | X | | ID image is of a screen. |
| REJECTED | PHOTOCOPY | X | X | Document is a photocopy, not the original. |
| WARNING | UNSUPPORTED_COUNTRY | X | | Document issued by a country not configured for your organisation. |
| WARNING | UNSUPPORTED_DOCUMENT_TYPE | X | | Document type is not supported. |

## Extraction
**Dependencies:** Usability
**Credentials:** ID, Document

| Decision | Label | Description |
|---|---|---|
| PASSED | OK | All required data values were successfully extracted from the image of the ID. |
| NOT_EXECUTED | PRECONDITION_NOT_FULFILLED | Required data from another capability is not available. |
| NOT_EXECUTED | TECHNICAL_ERROR | An error prevented execution. |

Mandatory ID fields: first name, last name, date of birth, document number, expiry date.

## Image Checks
**Dependencies:** Usability, Extraction
**Credentials:** ID, Selfie, Document

| Decision | Label | ID | Document | Description |
|---|---|---|---|---|
| NOT_EXECUTED | PRECONDITION_NOT_FULFILLED | X | X | Required data from another capability is not available. |
| NOT_EXECUTED | TECHNICAL_ERROR | X | X | An error prevented execution. |
| PASSED | OK | X | X | The images of the ID document passed all image checks. |
| REJECTED | FAILED | X | | The images of the ID document did not pass all image checks. |
| REJECTED | WATERMARK | X | | The image contains a watermark (e.g., "Sample"). |
| REJECTED | OTHER_REJECTION | X | | Rejected for a reason not covered by other labels. |
| REJECTED | GHOST_IMAGE_DIFFERENT | X | | Mismatch between the ID's main image and ghost image. |
| REJECTED | PUNCHED | X | | The ID has been hole-punched. |
| REJECTED | SAMPLE | X | X | The ID is a known sample document. |
| REJECTED | FAKE | X | | The ID is fake (well-known fake, or image found on public internet). |
| REJECTED | CHIP_MISSING | X | | The ID has a missing chip. |
| REJECTED | DIGITAL_MANIPULATION | X | | The image was manipulated before being uploaded. |
| REJECTED | MISMATCH_FRONT_BACK | X | | The country on the front does not match the one on the back. |
| REJECTED | MANIPULATED_DOCUMENT | X | X | Physically superimposed photo or text. Generic label; more specific labels below usually returned instead. |
| REJECTED | MANIPULATED_DOCUMENT_PHOTO | X | | Superimposed photo or text. |
| REJECTED | MANIPULATED_DOCUMENT_DOCUMENT_NUMBER | X | | Document number shows visible manipulations. |
| REJECTED | MANIPULATED_DOCUMENT_EXPIRY | X | | Expiration date shows visible manipulations. |
| REJECTED | MANIPULATED_DOCUMENT_DOB | X | | Date of birth shows visible manipulations. |
| REJECTED | MANIPULATED_DOCUMENT_NAME | X | | Name shows visible manipulations. |
| REJECTED | MANIPULATED_DOCUMENT_ADDRESS | X | | Address shows visible manipulations. |
| REJECTED | MANIPULATED_DOCUMENT_SECURITY_CHECKS | X | | Back-office agent rejected based on security feature issues (microprint, logo, etc.). |
| REJECTED | MANIPULATED_DOCUMENT_SIGNATURE | X | | Signature shows visible manipulations. |
| REJECTED | MANIPULATED_DOCUMENT_PERSONAL_NUMBER | X | | Personal number shows visible manipulations. |
| REJECTED | MANIPULATED_DOCUMENT_PLACE_OF_BIRTH | X | | Place of birth shows visible manipulations. |
| REJECTED | MANIPULATED_DOCUMENT_GENDER | X | | Gender shows visible manipulations. |
| REJECTED | MANIPULATED_DOCUMENT_ISSUING_DATE | X | | Issue date shows visible manipulations. |
| REJECTED | LOOKUPS_HIGH_RISK_FACE | X | | Face match confirmed as fraud by Jumio internal review or Portal status. |
| WARNING | DIFFERENT_PERSON | X | | Face in the image does not match the person on the ID. |
| WARNING | REPEATED_FACE | X | | Same face seen in a previous transaction. If personal data matches → WARNING; if data differs → REJECTED with MISMATCHING_DATA_REPEATED_FACE in Data Checks. |
| WARNING | GHOST_IMAGE_QUALITY_INSUFFICIENT | X | | Ghost image too faded to confidently assess. |

## Data Checks
**Dependencies:** Usability, Extraction, Image Checks
**Credentials:** ID only

| Decision | Label | Description |
|---|---|---|
| NOT_EXECUTED | PRECONDITION_NOT_FULFILLED | Required data from another capability is not available. |
| NOT_EXECUTED | TECHNICAL_ERROR | An error prevented execution. |
| PASSED | OK | Fraud was not detected during analysis of data extracted from the ID image. |
| WARNING | DOCUMENT_EXPIRY_WITHIN_CONFIGURED_LIMIT | The document is nearing its expiration date. |
| WARNING | ID_DATA_MISMATCH_LOW_CONFIDENCE | Probable mismatch between different occurrences of a data field. |
| WARNING | ID_DATA_INVALID | Data failed validation checks (field length, formatting, character type, etc.). |
| WARNING | UNREADABLE_DATASOURCE | Data in the MRZ or barcode was not readable. |
| WARNING | LOOKUPS_MEDIUM_RISK_SAME_DOCUMENT_NUMBER | Document number matches a past transaction with different first name, last name, and DOB. |
| REJECTED | HIGH_FRAUD_RISK | High probability of fraud. |
| REJECTED | NFC_CERTIFICATE | Mismatch between microchip data and OCR-extracted data. Mobile NFC transactions only. |
| REJECTED | MISMATCHING_DATAPOINTS | Mismatch between repeating datapoints (e.g. barcode data vs printed data). |
| REJECTED | MRZ_CHECKSUM | The MRZ checksum has an unexpected value. |
| REJECTED | MISMATCHING_DATA_REPEATED_FACE | ID or selfie matches a previous transaction but personal data does not match. |
| REJECTED | CUSTOMER_FEEDBACK | ID data matches a previous transaction labeled as fraud via the feedback feature. |
| REJECTED | ID_DATA_MISMATCH | Significant mismatch between instances of a data field. |
| REJECTED | LOOKUPS_HIGH_RISK_SAME_DATA | ID document matches at least one past rejected transaction. |
| REJECTED | LOOKUPS_HIGH_RISK_SAME_FACE_MISMATCHING_DATA | ID or selfie matches a previous upload with mismatching personal data. |
| REJECTED | LOOKUPS_HIGH_RISK_DEVICE | Device data matches one or more previously rejected transactions. |
| REJECTED | LOOKUPS_HIGH_RISK_IP_ADDRESS | IP address matches one or more previously rejected transactions. |

## Liveness
**Dependencies:** Usability (selfie must PASS usability)
**Credentials:** Selfie, Facemap (optional)
**Note:** Independent of document chain.

| Decision | Label | Description |
|---|---|---|
| NOT_EXECUTED | PRECONDITION_NOT_FULFILLED | Required data from another capability is not available. |
| NOT_EXECUTED | TECHNICAL_ERROR | An error prevented execution. |
| PASSED | OK | Analysis determined that the end user was physically present during the verification process. |
| REJECTED | LIVENESS_UNDETERMINED | Liveness cannot be determined. |
| REJECTED | ID_USED_AS_SELFIE | An ID photo was used for the selfie. |
| REJECTED | MULTIPLE_PEOPLE | More than one person appears in the selfie. |
| REJECTED | DIGITAL_COPY | The selfie was captured from a screen. |
| REJECTED | PHOTOCOPY | The selfie was captured from a paper printout. |
| REJECTED | MANIPULATED | The selfie was manipulated prior to uploading (e.g. background swap). |
| REJECTED | NO_FACE_PRESENT | A face does not appear in the selfie. |
| REJECTED | FACE_NOT_FULLY_VISIBLE | The face is only partially visible in the selfie. |
| REJECTED | BLACK_WHITE | The selfie image is black and white. |
| WARNING | AGE_DIFFERENCE | Large difference between estimated selfie age and date of birth on the ID. |
| WARNING | BAD_QUALITY | The selfie is of bad quality. |

Returns: predictedAge (int), ageConfidenceRange (bracket)

## Similarity Check
**Dependencies:** Usability (face detectability on ID only)
**Credentials:** ID, Selfie
**Note:** Runs independently of document chain; only blocked if face undetectable on ID.

| Decision | Label | Description |
|---|---|---|
| NOT_EXECUTED | PRECONDITION_NOT_FULFILLED | Capability could not run because the required face could not be detected on the ID image. |
| NOT_EXECUTED | TECHNICAL_ERROR | An error prevented execution. |
| PASSED | MATCH | The faces in the images being compared belong to the same person. |
| REJECTED | NO_MATCH | The faces in the selfie and ID do not match. |
| WARNING | NOT_POSSIBLE | Similarity cannot be determined. |

## Watchlist Screening
**Dependencies (with ID):** Usability, Extraction, Image Checks
**Can run standalone** with: firstName, lastName, dateOfBirth, address.country

| Decision | Label | Description |
|---|---|---|
| NOT_EXECUTED | PRECONDITION_NOT_FULFILLED | Required data from another capability is not available. |
| NOT_EXECUTED | TECHNICAL_ERROR | An error prevented execution. |
| NOT_EXECUTED | NOT_ENOUGH_DATA | Not enough data to make a decision. |
| NOT_EXECUTED | VALIDATION_FAILED | Validation failed during processing. |
| NOT_EXECUTED | INVALID_MERCHANT_SETTINGS | Invalid merchant settings detected. |
| NOT_EXECUTED | NO_VALID_ID_CREDENTIAL | No valid ID credential provided. |
| NOT_EXECUTED | EXTRACTION_NOT_DONE | Data extraction was not performed. |
| PASSED | OK | The end user was not found on any watchlists. |
| WARNING | ALERT | The end user was found on one or more watchlists. |
