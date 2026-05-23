"""
weekly_plan.py — Weekly plan generator for Railway.
Schedule: every Sunday at 18:00 Israel time (16:00 UTC)

Generates next week's plan → writes markdown to recurring/plans/ →
stores structured data in Supabase → git push → Vercel redeploys.
"""

import os
import json
from datetime import date, timedelta, datetime
import anthropic

LEARNING_PATH = [
    (1, "AI/LLM Foundation",     "The AI Engineer Course 2026",                "Foundation — end-to-end LLM apps and RAG"),
    (2, "Agents + Fine-Tuning",  "Agentic Workflows with LangChain & LangGraph","Building stateful agents and multi-step workflows"),
    (3, "AWS Security",          "AWS Security Specialty (SCS-C03)",            "IAM, KMS, Secrets Manager, VPC security"),
    (4, "System Design",         "System Design Interview",                      "Scalability, caching, message queues, databases"),
    (5, "Kubernetes + Algorithms","Kubernetes CKA + Master the Coding Interview","CKA production ops, DP and graph algorithms"),
    (6, "Security Capstone",     "Ethical Hacking & OWASP Top 10",              "Pen testing, XSS, CSRF, API security"),
]

DIY_ROTATION = [
    "Wall-Mounted Floating Shelves",
    "Cable Management Desk Setup",
    "Kitchen Herb Garden",
    "Custom LED Ambient Lighting",
    "Phone/Tablet Stand from Wood",
    "Window Insulation Film",
    "Balcony Privacy Screen",
    "Magnetic Knife Strip",
    "DIY Headboard",
    "Rope Bookshelf",
]

TRIP_IDEAS = [
    "Rosh Hanikra + Nahariya — northern coastal escape, 1h45m drive",
    "Haifa day trip — Bahá'í Gardens, Carmel forest, German Colony",
    "Jerusalem weekend — Old City, Yad Vashem, Mahane Yehuda",
    "Dead Sea Friday half-day — float, roadside hummus, back by evening",
    "Acre (Akko) day trip — Old City walls, hummus at Hummus Said, harbour",
    "Caesarea archaeological site + Zichron Yaakov wine tour",
    "Ein Gedi + Masada day trip — desert nature and history",
    "Galilee wine region — wineries around Zefat and Rosh Pinna",
]


def next_week_start() -> date:
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7 or 7
    return today + timedelta(days=days_until_monday)


def current_month() -> int:
    """Return which learning month we're in (1–6) based on week count since epoch."""
    ref = date(2026, 1, 5)   # first Monday of the learning path
    weeks_elapsed = (date.today() - ref).days // 7
    return min(6, max(1, (weeks_elapsed // 4) + 1))


def generate_plan(week_start: date) -> str:
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    month_num = current_month()
    _, month_theme, course_name, course_focus = LEARNING_PATH[month_num - 1]
    week_num = week_start.isocalendar()[1]
    diy = DIY_ROTATION[week_num % len(DIY_ROTATION)]
    trip = TRIP_IDEAS[week_num % len(TRIP_IDEAS)]

    msg = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=2500,
        messages=[{
            'role': 'user',
            'content': f"""Generate a weekly plan for Itay Osovlanski — 30yo Senior Backend Engineer in Tel Aviv.

Week: {week_start.strftime('%B %d, %Y')} (week #{week_num})
Learning month: {month_num}/6 — {month_theme}
Current course: {course_name}
Course focus this week: {course_focus}
DIY project: {diy}
Weekend trip idea: {trip}

Write the plan in this exact markdown format (keep all section headers identical):

# 📅 Weekly Plan — Week of {week_start.strftime('%B %-d, %Y')}

> *Tel Aviv · Senior Backend Engineer · 30 y/o*

---

## 🎯 Top 3 Goals This Week

1. **[AI/coding goal]** ...
2. **[Health/fitness goal]** ...
3. **[Personal/life goal]** ...

---

## 🗓 Daily Schedule

| Day | Morning (7–9am) | Deep Work (9am–1pm) | Afternoon | Evening |
|-----|-----------------|----------------------|-----------|---------|
[7 rows for Mon–Sun with realistic Tel Aviv engineer lifestyle]

---

## ✅ Habit Tracker

| Habit | Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|-------|-----|-----|-----|-----|-----|-----|-----|
| 🏋️ Exercise | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 📖 Read 20min | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 🎓 Learn / course | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 🥗 Eat healthy | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 😴 Sleep 7h+ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 👟 10k steps | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 📵 No doom-scrolling | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 💻 Side project work | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |

---

## 🎓 Learning Focus

**Course:** *{course_name}*

**This week's focus:** {course_focus}

[3–4 bullet points of specific things to do this week]

---

## 🔨 DIY Project This Week

**Project: {diy}**

[2–3 sentences on timing, what to buy, and what to achieve by Saturday]

---

## 💼 Job Search Tracker

| Date Applied | Company | Role | Stage | Follow-up Date | Notes |
|---|---|---|---|---|---|
| | | | | | |

---

## 📬 Admin / Email Checklist

- [ ] Review last month's expenses against the ₪1,500/week budget target
- [ ] Follow up on any pending professional emails older than 5 days
- [ ] [one relevant admin item for this week]

---

## 💰 Weekly Budget Reminder

**Target: ₪1,500 / week** *(excluding rent)*

| Category | Budget | Spent | Remaining |
|----------|--------|-------|-----------|
| Groceries & food | ₪500 | | |
| Eating out / coffee | ₪300 | | |
| Transport | ₪150 | | |
| Entertainment | ₪200 | | |
| DIY / misc | ₪350 | | |
| **Total** | **₪1,500** | | |

---

## ✈️ Weekend Trip Idea

**{trip}**

[2–3 sentences: what to do, distance, approximate cost]

---

## 📝 End-of-Week Reflection *(fill in Sunday evening)*

**What did I actually accomplish this week?**

*(Write here)*

**What got in the way?**

*(Write here)*

**One thing I'm proud of:**

*(Write here)*

**One thing to do differently next week:**

*(Write here)*

**Energy level this week (1–10):** ___

**Mood overall (1–10):** ___

---

*Generated automatically on {date.today().strftime('%A, %B %-d, %Y')} · Next plan drops Sunday {(week_start + timedelta(days=6)).strftime('%b %-d')} evening.*""",
        }]
    )
    return msg.content[0].text


def save_markdown(content: str, week_start: date) -> str:
    filename = f"week_{week_start.strftime('%Y-%m-%d')}.md"
    path = f'recurring/plans/{filename}'
    os.makedirs('recurring/plans', exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)
    print(f'  ✓ Wrote {path}')
    return path


def store_in_supabase(week_start: date, markdown: str):
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_SERVICE_KEY')
    if not (url and key):
        print('  Supabase not configured — skipping')
        return
    import urllib.request
    payload = json.dumps({
        'week_start': str(week_start),
        'plan':       markdown,
    }).encode()
    req = urllib.request.Request(
        f'{url}/rest/v1/weekly_plans',
        data=payload,
        headers={
            'apikey': key, 'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
            'Prefer': 'resolution=merge-duplicates',
        },
        method='POST',
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        print('  ✓ Stored in Supabase')
    except Exception as e:
        print(f'  Warning: Supabase write: {e}')


def git_push(filepath: str, week_start: date):
    from github_push import push_file
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    push_file(filepath, content, f'auto: weekly plan {week_start}')


def main():
    week_start = next_week_start()
    print(f'[{datetime.now().isoformat()}] Generating weekly plan for {week_start}')
    plan     = generate_plan(week_start)
    filepath = save_markdown(plan, week_start)
    store_in_supabase(week_start, plan)
    git_push(filepath, week_start)
    print('Done ✓')


if __name__ == '__main__':
    main()
