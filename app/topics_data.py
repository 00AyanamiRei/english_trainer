from __future__ import annotations

import random
from dataclasses import dataclass

from .database import Database


@dataclass(frozen=True)
class Topic:
    key: str
    category: str
    level: str
    title: str
    question: str


_RAW: list[tuple[str, str, str, str]] = [
    ("Повсякдення", "A2", "Your morning routine", "What do you usually do in the morning before you leave home?"),
    ("Повсякдення", "A2", "Your home", "Can you describe the place where you live? What do you like about it?"),
    ("Повсякдення", "A2", "Family", "Tell me about your family. Who are you closest to?"),
    ("Повсякдення", "A2", "Weekend plans", "What are you planning to do this weekend?"),
    ("Повсякдення", "B1", "A perfect day", "What would your perfect day look like from morning to night?"),
    ("Повсякдення", "B1", "Neighbours", "Do you know your neighbours well? How do people usually get along in your building?"),
    ("Повсякдення", "B1", "Shopping habits", "Do you prefer shopping online or in real shops? Why?"),
    ("Повсякдення", "B1", "Favourite season", "Which season do you like the most and what do you do during it?"),
    ("Повсякдення", "B2", "Time management", "How do you organise your time when you have too many things to do?"),
    ("Повсякдення", "B2", "City or village", "Would you rather live in a big city or in a small village? What are the main reasons?"),
    ("Подорожі", "A2", "Your hometown", "What is your hometown like? What should a visitor see there?"),
    ("Подорожі", "A2", "Holidays by the sea", "Do you like holidays by the sea? What do you do there?"),
    ("Подорожі", "B1", "Dream destination", "If you could travel anywhere tomorrow, where would you go and why?"),
    ("Подорожі", "B1", "A trip that went wrong", "Have you ever had a trip where something went wrong? What happened?"),
    ("Подорожі", "B1", "Public transport", "How do you usually get around your city? Is public transport good there?"),
    ("Подорожі", "B1", "Alone or in a group", "Do you prefer travelling alone or with other people? Why?"),
    ("Подорожі", "B2", "Culture shock", "Have you ever felt culture shock in a new place? What surprised you the most?"),
    ("Подорожі", "B2", "Mass tourism", "Does mass tourism do more good or more harm to popular places?"),
    ("Подорожі", "B2", "Moving abroad", "Would you consider moving to another country for a few years? What would worry you?"),
    ("Подорожі", "C1", "Slow travel", "Some people say travelling slowly is better than visiting ten cities in a week. What is your view?"),
    ("Робота та навчання", "A2", "Your studies", "What are you studying and why did you choose it?"),
    ("Робота та навчання", "A2", "A typical day", "What does a typical day at your university or work look like?"),
    ("Робота та навчання", "B1", "Dream job", "What job would you do if money was not a problem?"),
    ("Робота та навчання", "B1", "Learning English", "What is the hardest part of learning English for you?"),
    ("Робота та навчання", "B1", "Teamwork", "Do you enjoy working in a team, or do you prefer working alone?"),
    ("Робота та навчання", "B2", "Remote work", "Do you think working from home is better than working in an office?"),
    ("Робота та навчання", "B2", "Exams and stress", "How do you deal with stress before an important exam or deadline?"),
    ("Робота та навчання", "B2", "First job advice", "What advice would you give to a student looking for their first job?"),
    ("Робота та навчання", "C1", "Career and balance", "Is it realistic to have a successful career and a balanced life at the same time?"),
    ("Робота та навчання", "C1", "Future of education", "How do you think universities will change in the next twenty years?"),
    ("Технології", "A2", "Your phone", "What do you use your phone for most of the day?"),
    ("Технології", "B1", "Social media", "Which social media do you use and how much time do you spend on it?"),
    ("Технології", "B1", "Favourite app", "What is your favourite app or program and why?"),
    ("Технології", "B1", "Online learning", "Have you ever studied something online? How was it?"),
    ("Технології", "B2", "Artificial intelligence", "How do you think artificial intelligence will change everyday life?"),
    ("Технології", "B2", "Privacy online", "Do you worry about your privacy on the internet?"),
    ("Технології", "B2", "Gadgets and focus", "Do modern gadgets help us focus or distract us more?"),
    ("Технології", "B2", "What is programming", "How would you explain to a child what programming is?"),
    ("Технології", "C1", "Space exploration", "Is spending money on space exploration worth it when there are problems on Earth?"),
    ("Технології", "C1", "Technology and relationships", "Has technology made relationships between people stronger or weaker?"),
    ("Їжа та здоров'я", "A2", "Favourite food", "What is your favourite food and can you cook it yourself?"),
    ("Їжа та здоров'я", "A2", "Breakfast", "What do you usually have for breakfast?"),
    ("Їжа та здоров'я", "B1", "Cooking at home", "Do you like cooking? What is the best dish you can make?"),
    ("Їжа та здоров'я", "B1", "Eating out", "How often do you eat in restaurants or cafes? Do you have a favourite place?"),
    ("Їжа та здоров'я", "B1", "Sport and exercise", "Do you do any sport? How do you stay active?"),
    ("Їжа та здоров'я", "B1", "Sleep habits", "How many hours do you usually sleep and how do you feel in the morning?"),
    ("Їжа та здоров'я", "B2", "Healthy lifestyle", "What does a healthy lifestyle mean to you and how hard is it to keep?"),
    ("Їжа та здоров'я", "B2", "Fast food", "Should governments make unhealthy food more expensive? Why or why not?"),
    ("Їжа та здоров'я", "B2", "Traditional dishes", "What traditional dish from your country would you recommend to a foreigner?"),
    ("Їжа та здоров'я", "C1", "Mental health", "Why do you think people talk more about mental health nowadays?"),
    ("Культура та дозвілля", "A2", "Favourite music", "What kind of music do you like to listen to?"),
    ("Культура та дозвілля", "A2", "Hobbies", "What do you like doing in your free time?"),
    ("Культура та дозвілля", "B1", "Films and series", "What was the last film or series you watched? Would you recommend it?"),
    ("Культура та дозвілля", "B1", "Books", "Do you read books? What was the most interesting one?"),
    ("Культура та дозвілля", "B1", "Video games", "Do you play video games? What do you like about them?"),
    ("Культура та дозвілля", "B1", "Holidays and traditions", "What is your favourite holiday or tradition and how do you celebrate it?"),
    ("Культура та дозвілля", "B2", "Why learn languages", "Why do people learn languages even though translators are so good now?"),
    ("Культура та дозвілля", "B2", "Art and museums", "Do you enjoy museums and galleries? What makes a visit interesting?"),
    ("Культура та дозвілля", "B2", "Music and mood", "Can music change your mood or help you work? Give an example."),
    ("Культура та дозвілля", "C1", "Books versus films", "Is a book always better than the film based on it?"),
    ("Суспільство", "B1", "Volunteering", "Have you ever helped others as a volunteer? Would you like to?"),
    ("Суспільство", "B1", "Pets", "Do you have a pet, or would you like one? What are the pros and cons?"),
    ("Суспільство", "B1", "Role models", "Who is a person you admire and why?"),
    ("Суспільство", "B2", "Money and happiness", "Does more money make people happier?"),
    ("Суспільство", "B2", "Protecting the environment", "What small things can ordinary people do to protect the environment?"),
    ("Суспільство", "B2", "Generation gap", "What do older and younger generations often misunderstand about each other?"),
    ("Суспільство", "B2", "Fake news", "How do you check whether a piece of news is true?"),
    ("Суспільство", "B2", "Public speaking", "Why are so many people afraid of speaking in public?"),
    ("Суспільство", "C1", "Four-day work week", "Should the working week be shortened to four days?"),
    ("Суспільство", "C1", "Defining success", "How would you define success, and has your definition changed over time?"),
    ("Мрії та плани", "A2", "Plans for next year", "What would you like to do next year?"),
    ("Мрії та плани", "B1", "Childhood memories", "What is your happiest memory from childhood?"),
    ("Мрії та плани", "B1", "A skill to learn", "What new skill would you like to learn and why?"),
    ("Мрії та плани", "B1", "A big goal", "What is one big goal you want to achieve in the next five years?"),
    ("Мрії та плани", "B2", "Biggest challenge", "Tell me about a difficult situation you overcame. What did you learn?"),
    ("Мрії та плани", "B2", "Advice to younger you", "What advice would you give to yourself five years ago?"),
    ("Мрії та плани", "B2", "Winning the lottery", "Imagine you won a million dollars. What would you do with it?"),
    ("Мрії та плани", "B2", "Fears", "What is something you are afraid of, and have you tried to overcome it?"),
    ("Мрії та плани", "C1", "Life in 2050", "What do you think everyday life will be like in 2050?"),
    ("Мрії та плани", "C1", "Regrets", "Is it better to regret something you did or something you never tried?"),
]

TOPICS: list[Topic] = [Topic(t[2].casefold(), *t) for t in _RAW]
CATEGORIES: list[str] = list(dict.fromkeys(t.category for t in TOPICS))
LEVELS = ["A2", "B1", "B2", "C1"]


def _pool(category: str | None, level: str | None) -> list[Topic]:
    return [t for t in TOPICS if (not category or t.category == category) and (not level or t.level == level)]


def remaining(db: Database, category: str | None, level: str | None) -> tuple[int, int]:
    pool = _pool(category, level)
    used = db.used_topics()
    return sum(1 for t in pool if t.key not in used), len(pool)


def pick_topic(db: Database, category: str | None = None, level: str | None = None,
               rng: random.Random | None = None) -> Topic | None:
    rng = rng or random.Random()
    pool = _pool(category, level)
    if not pool:
        return None
    used = db.used_topics()
    fresh = [t for t in pool if t.key not in used]
    if not fresh:
        last = db.last_topic()
        db.clear_used_topics([t.key for t in pool])
        fresh = [t for t in pool if t.key != last] or pool
    topic = rng.choice(fresh)
    db.mark_topic_used(topic.key)
    return topic
