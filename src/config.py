"""Provider config with masked keys. No secret is ever printed."""
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def mask_key(v: str) -> str:
    if not v or len(v) <= 12:
        return "(missing)"
    return v[:6] + "..." + v[-4:]


def get_settings() -> dict:
    return {
        "provider": os.getenv("PROVIDER", "gemini,groq"),
        "gen_model": os.getenv(
            "GEN_MODEL", "gemini-3.5-flash"
        ),
        "emb_model": os.getenv("EMB_MODEL", "BAAI/bge-m3"),
        "masked_keys": {
            "GROQ": mask_key(os.getenv("GROQ_API_KEY", "")),
            "GROQ_2": mask_key(os.getenv("GROQ_API_KEY_2", "")),
            "GROQ_3": mask_key(os.getenv("GROQ_API_KEY_3", "")),
            "GROQ_4": mask_key(os.getenv("GROQ_API_KEY_4", "")),
            "GROQ_5": mask_key(os.getenv("GROQ_API_KEY_5", "")),
            "GEMINI": mask_key(os.getenv("GEMINI_API_KEY", "")),
            "GEMINI_2": mask_key(os.getenv("GEMINI_API_KEY_2", "")),
            "GEMINI_3": mask_key(os.getenv("GEMINI_API_KEY_3", "")),
            "GEMINI_4": mask_key(os.getenv("GEMINI_API_KEY_4", "")),
            "OPENROUTER": mask_key(os.getenv("OPENROUTER_API_KEY", "")),
        },
    }
