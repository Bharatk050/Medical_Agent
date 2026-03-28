import io
import json
import os
import re
from typing import Dict, List, Optional

from dotenv import load_dotenv
from google import generativeai as genai
from PIL import Image
from pydantic import BaseModel

try:
    from fastapi import FastAPI, File, HTTPException, UploadFile
except Exception:
    FastAPI = None
    File = None
    HTTPException = None
    UploadFile = None


load_dotenv()

app = FastAPI(title="Medical Prescription Extraction API", version="2.0") if FastAPI else None
_ocr_model = None
_ocr_model_name = None


class PrescriptionDrug(BaseModel):
    name: str
    dosage: Optional[str]
    frequency: Optional[str]
    duration: Optional[str]
    instructions: Optional[str]
    confidence: str
    red_flags: List[str]


class PrescriptionResponse(BaseModel):
    status: str
    raw_text: str
    medicines: List[PrescriptionDrug]
    sectioned_output: Dict[str, str]


def _configure_gemini() -> str:
    api_key = (os.getenv("GOOGLE_API_KEY") or "").strip().strip('"').strip("'")
    if not api_key:
        raise RuntimeError("Missing GOOGLE_API_KEY for prescription extraction.")
    genai.configure(api_key=api_key)
    return api_key


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _extract_json_block(text: str) -> Dict[str, object]:
    cleaned = _strip_json_fence(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError("Model response did not contain valid JSON.")
        return json.loads(match.group(0))


def _candidate_ocr_model_names() -> List[str]:
    candidates = []
    for value in [os.getenv("OCR_GEMINI_MODEL"), os.getenv("GEMINI_MODEL")]:
        if value and value.strip():
            candidates.append(value.strip())

    candidates.extend(
        [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-flash-latest",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        ]
    )
    seen = set()
    ordered = []
    for name in candidates:
        if name not in seen:
            ordered.append(name)
            seen.add(name)
    return ordered


def get_ocr_model():
    global _ocr_model, _ocr_model_name
    if _ocr_model is not None:
        return _ocr_model

    _configure_gemini()
    _ocr_model_name = _candidate_ocr_model_names()[0]
    _ocr_model = genai.GenerativeModel(model_name=_ocr_model_name)
    return _ocr_model


def _build_prescription_prompt() -> str:
    return """
You are extracting information from a medical prescription image.
Read only what is actually visible. Do not invent medicines or dosages.
If a field is uncertain, set it to null.

Return JSON only with this exact shape:
{
  "raw_text": "full visible transcription in plain text",
  "medicines": [
    {
      "name": "string",
      "dosage": "string or null",
      "frequency": "string or null",
      "duration": "string or null",
      "instructions": "string or null",
      "confidence": "high | medium | low",
      "red_flags": ["string"]
    }
  ],
  "warnings": [
    "string"
  ]
}

Rules:
- Preserve medicine names exactly as seen when possible.
- Include only prescribed medicines, not clinic headers or patient metadata.
- If handwriting is unclear, mention that uncertainty in warnings.
- Keep raw_text concise but faithful to the document.
- Use "low" confidence when the medicine name is uncertain, looks incomplete, or key fields are hard to read.
- Add red_flags for ambiguity like "unclear handwriting", "dose missing", "frequency missing", "duration missing", "non-medicine text suspected".
""".strip()


def _run_gemini_prescription_extraction(image: Image.Image) -> Dict[str, object]:
    _configure_gemini()
    prompt = _build_prescription_prompt()
    last_error = None
    response = None

    for model_name in _candidate_ocr_model_names():
        model = genai.GenerativeModel(model_name=model_name)
        try:
            try:
                response = model.generate_content(
                    [prompt, image],
                    generation_config={
                        "temperature": 0,
                        "response_mime_type": "application/json",
                    },
                )
            except TypeError:
                response = model.generate_content(
                    [prompt, image], generation_config={"temperature": 0}
                )
            global _ocr_model, _ocr_model_name
            _ocr_model = model
            _ocr_model_name = model_name
            break
        except Exception as err:
            last_error = err
            message = str(err).lower()
            if (
                "not found" in message
                or "404" in message
                or "not supported for generatecontent" in message
                or "resourceexhausted" in message
                or "429" in message
                or "quota" in message
                or "exceeded your current quota" in message
            ):
                continue
            raise

    if response is None:
        raise RuntimeError(
            "No supported Gemini OCR model was available for this API key."
            + (f" Last error: {last_error}" if last_error else "")
        )

    payload = _extract_json_block(getattr(response, "text", "") or "")
    medicines = payload.get("medicines") or []
    warnings = payload.get("warnings") or []
    raw_text = _normalize_text(str(payload.get("raw_text") or ""))

    normalized_medicines = []
    for medicine in medicines:
        if not isinstance(medicine, dict):
            continue
        name = str(medicine.get("name") or "").strip()
        if not name:
            continue
        normalized_medicines.append(
            PrescriptionDrug(
                name=name,
                dosage=(medicine.get("dosage") or None),
                frequency=(medicine.get("frequency") or None),
                duration=(medicine.get("duration") or None),
                instructions=(medicine.get("instructions") or None),
                confidence=_normalize_confidence(medicine.get("confidence")),
                red_flags=_normalize_red_flags(medicine.get("red_flags")),
            )
        )

    return {
        "raw_text": raw_text,
        "medicines": normalized_medicines,
        "warnings": [str(item).strip() for item in warnings if str(item).strip()],
    }


def _normalize_confidence(value: object) -> str:
    confidence = str(value or "low").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        return "low"
    return confidence


def _normalize_red_flags(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _validate_medicine(medicine: PrescriptionDrug) -> PrescriptionDrug:
    red_flags = list(medicine.red_flags)
    confidence = medicine.confidence
    normalized_name = medicine.name.strip()
    lowered_name = normalized_name.lower()

    if len(normalized_name) < 3:
        red_flags.append("medicine name too short")
        confidence = "low"

    if re.search(r"[^a-z0-9\s\-\+\(\)\/\.]", lowered_name):
        red_flags.append("unexpected characters in medicine name")
        confidence = "low"

    if any(token in lowered_name for token in ["patient", "doctor", "age", "date", "rx", "diagnosis"]):
        red_flags.append("non-medicine text suspected")
        confidence = "low"

    missing_fields = sum(
        field is None or not str(field).strip()
        for field in [medicine.dosage, medicine.frequency, medicine.duration]
    )
    if missing_fields >= 2 and confidence == "high":
        confidence = "medium"
        red_flags.append("multiple treatment fields missing")
    elif missing_fields >= 2:
        red_flags.append("multiple treatment fields missing")

    return PrescriptionDrug(
        name=normalized_name,
        dosage=medicine.dosage,
        frequency=medicine.frequency,
        duration=medicine.duration,
        instructions=medicine.instructions,
        confidence=confidence,
        red_flags=sorted(set(red_flags)),
    )


def build_sectioned_output(
    medicines: List[PrescriptionDrug], raw_text: str, warnings: List[str]
) -> Dict[str, str]:
    if not medicines:
        summary = "No prescription medicines were confidently extracted."
    else:
        summary = "\n".join(
            [
                f"- {med.name} [{med.confidence}]: {med.dosage or 'N/A'}, {med.frequency or 'N/A'}, {med.duration or 'N/A'} - {med.instructions or 'Verify manually'}"
                for med in medicines
            ]
        )

    usage_guidance = (
        "1) Match each extracted medicine against the original prescription before use.\n"
        "2) Confirm dose, schedule, and duration with a pharmacist or prescribing clinician.\n"
        "3) Treat any missing or uncertain field as unverified.\n"
    )

    warning_text = (
        "\n".join(f"- {item}" for item in warnings)
        if warnings
        else "- No explicit extraction warnings were returned by the model."
    )

    return {
        "prescribed_medicines": summary,
        "usage_guidance": usage_guidance,
        "extraction_warnings": warning_text,
        "quality_gate": _build_quality_gate(medicines, warnings),
        "raw_parsed_text": raw_text,
    }


def _build_quality_gate(medicines: List[PrescriptionDrug], warnings: List[str]) -> str:
    if not medicines:
        return "High risk: no medicines were extracted with enough certainty for use without manual review."

    low_confidence = [med.name for med in medicines if med.confidence == "low"]
    flagged = [med.name for med in medicines if med.red_flags]

    if low_confidence:
        return (
            "High risk: manual review required for "
            + ", ".join(low_confidence)
            + ". Do not rely on these rows without pharmacist confirmation."
        )
    if warnings or flagged:
        return "Medium risk: extraction is usable for review, but flagged fields still need manual confirmation."
    return "Lower risk: no major extraction issues were detected, but manual verification is still required."


def extract_prescription_from_bytes(
    content: bytes, content_type: Optional[str] = None
) -> Dict[str, object]:
    if content_type and not content_type.startswith("image/"):
        raise ValueError("File must be an image")

    try:
        image = Image.open(io.BytesIO(content)).convert("RGB")
    except Exception as err:
        raise ValueError(f"Could not read image: {err}") from err

    extraction = _run_gemini_prescription_extraction(image)
    medicines = [_validate_medicine(medicine) for medicine in extraction["medicines"]]
    raw_text = extraction["raw_text"]
    warnings = extraction["warnings"]
    sectioned = build_sectioned_output(medicines, raw_text, warnings)

    return {
        "status": "success",
        "raw_text": raw_text,
        "medicines": [medicine.model_dump() for medicine in medicines],
        "sectioned_output": sectioned,
    }


if app is not None:
    @app.post("/prescription", response_model=PrescriptionResponse)
    async def extract_prescription(file: UploadFile = File(...)):
        content_type = file.content_type or ""
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=415, detail="File must be an image")

        try:
            content = await file.read()
            result = extract_prescription_from_bytes(content, content_type)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        except Exception as err:
            raise HTTPException(status_code=500, detail=f"Prescription extraction failed: {err}") from err

        return PrescriptionResponse(**result)


    @app.get("/health")
    async def health_check():
        return {"status": "ok", "service": "Medical Prescription Extraction API"}
