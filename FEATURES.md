# CliniGuide AI Features

This document describes the features currently implemented in this project based on the code in `main.py` and `api.py`.

## Product Overview

CliniGuide AI is a medical-assistance application with two delivery surfaces:

- A Streamlit web app for condition review, prescription image upload, and nearby pharmacy lookup.
- A FastAPI service for prescription extraction from uploaded images.

The app is designed as a decision-support tool, not a replacement for licensed medical care.

## Streamlit Application Features

### 1. Condition Intake

Users can enter a free-text description of symptoms, concerns, or a known condition.

Examples supported by the UI:

- Symptom descriptions such as fever, cough, sore throat, and body aches.
- A diagnosis or condition name for structured guidance.

### 2. AI Medical Guidance

When a condition is entered, the app sends a structured prompt to a Gemini model and returns a formatted response with:

- A plain-language explanation of the condition.
- Prescription treatment suggestions when commonly used.
- Over-the-counter options when relevant.
- Home-care or self-care suggestions when relevant.
- Precautions and escalation guidance for urgent symptoms.

The prompt is intentionally structured to keep outputs clinically organized and conservative.

### 3. Optional Web-Backed Medical References

The Streamlit app can enrich the model prompt with content retrieved from trusted medical sites using DuckDuckGo search.

Current retrieval behavior:

- Searches are limited to:
  - `mayoclinic.org`
  - `medlineplus.gov`
  - `who.int`
- Up to 2 search results are processed.
- Page content is scraped and truncated before being added to the model prompt.
- Retrieved source URLs are shown in the UI when citations are used.

If search fails or returns no usable content, the app continues with model-only guidance and informs the user.

### 4. Prescription Image Upload

Users can upload a prescription image from the Streamlit interface.

Supported file types:

- `png`
- `jpg`
- `jpeg`
- `webp`

Uploaded images are passed to the extraction pipeline implemented in `api.py`.

### 5. Prescription Extraction Summary

After a successful upload, the app displays structured medicine extraction results in a table with these fields:

- Medicine
- Confidence
- Dosage
- Frequency
- Duration
- Instructions
- Red Flags

This gives the user a normalized summary of the medicines detected in the uploaded prescription.

### 6. Prescription Verification Guidance

The OCR workflow includes safety-oriented output sections:

- Verification guidance
- Model warnings
- Quality gate
- Raw extracted text (optional)

These sections are intended to reduce over-trust in OCR and keep manual verification central to the workflow.

### 7. Raw OCR Display Toggle

The sidebar includes a control to show or hide raw extracted text from the prescription pipeline.

This is useful for:

- Manual comparison with the image.
- Debugging extraction quality.
- Reviewing ambiguous handwriting output.

### 8. Nearby Pharmacy Search

Users can enter a location and request nearby pharmacy results from the same interface.

Current behavior:

- Search is performed using DuckDuckGo text search.
- The app requests up to 6 result links.
- Results are displayed as clickable name-and-link entries.

If no location is entered, the UI prompts the user to provide one. If the lookup fails, the UI shows the failure without crashing the app.

### 9. Sidebar Workspace Controls

The Streamlit app includes runtime controls in the sidebar for:

- Theme selection
- Enabling or disabling web citations
- Enabling or disabling nearby pharmacy search
- Showing or hiding raw OCR text
- Selecting the Gemini model used for guidance

These controls allow non-code configuration during use.

### 10. Theme Support

The UI supports two visual themes:

- Light
- Dark

The app injects a custom CSS system with:

- Custom color variables
- Hero panel styling
- Responsive cards
- Styled tables
- Styled alerts
- Mobile-friendly layout adjustments

### 11. Responsive Dashboard Layout

The Streamlit frontend uses a two-column layout for the main workflow:

- Left column: condition input and location
- Right column: prescription upload

Results are then rendered in stacked cards below the form area.

### 12. Session-Aware Chat Reuse

The app stores a Gemini chat object in Streamlit session state and reuses it unless the selected model changes.

This provides:

- Lower overhead than rebuilding a chat each response.
- Per-session continuity tied to the chosen model.

### 13. Model Discovery and Selection

The app attempts to list available Gemini models dynamically and filters them to models that support `generateContent`.

It also includes a fallback preference order for common models such as:

- `gemini-flash-latest`
- `gemini-1.5-flash`
- `gemini-2.0-flash`
- `gemini-2.0-flash-lite`
- `gemini-1.5-pro`

If no live model list is available, the app still falls back to a default model name.

### 14. Retry Logic for Transient Gemini Failures

The app wraps `generate_content` calls with retry behavior for transient Google API failures, specifically:

- `ServiceUnavailable`
- `DeadlineExceeded`

This improves resilience for temporary service interruptions.

### 15. API Key Validation

The Streamlit app validates the presence of `GOOGLE_API_KEY` at startup.

If the key is missing:

- The UI shows an error message.
- App execution stops early.

This prevents partially broken execution.

## Prescription Extraction Engine Features

The prescription extraction pipeline is implemented in `api.py` and is used by both the Streamlit app and the FastAPI service.

### 16. Image Validation and Loading

The extraction pipeline:

- Verifies that the uploaded content is an image when a content type is provided.
- Loads the image with Pillow.
- Converts the image to RGB before sending it to Gemini.

Invalid files raise a controlled error.

### 17. Gemini Vision-Based Prescription Parsing

The pipeline sends the image and a structured extraction prompt to Gemini and requests JSON output.

The prompt instructs the model to extract:

- `raw_text`
- `medicines`
- `warnings`

For each medicine, the expected fields are:

- `name`
- `dosage`
- `frequency`
- `duration`
- `instructions`
- `confidence`
- `red_flags`

### 18. OCR Model Fallback Sequence

The OCR subsystem attempts multiple Gemini model names in order until one succeeds.

Candidate sources include:

- `OCR_GEMINI_MODEL` from environment variables
- `GEMINI_MODEL` from environment variables
- Built-in fallback model names

It skips to the next candidate when the current model is:

- unavailable
- not supported for the request
- quota-limited

### 19. JSON Cleanup and Recovery

The OCR pipeline includes logic to recover valid JSON from imperfect model responses by:

- Stripping Markdown code fences.
- Attempting direct JSON parsing.
- Falling back to extracting the first JSON object block from the response text.

This makes the extraction flow more tolerant of model formatting drift.

### 20. Text Normalization

The extracted raw text is normalized to clean whitespace and newline formatting before being returned.

### 21. Confidence Normalization

Medicine confidence values are normalized into a fixed set:

- `high`
- `medium`
- `low`

Unexpected values are downgraded to `low`.

### 22. Red-Flag Normalization

The extraction pipeline normalizes `red_flags` into a clean list of non-empty strings.

### 23. Post-Extraction Medicine Validation

Each extracted medicine is validated after model generation.

Current validation checks include:

- Very short medicine names
- Unexpected characters in medicine names
- Suspected non-medicine text
- Multiple missing treatment fields

Validation can downgrade confidence and append additional red flags.

### 24. Quality Gate Classification

The pipeline generates a quality gate message to describe extraction risk:

- High risk when no medicines are extracted confidently
- High risk when low-confidence medicines are present
- Medium risk when warnings or red flags remain
- Lower risk when no major issues are detected

Even the lowest-risk state still requires manual verification.

### 25. Structured Sectioned Output

The OCR system returns a `sectioned_output` payload containing:

- `prescribed_medicines`
- `usage_guidance`
- `extraction_warnings`
- `quality_gate`
- `raw_parsed_text`

This is used by the Streamlit UI to render safety-focused review sections.

## FastAPI Service Features

### 26. Prescription Extraction Endpoint

The project exposes a FastAPI endpoint:

- `POST /prescription`

Behavior:

- Accepts an uploaded image file.
- Validates file type.
- Runs the same extraction logic used by the Streamlit app.
- Returns a structured `PrescriptionResponse`.

### 27. Health Check Endpoint

The project exposes a basic health endpoint:

- `GET /health`

Response shape:

- service status
- service name

### 28. Typed API Response Models

The FastAPI layer uses Pydantic models for:

- individual extracted medicines
- the overall prescription response

This provides explicit response structure and validation.

### 29. Graceful Optional FastAPI Import

The code handles missing FastAPI dependencies safely by guarding imports.

If FastAPI is unavailable:

- API app creation is skipped
- Streamlit-side extraction logic can still exist independently

## Safety and Failure-Handling Features

### 30. Conservative Medical Positioning

The guidance prompt explicitly instructs the model to:

- remain clinically grounded
- avoid overconfident treatment framing
- remind the user to seek licensed care for emergencies, severe symptoms, or medication decisions

### 31. Non-Crash Fallbacks for External Dependencies

The app includes graceful handling for several failure modes:

- search engine failures
- unavailable web citations
- OCR extraction errors
- invalid uploaded files
- missing Gemini API key
- unavailable or quota-limited Gemini models
- pharmacy lookup failures

### 32. Caching for Expensive Operations

The app uses Streamlit caching for:

- model listing
- medical web retrieval
- nearby pharmacy search

This reduces repeat network and processing overhead during app usage.

## Configuration Features

### 33. Environment Variable Support

The project reads configuration from environment variables, including:

- `GOOGLE_API_KEY`
- `GEMINI_MODEL`
- `OCR_GEMINI_MODEL`

### 34. Default Model Preference Logic

If `GEMINI_MODEL` is set, the app attempts to use it first. If not, it selects from a built-in fallback order.

The OCR pipeline follows a similar fallback pattern, with a separate override option through `OCR_GEMINI_MODEL`.

## Important Current Limitations

These are not missing from this document; they are the current behavior of the implementation.

- Medical citations are retrieved by web search and page scraping, not from a medical database or formal evidence pipeline.
- Nearby pharmacy lookup is search-result based, not map-coordinate based.
- A `geocode_place()` helper exists in `main.py`, but it is not currently wired into the pharmacy search flow.
- Prescription extraction depends on Gemini multimodal model availability and quota.
- The system provides support and structure, but it does not verify prescriptions against a drug database.

## Primary User Flows

### Condition Review Flow

1. User enters a condition or symptoms.
2. User optionally leaves web citations enabled.
3. App retrieves medical content from trusted public sources when available.
4. Gemini generates structured medical guidance.
5. Sources are shown if retrieval succeeded.

### Prescription Review Flow

1. User uploads a prescription image.
2. The image is validated and processed by Gemini.
3. Medicines are normalized and validated.
4. Results are shown in a structured table.
5. Warnings, quality gate, and verification guidance are displayed.

### Combined Workflow

1. User enters symptoms.
2. User uploads a prescription.
3. User optionally enters a location.
4. App generates condition guidance, prescription extraction results, and nearby pharmacy links in one session.

