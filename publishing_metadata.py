from dataclasses import dataclass

from story_loader import Story


@dataclass(frozen=True)
class PlatformMetadata:
    title: str
    description: str
    tags: list[str]
    privacy_status: str = "public"


def build_youtube_metadata(story: Story) -> PlatformMetadata:
    title = f"{story.title} | Heart Touching Hindi Story #Shorts"
    mood_label = (story.mood or "emotional_story").replace("_", " ")
    description = (
        f"{story.title}\n\n"
        "Ek chhoti si emotional Hindi/Hinglish story, un feelings ke liye jo hum aksar bol nahi paate.\n\n"
        "If this story touched your heart, share it with someone who needs to hear it today.\n\n"
        "Follow The Ashy Notes on Instagram:\n"
        "https://www.instagram.com/theashynotes/\n"
        "@theashynotes\n\n"
        "The Ashy Notes - Stories That Stay\n\n"
        "#Shorts #TheAshyNotes #HindiStory #EmotionalStory #LifeLessons #HeartTouchingStory"
    )
    tags = [
        "Shorts",
        "The Ashy Notes",
        story.title,
        "emotional story",
        "heart touching story",
        "Hindi story",
        "Hinglish story",
        "Hindi shorts",
        "YouTube Shorts India",
        "life lesson",
        "storytelling",
        "relatable story",
        "sad story",
        "motivational story",
        "middle class story",
        "family emotion",
        "friendship story",
        "student life story",
        "viral shorts",
        mood_label,
    ]
    return PlatformMetadata(title=title, description=description, tags=tags)


def build_instagram_caption(story: Story) -> str:
    mood_label = (story.mood or "emotional story").replace("_", " ")
    hashtags = [
        "#TheAshyNotes",
        "#EmotionalStory",
        "#HindiStory",
        "#HinglishStory",
        "#LifeLessons",
        "#HeartTouchingStory",
        "#RelatableReels",
        "#ReelsIndia",
    ]
    return (
        f"{story.title}\n\n"
        "Kabhi-kabhi chhoti si kahani zindagi ki sabse badi baat samjha deti hai.\n\n"
        "If this story touched your heart, save it and share it with someone close.\n\n"
        "The Ashy Notes - Stories That Stay\n\n"
        f"{mood_label}\n"
        f"{' '.join(hashtags)}"
    )
