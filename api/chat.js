import Anthropic from "@anthropic-ai/sdk";
import { createClient } from "@supabase/supabase-js";

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_KEY);

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).end();

  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  const { type, id, label } = req.body;

  try {
    let context = "";

    if (type === "email") {
      const { data } = await supabase.from("emails").select("*").eq("id", id).single();
      context = `Email from: ${data?.sender}\nSubject: ${data?.subject}\nExisting summary: ${data?.ai_summary || "none"}`;
    } else if (type === "diy") {
      const { data } = await supabase.from("diy_log").select("*").eq("id", id).single();
      context = `DIY log entry (${data?.date}): ${data?.entry}`;
    } else if (type === "overview") {
      const [emails, diy, plans] = await Promise.all([
        supabase.from("emails").select("subject,sender,priority").order("date", { ascending: false }).limit(5),
        supabase.from("diy_log").select("date,entry").order("date", { ascending: false }).limit(3),
        supabase.from("weekly_plans").select("week_start,plan").order("week_start", { ascending: false }).limit(1),
      ]);
      context = `Recent emails: ${JSON.stringify(emails.data)}\nRecent DIY: ${JSON.stringify(diy.data)}\nCurrent plan: ${JSON.stringify(plans.data)}`;
    }

    const message = await anthropic.messages.create({
      model: "claude-haiku-4-5-20251001",
      max_tokens: 300,
      messages: [{
        role: "user",
        content: `Give a concise 2-3 sentence insight or summary about this: ${label || type}\n\nContext:\n${context}`,
      }],
    });

    res.json({ summary: message.content[0].text });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
}
