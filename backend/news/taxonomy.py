from __future__ import annotations

# ruff: noqa: E501
from dataclasses import dataclass

TAXONOMY_VERSION = "2026-06-03"


@dataclass(frozen=True)
class NewsSubtopic:
    slug: str
    name: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class NewsCategory:
    slug: str
    name: str
    description: str
    subtopics: tuple[NewsSubtopic, ...]


NEWS_TAXONOMY: tuple[NewsCategory, ...] = (
    NewsCategory(
        slug="society-lifestyle",
        name="Society & Lifestyle",
        description="Daily-life and social topics for relatable opinion-based discussion.",
        subtopics=(
            NewsSubtopic("remote-work", "Remote work", ("remote work", "work from home", "hybrid work")),
            NewsSubtopic("social-media-habits", "Social media habits", ("social media", "online habits")),
            NewsSubtopic("online-friendships", "Online friendships", ("online friends", "digital friendship")),
            NewsSubtopic("dating-apps", "Dating apps", ("dating app", "online dating")),
            NewsSubtopic("food-delivery-culture", "Food delivery culture", ("food delivery", "delivery app")),
            NewsSubtopic("influencer-culture", "Influencer culture", ("influencer", "creator economy")),
            NewsSubtopic("work-life-balance", "Work-life balance", ("work-life balance", "overwork")),
            NewsSubtopic("consumer-habits", "Consumer habits", ("consumer behavior", "shopping habits")),
            NewsSubtopic("urban-life", "Urban life", ("urban life", "city life")),
            NewsSubtopic("family-relationships", "Family and relationships", ("family", "relationships")),
        ),
    ),
    NewsCategory(
        slug="technology-ai",
        name="Technology & AI",
        description="Technology, artificial intelligence, and digital society topics.",
        subtopics=(
            NewsSubtopic("ai-replacing-jobs", "AI replacing jobs", ("AI jobs", "automation", "workforce")),
            NewsSubtopic("deepfakes", "Deepfakes", ("deepfake", "synthetic media", "fake video")),
            NewsSubtopic("ai-teachers", "AI teachers", ("AI tutor", "AI classroom", "AI teacher")),
            NewsSubtopic("self-driving-cars", "Self-driving cars", ("self-driving", "autonomous vehicle")),
            NewsSubtopic("privacy-convenience", "Privacy vs convenience", ("privacy", "convenience", "data")),
            NewsSubtopic("vr-classrooms", "VR classrooms", ("VR classroom", "virtual reality education")),
            NewsSubtopic("humanoid-robots", "Humanoid robots", ("humanoid robot", "robotics")),
            NewsSubtopic("social-media-algorithms", "Social media algorithms", ("algorithm", "recommendation")),
            NewsSubtopic("ai-companions", "AI companions", ("AI companion", "chatbot companion")),
            NewsSubtopic("brain-computer-interfaces", "Brain-computer interfaces", ("brain-computer", "neural interface")),
        ),
    ),
    NewsCategory(
        slug="education-learning",
        name="Education & Learning",
        description="School, university, and learning topics connected to student experience.",
        subtopics=(
            NewsSubtopic("attendance-policies", "University attendance policies", ("attendance policy", "university attendance")),
            NewsSubtopic("english-education-japan", "English education in Japan", ("English education", "Japan")),
            NewsSubtopic("homework-effectiveness", "Homework effectiveness", ("homework", "assignment")),
            NewsSubtopic("study-abroad", "Study abroad", ("study abroad", "international student")),
            NewsSubtopic("ai-homework", "AI use in homework", ("AI homework", "ChatGPT homework", "academic integrity")),
            NewsSubtopic("standardized-testing", "Standardized testing", ("standardized test", "exam")),
            NewsSubtopic("online-learning", "Online learning", ("online learning", "remote learning")),
            NewsSubtopic("gap-years", "Gap years", ("gap year", "year off")),
            NewsSubtopic("future-universities", "Future universities", ("future university", "higher education future")),
            NewsSubtopic("student-motivation", "Student motivation", ("student motivation", "learning motivation")),
        ),
    ),
    NewsCategory(
        slug="environment-sustainability",
        name="Environment & Sustainability",
        description="Climate, energy, environmental policy, and sustainable consumption.",
        subtopics=(
            NewsSubtopic("plastic-bans", "Plastic bans", ("plastic ban", "single-use plastic")),
            NewsSubtopic("nuclear-energy", "Nuclear energy", ("nuclear energy", "nuclear power")),
            NewsSubtopic("climate-anxiety", "Climate anxiety", ("climate anxiety", "eco anxiety")),
            NewsSubtopic("carbon-taxes", "Carbon taxes", ("carbon tax", "carbon pricing")),
            NewsSubtopic("electric-vehicles", "Electric vehicles", ("electric vehicle", "EV")),
            NewsSubtopic("recycling-effectiveness", "Recycling effectiveness", ("recycling", "waste management")),
            NewsSubtopic("overtourism", "Overtourism", ("overtourism", "tourism impact")),
            NewsSubtopic("sustainable-fashion", "Sustainable fashion", ("sustainable fashion", "ethical fashion")),
            NewsSubtopic("fast-fashion", "Fast fashion", ("fast fashion", "clothing waste")),
            NewsSubtopic("food-waste", "Food waste", ("food waste", "food loss")),
        ),
    ),
    NewsCategory(
        slug="business-work-economy",
        name="Business, Work & Economy",
        description="Business, labor, money, and economic topics.",
        subtopics=(
            NewsSubtopic("universal-basic-income", "Universal basic income", ("universal basic income", "UBI")),
            NewsSubtopic("minimum-wage", "Minimum wage", ("minimum wage", "living wage")),
            NewsSubtopic("inflation", "Inflation", ("inflation", "cost of living")),
            NewsSubtopic("cashless-society", "Cashless society", ("cashless", "digital payment")),
            NewsSubtopic("cryptocurrency", "Cryptocurrency", ("cryptocurrency", "bitcoin", "crypto")),
            NewsSubtopic("gig-economy", "Gig economy", ("gig economy", "platform work")),
            NewsSubtopic("work-automation", "Work automation", ("work automation", "automated jobs")),
            NewsSubtopic("tourism-economy", "Tourism economy", ("tourism economy", "travel industry")),
            NewsSubtopic("four-day-work-week", "4-day work week", ("4-day work week", "four-day work week")),
            NewsSubtopic("startup-culture", "Startup culture", ("startup", "entrepreneurship")),
        ),
    ),
    NewsCategory(
        slug="health-psychology",
        name="Health & Psychology",
        description="Physical health, mental health, behavior, and psychology topics.",
        subtopics=(
            NewsSubtopic("mental-health-universities", "Mental health in universities", ("student mental health", "university mental health")),
            NewsSubtopic("burnout", "Burnout", ("burnout", "stress", "overwork")),
            NewsSubtopic("smartphone-addiction", "Smartphone addiction", ("smartphone addiction", "screen time")),
            NewsSubtopic("exercise-habits", "Exercise habits", ("exercise habit", "physical activity")),
            NewsSubtopic("sleep-deprivation", "Sleep deprivation", ("sleep deprivation", "insomnia", "sleep disorder")),
            NewsSubtopic("stress-management", "Stress management", ("stress management", "coping stress")),
            NewsSubtopic("loneliness", "Loneliness", ("loneliness", "social isolation")),
            NewsSubtopic("therapy-culture", "Therapy culture", ("therapy", "counseling")),
            NewsSubtopic("diet-trends", "Diet trends", ("diet trend", "nutrition trend")),
            NewsSubtopic("climate-anxiety", "Climate anxiety", ("climate anxiety", "eco anxiety")),
        ),
    ),
    NewsCategory(
        slug="culture-media",
        name="Culture & Media",
        description="Culture, entertainment, identity, and media consumption topics.",
        subtopics=(
            NewsSubtopic("streaming-services", "Streaming services", ("streaming service", "Netflix", "video streaming")),
            NewsSubtopic("celebrity-scandals", "Celebrity scandals", ("celebrity scandal", "celebrity news")),
            NewsSubtopic("video-games", "Video games", ("video game", "gaming")),
            NewsSubtopic("vtubers", "VTubers", ("VTuber", "virtual YouTuber")),
            NewsSubtopic("parasocial-relationships", "Parasocial relationships", ("parasocial", "fan relationship")),
            NewsSubtopic("sports-events", "Sports events", ("sports event", "Olympics", "World Cup")),
            NewsSubtopic("music-fandoms", "Music fandoms", ("music fandom", "fan culture")),
            NewsSubtopic("reality-tv", "Reality TV", ("reality TV", "reality show")),
            NewsSubtopic("anime-influence", "Anime influence", ("anime", "Japanese animation")),
            NewsSubtopic("cultural-stereotypes", "Cultural stereotypes", ("cultural stereotype", "stereotype")),
        ),
    ),
    NewsCategory(
        slug="global-issues-ethics",
        name="Global Issues & Ethics",
        description="Global social issues, ethical debates, and controversial topics.",
        subtopics=(
            NewsSubtopic("immigration", "Immigration", ("immigration", "migrant", "refugee")),
            NewsSubtopic("globalization", "Globalization", ("globalization", "global trade")),
            NewsSubtopic("cultural-appropriation", "Cultural appropriation", ("cultural appropriation",)),
            NewsSubtopic("language-loss", "Language loss", ("language loss", "endangered language")),
            NewsSubtopic("international-marriages", "International marriages", ("international marriage", "intercultural marriage")),
            NewsSubtopic("death-penalty", "Death penalty", ("death penalty", "capital punishment")),
            NewsSubtopic("animal-testing", "Animal testing", ("animal testing", "animal research")),
            NewsSubtopic("surveillance", "Surveillance", ("surveillance", "facial recognition")),
            NewsSubtopic("freedom-of-speech", "Freedom of speech", ("freedom of speech", "free speech")),
            NewsSubtopic("wealth-inequality", "Wealth inequality", ("wealth inequality", "income inequality")),
            NewsSubtopic("genetic-engineering", "Genetic engineering", ("genetic engineering", "gene editing")),
            NewsSubtopic("ai-consciousness", "AI consciousness", ("AI consciousness", "sentient AI")),
            NewsSubtopic("robot-rights", "Robot rights", ("robot rights", "AI rights")),
            NewsSubtopic("digital-immortality", "Digital immortality", ("digital immortality", "mind uploading")),
            NewsSubtopic("human-enhancement", "Human enhancement", ("human enhancement", "biohacking")),
        ),
    ),
)

MAIN_CATEGORY_SLUGS = tuple(category.slug for category in NEWS_TAXONOMY)


def get_category(slug: str) -> NewsCategory:
    for category in NEWS_TAXONOMY:
        if category.slug == slug:
            return category
    msg = f"Unknown news category: {slug}"
    raise ValueError(msg)


def get_subtopic(category_slug: str, subtopic_slug: str) -> NewsSubtopic:
    category = get_category(category_slug)
    for subtopic in category.subtopics:
        if subtopic.slug == subtopic_slug:
            return subtopic
    msg = f"Unknown news subtopic: {category_slug}/{subtopic_slug}"
    raise ValueError(msg)


def serialize_taxonomy() -> list[dict[str, object]]:
    return [
        {
            "slug": category.slug,
            "name": category.name,
            "description": category.description,
            "subtopics": [
                {"slug": subtopic.slug, "name": subtopic.name}
                for subtopic in category.subtopics
            ],
        }
        for category in NEWS_TAXONOMY
    ]
