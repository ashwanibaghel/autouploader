from dataclasses import dataclass


@dataclass(frozen=True)
class MoodProfile:
    mood: str
    pexels_keywords: list[str]
    audio_keywords: list[str]


MOOD_PROFILES = {
    "student_struggle": MoodProfile(
        mood="student_struggle",
        pexels_keywords=[
            "student studying alone night",
            "worried student money problem",
            "college student library sad",
            "middle class family home sad",
            "father son emotional home",
            "poor father working family",
            "young man studying books",
            "student laptop night",
            "alone walking road night",
        ],
        audio_keywords=["sad", "emotional", "piano", "study"],
    ),
    "sad": MoodProfile(
        mood="sad",
        pexels_keywords=["sad person alone", "rain window sad", "lonely road night"],
        audio_keywords=["sad", "emotional", "piano"],
    ),
    "heartbreak": MoodProfile(
        mood="heartbreak",
        pexels_keywords=["heartbreak alone rain", "lonely person walking", "empty road night"],
        audio_keywords=["heartbreak", "sad", "piano"],
    ),
    "loneliness": MoodProfile(
        mood="loneliness",
        pexels_keywords=["alone person city night", "lonely walking", "empty room sad"],
        audio_keywords=["lonely", "sad", "ambient"],
    ),
    "motivation": MoodProfile(
        mood="motivation",
        pexels_keywords=["working hard laptop night", "runner sunrise", "city success work"],
        audio_keywords=["motivation", "uplifting", "inspiring"],
    ),
    "hope": MoodProfile(
        mood="hope",
        pexels_keywords=["sunrise hope", "person walking sunrise", "city lights hopeful"],
        audio_keywords=["hope", "inspiring", "emotional"],
    ),
    "success": MoodProfile(
        mood="success",
        pexels_keywords=["success city lights", "working laptop success", "sunrise achievement"],
        audio_keywords=["success", "uplifting", "inspiring"],
    ),
    "family": MoodProfile(
        mood="family",
        pexels_keywords=["family home emotional", "parents child home", "mother father home"],
        audio_keywords=["family", "emotional", "piano"],
    ),
    "parents": MoodProfile(
        mood="parents",
        pexels_keywords=["parents home emotional", "father working family", "mother cooking home"],
        audio_keywords=["parents", "family", "emotional"],
    ),
    "friendship": MoodProfile(
        mood="friendship",
        pexels_keywords=["friends walking emotional", "friendship city", "friends support"],
        audio_keywords=["friendship", "emotional", "hope"],
    ),
}


def analyze_mood(title: str, body: str, explicit_mood: str | None = None) -> MoodProfile:
    if explicit_mood:
        normalized = explicit_mood.lower().replace(" ", "_")
        if normalized in MOOD_PROFILES:
            return MOOD_PROFILES[normalized]

    text = f"{title} {body}".lower()
    if any(word in text for word in ["fees", "exam", "college", "student", "study", "padh"]):
        return MOOD_PROFILES["student_struggle"]
    if any(word in text for word in ["maa", "papa", "father", "mother", "parents"]):
        return MOOD_PROFILES["parents"]
    if any(word in text for word in ["breakup", "heartbreak", "dhoka"]):
        return MOOD_PROFILES["heartbreak"]
    if any(word in text for word in ["alone", "akela", "lonely", "tanha"]):
        return MOOD_PROFILES["loneliness"]
    if any(word in text for word in ["hope", "umeed", "subah", "sapna"]):
        return MOOD_PROFILES["hope"]

    return MOOD_PROFILES["sad"]
