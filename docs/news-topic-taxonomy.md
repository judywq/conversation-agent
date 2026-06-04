# News Topic Taxonomy

This taxonomy is for the student-facing news learning flow. Students first choose
a main category. They may then choose a subtopic, but the subtopic is optional.

Miniflux should remain responsible for RSS subscription, fetching, deduplication,
and updates. The Django application should own this learning taxonomy and use it
to filter or label articles retrieved from Miniflux.

## Selection Flow

```text
Main category required
Subtopic optional
Recent news articles selected from Miniflux/Django cache
Learning activity generated from selected article context
```

If a student only chooses a main category, the system should return recent news
from that category. If the student also chooses a subtopic, the system should
prefer articles matching that narrower topic.

## Main Categories and Subtopics

### 1. Society & Lifestyle

Relatable daily-life and social topics that are suitable for lower-intermediate
learners and opinion-based discussion.

- Remote work
- Social media habits
- Online friendships
- Dating apps
- Food delivery culture
- Influencer culture
- Work-life balance
- Consumer habits
- Urban life
- Family and relationships

### 2. Technology & AI

Technology, artificial intelligence, and digital society topics. This is one of
the strongest academic categories for news-based learning.

- AI replacing jobs
- Deepfakes
- AI teachers
- Self-driving cars
- Privacy vs convenience
- VR classrooms
- Humanoid robots
- Social media algorithms
- AI companions
- Brain-computer interfaces

### 3. Education & Learning

Education topics that Japanese university students can connect to their own
school and learning experiences.

- University attendance policies
- English education in Japan
- Homework effectiveness
- Study abroad
- AI use in homework
- Standardized testing
- Online learning
- Gap years
- Future universities
- Student motivation

### 4. Environment & Sustainability

Environmental issues, climate-related policy, energy, and sustainable consumer
choices.

- Plastic bans
- Nuclear energy
- Climate anxiety
- Carbon taxes
- Electric vehicles
- Recycling effectiveness
- Overtourism
- Sustainable fashion
- Fast fashion
- Food waste

### 5. Business, Work & Economy

Business, labor, money, and economic topics. This is especially useful for
economics and business students.

- Universal basic income
- Minimum wage
- Inflation
- Cashless society
- Cryptocurrency
- Gig economy
- Work automation
- Tourism economy
- 4-day work week
- Startup culture

### 6. Health & Psychology

Physical health, mental health, behavior, and psychology topics that connect to
students' lived experiences.

- Mental health in universities
- Burnout
- Smartphone addiction
- Exercise habits
- Sleep deprivation
- Stress management
- Loneliness
- Therapy culture
- Diet trends
- Climate anxiety

### 7. Culture & Media

Culture, entertainment, identity, and media topics. This category combines
popular culture and media consumption because many articles naturally overlap.

- Streaming services
- Celebrity scandals
- Video games
- VTubers
- Parasocial relationships
- Sports events
- Music fandoms
- Reality TV
- Anime influence
- Cultural stereotypes

### 8. Global Issues & Ethics

Global social issues, ethical debates, and controversial topics. This category
is useful for higher-level discussion, debate, and writing tasks.

- Immigration
- Globalization
- Cultural appropriation
- Language loss
- International marriages
- Death penalty
- Animal testing
- Surveillance
- Freedom of speech
- Wealth inequality
- Genetic engineering
- AI consciousness
- Robot rights
- Digital immortality
- Human enhancement

## Classification Rules

Some topics naturally overlap. Use these rules to keep the taxonomy consistent.

1. Use the article's main angle, not just its keywords.
2. Put "smartphone addiction" under Health & Psychology when the focus is user
   behavior or mental health.
3. Put "smartphone addiction" under Technology & AI only when the focus is app
   design, recommendation algorithms, or platform responsibility.
4. Put "AI replacing jobs" under Technology & AI when the focus is AI capability.
5. Put "work automation" under Business, Work & Economy when the focus is jobs,
   wages, companies, or labor markets.
6. Put "fast fashion" and "sustainable fashion" under Environment &
   Sustainability unless the article is mainly about trends or identity.
7. Treat future-oriented topics as subtopics or tags, not as a separate main
   category.
8. Allow one article to have multiple subtopic labels when needed.

## Suggested Django Representation

```text
NewsCategory
- name
- description
- display_order

NewsSubtopic
- category
- name
- keywords
- display_order

NewsArticle
- title
- summary
- url
- source
- published_at
- category
- subtopics
```

Subtopics should behave like labels. A single article may match more than one
subtopic, especially when technology, business, health, and ethics overlap.
