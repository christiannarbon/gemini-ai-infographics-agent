def _friendly_error_message(message: str) -> str:
    normalized = message.lower()
    if "project_number" in normalized or "resource_id" in normalized:
        return "A placeholder remains in the Agent Runtime resource name. Set AGENT_RUNTIME_RESOURCE_NAME to the actual projects/.../reasoningEngines/... value and redeploy Cloud Run."
    if "publisher model" in normalized or (
        "model" in normalized and "404" in normalized
    ):
        return "Gemini model not found. Check the model ID and GOOGLE_CLOUD_LOCATION=global settings."
    if (
        "signed url" in normalized
        or "signblob" in normalized
        or "serviceaccounttokencreator" in normalized
    ):
        return "Insufficient permissions to generate the signed URL for the image. Please re-run scripts/runtime-iam-config.sh."
    if "permission" in normalized or "403" in normalized or "denied" in normalized:
        return "Insufficient Google Cloud permissions. Check IAM configurations for Cloud Run, Agent Runtime, and Cloud Storage."
    if (
        "agent runtime returned no workflow response" in normalized
        or "assertionerror" in normalized
    ):
        return "Agent Runtime did not return the expected response format. Check the Runtime logs."
    if "gcs_bucket is required" in normalized:
        return "The destination bucket for generated images is not set. Set GCS_BUCKET and redeploy Runtime."
    if "exceeds" in normalized and "bytes" in normalized:
        return "Retrieving stopped because the article body is too large. Try another article URL."
    if "url" in normalized or "fetch" in normalized or "article" in normalized:
        return "Could not retrieve the article body. Try a publicly accessible article URL, or another URL."
    return message


def display_error(exc: Exception) -> str:
    raw_message = str(exc).strip()
    technical_detail = raw_message or f"{type(exc).__name__}: {exc!r}"
    friendly_message = _friendly_error_message(technical_detail)
    if friendly_message == technical_detail:
        return friendly_message
    return f"{friendly_message}\nTechnical Details: {technical_detail}"
