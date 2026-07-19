DEFAULT_FACT_EXTRACTION_PROMPT = """You are a Developer Memory Organizer for a coding-assistant memory store. Extract durable, reusable facts from the input and return them as JSON.

Rules — follow all of them:

1. PRESERVE SCOPE TAGS VERBATIM. If an input fact begins with a bracketed scope tag like `[ProjectName]:` or `[global]:`, every extracted fact derived from it MUST begin with that exact same tag, unchanged. Never strip, reword, or relocate the tag.
1b. CLASSIFY UNTAGGED FACTS. If an input fact has no scope tag, assign one:
   - Prefix `[global]:` when the fact holds across projects: user preferences, corrections, workflow habits, dev-machine setup, tool conventions, account/infra facts.
   - Prefix `[<name>]:` when the fact is tied to a specific project whose name appears in the text (lowercase the name, e.g. `[voicecraft]:`).
   - If the fact is project-specific but the project is not identifiable from the text, keep it untagged — never guess a project name.
2. STAY CLOSE TO THE SOURCE WORDING. Keep technical identifiers exactly as written: file paths, commands, env var names, versions, commit hashes, URLs, function names. Do not paraphrase facts into third-person narration like "User notes that..." or "User is using..." — keep the original declarative form.
3. KEEP FACTS SUBSTANTIVE. A fact must be specific and useful in a future session: stack/architecture decisions, exact dev/test/build commands, bug root causes, rejected approaches and why, conventions, env var names and purposes, gotchas.
4. DISCARD NOISE. Return no fact for:
   - Raw shell command transcripts or tool invocations ("executed command: cd ... && grep ...")
   - Transient task intents or status ("wants to deploy", "is planning to", "requests next steps")
   - Greetings, meta-conversation, or notes about saving/storing memories themselves
   - Secrets or credential values (env var NAMES are fine, values are not)
5. One distinct fact per list item; split unrelated facts, keep related details together.

Few-shot examples:

Input: Hi, can you help me deploy this?
Output: {"facts": []}

Input: User executed command: cd api && grep -rn "retry" app/utils/
Output: {"facts": []}

Input: [acme-shop]: PostgreSQL 15 via Prisma ORM. Migrations in /prisma/migrations. Commands: pnpm db:migrate, pnpm db:seed. Connection via DATABASE_URL env var.
Output: {"facts": ["[acme-shop]: PostgreSQL 15 via Prisma ORM. Migrations in /prisma/migrations. Commands: pnpm db:migrate, pnpm db:seed. Connection via DATABASE_URL env var."]}

Input: [acme-shop]: Fixed checkout double-charge bug — root cause was missing idempotency key in /src/payments/charge.ts; retries now send Idempotency-Key header. Also, we want to look into the flaky CI job tomorrow.
Output: {"facts": ["[acme-shop]: Fixed checkout double-charge bug — root cause was missing idempotency key in /src/payments/charge.ts; retries now send Idempotency-Key header."]}

Input: I prefer named exports over default exports in TypeScript, and always use pnpm instead of npm.
Output: {"facts": ["[global]: Prefers named exports over default exports in TypeScript.", "[global]: Always uses pnpm instead of npm."]}

Input: AcmeShop deploys on Fly.io via fly deploy; secrets managed with fly secrets set, config in fly.toml.
Output: {"facts": ["[acmeshop]: Deploys on Fly.io via fly deploy; secrets managed with fly secrets set, config in fly.toml."]}

Return the facts in JSON format with key "facts" whose value is a list of strings. If nothing qualifies, return {"facts": []}.
"""

MEMORY_CATEGORIZATION_PROMPT = """Your task is to assign each piece of information (or “memory”) to one or more of the following categories. Feel free to use multiple categories per item when appropriate.

- Personal: family, friends, home, hobbies, lifestyle
- Relationships: social network, significant others, colleagues
- Preferences: likes, dislikes, habits, favorite media
- Health: physical fitness, mental health, diet, sleep
- Travel: trips, commutes, favorite places, itineraries
- Work: job roles, companies, projects, promotions
- Education: courses, degrees, certifications, skills development
- Projects: to‑dos, milestones, deadlines, status updates
- AI, ML & Technology: infrastructure, algorithms, tools, research
- Technical Support: bug reports, error logs, fixes
- Finance: income, expenses, investments, billing
- Shopping: purchases, wishlists, returns, deliveries
- Legal: contracts, policies, regulations, privacy
- Entertainment: movies, music, games, books, events
- Messages: emails, SMS, alerts, reminders
- Customer Support: tickets, inquiries, resolutions
- Product Feedback: ratings, bug reports, feature requests
- News: articles, headlines, trending topics
- Organization: meetings, appointments, calendars
- Goals: ambitions, KPIs, long‑term objectives

Guidelines:
- Return only the categories under 'categories' key in the JSON format.
- If you cannot categorize the memory, return an empty list with key 'categories'.
- Don't limit yourself to the categories listed above only. Feel free to create new categories based on the memory. Make sure that it is a single phrase.
"""
