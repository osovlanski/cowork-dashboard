"""
diy_log.py — Daily DIY log entry generator for Railway.
Schedule: every day at 07:00 Israel time (05:00 UTC)

Generates a contextual DIY log entry (quick-win / new project / full-day)
based on day of week → prepends to fun/diy/daily_log.md → git push.
"""

import os
import subprocess
from datetime import date, datetime
import anthropic

PROJECTS = [
    ("Wall-Mounted Floating Shelves",    "Medium",  "2–3h",  "200–400 ILS"),
    ("Cable Management Desk Setup",       "Easy",    "1–2h",  "150–300 ILS"),
    ("Kitchen Herb Garden",               "Easy",    "1h",    "250–400 ILS"),
    ("Custom LED Ambient Lighting",       "Medium",  "2h",    "300–500 ILS"),
    ("Upcycled Crate Storage",            "Easy",    "1–2h",  "200–350 ILS"),
    ("Phone/Tablet Stand from Wood",      "Easy",    "1–2h",  "80–150 ILS"),
    ("Window Insulation Film",            "Medium",  "1–2h",  "300–500 ILS"),
    ("Balcony Privacy Screen",            "Medium",  "2–3h",  "400–700 ILS"),
    ("Magnetic Knife Strip",              "Easy",    "30min", "100–200 ILS"),
    ("DIY Headboard",                     "Medium",  "3–4h",  "400–800 ILS"),
    ("Desk Organizer from PVC Pipe",      "Medium",  "2h",    "150–300 ILS"),
    ("Rope Bookshelf",                    "Medium",  "2–3h",  "300–500 ILS"),
]

DAY_TYPES = {
    4: ('quick',   'TGIF quick win — finish strong and start the weekend with a small build 🎉'),
    3: ('new',     'Thursday energy — start a new project and make the first 3 steps happen tonight'),
    5: ('full',    'Saturday project day — full build, take your time, enjoy the process ☕'),
    0: ('motivation', 'Monday momentum — small progress beats a perfect plan every time'),
    1: ('motivation', 'Tuesday check-in — mid-week is the perfect time for a quick project boost'),
    2: ('motivation', 'Wednesday progress — you\'re over the hump, pick up something hands-on'),
    6: ('reflection', 'Sunday reset — reflect on the week\'s build and plan what comes next 🌿'),
}


def pick_project(today: date) -> tuple:
    week = today.isocalendar()[1]
    day  = today.weekday()
    # Rotate through projects so each week has a fresh pick
    idx = (week * 3 + day) % len(PROJECTS)
    return PROJECTS[idx]


def generate_entry(today: date) -> str:
    client  = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    day     = today.weekday()
    day_name = today.strftime('%A')
    dtype, context = DAY_TYPES.get(day, ('motivation', ''))
    project, diff, time_est, budget = pick_project(today)

    type_instructions = {
        'quick':      'Write a punchy Friday quick-win entry. Include a simple 3-step game plan for tonight. TGIF vibe.',
        'new':        'Write a "start this project today" Thursday entry. List the first 3 concrete steps to get momentum.',
        'full':       'Write a full Saturday project day entry. Include all key steps, what to buy, and how long each phase takes.',
        'motivation': 'Write a short weekday motivational nudge. One concrete tiny action to make progress tonight (15–30 min max).',
        'reflection': 'Write a Sunday reflection entry. Ask one reflective question about last week\'s progress and suggest next week\'s pick.',
    }

    msg = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=500,
        messages=[{
            'role': 'user',
            'content': f"""Write a daily DIY log entry for Itay — 30yo software engineer in a Tel Aviv apartment.

Project: {project}
Difficulty: {diff} | Time: {time_est} | Budget: {budget}
Day: {day_name} ({context})

Instructions: {type_instructions[dtype]}

Format your response as:
## {today.strftime('%Y-%m-%d')} ({day_name}) — [short catchy title with emoji]

[2–3 sentence intro]

**The vitals**
- Time: {time_est}
- Budget: {budget}
- Difficulty: {diff}
- Tools: [relevant tools]

[Main content — steps or motivational nudge, max 250 words total]

Keep it friendly, practical, Tel Aviv-aware. No preamble, just the formatted entry.""",
        }]
    )
    return msg.content[0].text


def prepend_entry(entry: str) -> str:
    path = 'fun/diy/daily_log.md'
    os.makedirs('fun/diy', exist_ok=True)
    existing = ''
    if os.path.exists(path):
        with open(path) as f:
            existing = f.read()

    # Keep the title line, prepend new entry after it
    lines = existing.split('\n')
    if lines and lines[0].startswith('#'):
        title = lines[0]
        rest  = '\n'.join(lines[1:]).lstrip('\n')
        new_content = f"{title}\n\n{entry}\n\n---\n\n{rest}"
    else:
        new_content = f"# Daily DIY Log\n\n{entry}\n\n---\n\n{existing}"

    with open(path, 'w') as f:
        f.write(new_content)
    print(f'  ✓ Prepended entry to {path}')
    return path


def git_push(filepath: str, message: str):
    repo_dir = os.environ.get('REPO_DIR', '.')
    try:
        subprocess.run(['git', '-C', repo_dir, 'add', filepath], check=True)
        subprocess.run(['git', '-C', repo_dir, 'commit', '-m', message], check=True)
        subprocess.run(['git', '-C', repo_dir, 'push'], check=True)
        print(f'  ✓ Git pushed')
    except subprocess.CalledProcessError as e:
        print(f'  Warning: git push failed: {e}')


def main():
    today = date.today()
    print(f'[{datetime.now().isoformat()}] Generating DIY log entry for {today}')
    entry    = generate_entry(today)
    filepath = prepend_entry(entry)
    git_push(filepath, f'auto: DIY log {today}')
    print('Done ✓')


if __name__ == '__main__':
    main()
