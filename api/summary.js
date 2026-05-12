// Vercel Serverless Function — /api/summary
// POST { type: 'course'|'book'|'travel'|'diy', id: string, name: string }
// Returns { summary: string }
// Checks Supabase cache first; calls Claude Haiku if not cached.

const PROMPTS = {
  course:  (name) => `You are helping a 30-year-old senior software engineer in Tel Aviv evaluate a Udemy course. Summarize this course in exactly 3 sentences covering: (1) what you'll learn and build, (2) who it's best suited for and the effort required, (3) one concrete reason to prioritize it now. Course: "${name}"`,
  book:    (name) => `Summarize this book for a senior software engineer who reads for both enjoyment and professional growth. 3 sentences: (1) what it's about and why it's compelling, (2) the reading experience (difficulty, pace, style), (3) one specific reason an engineer would love it. Book: "${name}"`,
  travel:  (name) => `Summarize this destination for a solo 30-year-old traveling from Tel Aviv. 3 sentences: (1) the top 2–3 highlights, (2) practical info (flight time, best season, cost range), (3) one thing that makes it special for a tech-minded traveler. Destination: "${name}"`,
  diy:     (name) => `Summarize this DIY home project for a software engineer in a Tel Aviv apartment. 3 sentences: (1) what you make and the main benefit, (2) time, budget, and skill required, (3) one pro tip that makes it go smoothly. Project: "${name}"`,
};

export default async function handler(req, res) {
  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { type, id, name } = req.body || {};
  if (!type || !id || !name) return res.status(400).json({ error: 'Missing type, id, or name' });
  if (!PROMPTS[type]) return res.status(400).json({ error: 'Invalid type' });

  const supabaseUrl = process.env.SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_SERVICE_KEY;  // service role key (server-side only)
  const anthropicKey = process.env.ANTHROPIC_API_KEY;

  if (!anthropicKey) return res.status(500).json({ error: 'ANTHROPIC_API_KEY not set' });

  // ── Check Supabase cache ──────────────────────────────
  if (supabaseUrl && supabaseKey) {
    try {
      const cacheRes = await fetch(
        `${supabaseUrl}/rest/v1/ai_summaries?item_type=eq.${type}&item_key=eq.${id}&select=summary`,
        { headers: { apikey: supabaseKey, Authorization: `Bearer ${supabaseKey}` } }
      );
      const cached = await cacheRes.json();
      if (cached?.length > 0) {
        return res.status(200).json({ summary: cached[0].summary, cached: true });
      }
    } catch { /* cache miss, continue */ }
  }

  // ── Call Claude Haiku ─────────────────────────────────
  let summary;
  try {
    const claudeRes = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'x-api-key': anthropicKey,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 300,
        messages: [{ role: 'user', content: PROMPTS[type](name) }],
      }),
    });
    if (!claudeRes.ok) throw new Error(`Claude API error: ${claudeRes.status}`);
    const claudeData = await claudeRes.json();
    summary = claudeData.content?.[0]?.text;
    if (!summary) throw new Error('No summary returned');
  } catch (err) {
    console.error('Claude error:', err);
    return res.status(500).json({ error: 'Failed to generate summary' });
  }

  // ── Store in Supabase cache ───────────────────────────
  if (supabaseUrl && supabaseKey) {
    try {
      await fetch(`${supabaseUrl}/rest/v1/ai_summaries`, {
        method: 'POST',
        headers: {
          apikey: supabaseKey,
          Authorization: `Bearer ${supabaseKey}`,
          'Content-Type': 'application/json',
          Prefer: 'resolution=merge-duplicates',
        },
        body: JSON.stringify({ item_type: type, item_key: id, item_name: name, summary }),
      });
    } catch { /* cache write failed, not critical */ }
  }

  return res.status(200).json({ summary });
}
