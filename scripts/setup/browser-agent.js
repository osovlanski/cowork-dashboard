#!/usr/bin/env node
/**
 * Browser Setup Agent
 * Uses Claude in Chrome (MCP) to automate web steps:
 * Supabase project creation, Railway env vars, Vercel deployment config.
 *
 * Run AFTER the local agent has collected your secrets into .env.setup.
 * Secrets are read locally and typed into browser fields — never sent to any server.
 */

import Anthropic from "@anthropic-ai/sdk";
import dotenv from "dotenv";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const ENV_FILE = path.join(ROOT, ".env.setup");

// ── Load secrets ──────────────────────────────────────────────────────────────
if (!fs.existsSync(ENV_FILE)) {
  console.error(`\n❌  Missing .env.setup at ${ENV_FILE}\n`);
  process.exit(1);
}
dotenv.config({ path: ENV_FILE });

const client = new Anthropic();

// ── Secret-safe summary for prompts ──────────────────────────────────────────
// We pass values for secrets that need to be TYPED into browser fields.
// This is intentional — the browser agent must type them into UI fields.
// They travel over localhost MCP only, not the internet.
function secretsForBrowser(keys) {
  return keys
    .map((k) => `${k}=${process.env[k] || "MISSING"}`)
    .join("\n");
}

// ── Browser agent phases ──────────────────────────────────────────────────────
const BROWSER_SYSTEM = `
You are a browser automation agent helping set up the Cowork Dashboard project.
You control a real browser via tools. Follow instructions precisely and carefully.

Rules:
- Navigate to each URL step by step.
- Wait for pages to load before interacting.
- If a field isn't found, scroll and try again before giving up.
- When typing secrets, type them exactly as provided.
- Report what you did and what you found.
- If you hit a login wall, stop and report — the user must log in manually.
`.trim();

const browserPhases = {
  supabase: (secrets) => ({
    prompt: `
Open Supabase and set up the project schema:

1. Navigate to https://supabase.com/dashboard
2. If not logged in, stop and tell the user to log in.
3. Find the project named "cowork-dashboard" (or create it: New Project, name=cowork-dashboard, region=EU West).
4. Go to SQL Editor → New query.
5. The user will paste the schema SQL — tell them to open config/supabase_schema.sql and paste it, then click Run.
6. Go to Project Settings → API.
7. Find and copy: URL, anon/public key, service_role key.
8. Report all three values to the user so they can update .env.setup.

Current known values (may already be set):
${secrets}
    `.trim(),
  }),

  railway: (secrets) => ({
    prompt: `
Open Railway and configure environment variables for the Cowork project:

1. Navigate to https://railway.app/dashboard
2. If not logged in, stop and ask the user to log in.
3. Find the cowork project (or create it: New Project → Deploy from GitHub repo → select cowork repo).
4. Go to the project variables section.
5. Add each of these environment variables one by one:

${secrets}

6. Confirm each variable was saved.
7. Report done or any errors.
    `.trim(),
  }),

  vercel: (secrets) => ({
    prompt: `
Open Vercel and configure environment variables for the Cowork project:

1. Navigate to https://vercel.com/dashboard
2. If not logged in, stop and ask the user to log in.
3. Find the cowork project (or create it: Add New → Project → import GitHub repo).
4. Go to Settings → Environment Variables.
5. Add each of these variables for Production:

${secrets}

6. Confirm each was saved.
7. Go back to the project and trigger a redeploy if needed.
8. Copy the deployment URL (*.vercel.app) and report it.
    `.trim(),
  }),
};

// ── Run browser agent via Claude in Chrome MCP ────────────────────────────────
async function runBrowserAgent(phase) {
  console.log(`\n${"─".repeat(60)}`);
  console.log(`🌐 Browser agent phase: ${phase}`);
  console.log(`${"─".repeat(60)}\n`);

  let phaseConfig;
  if (phase === "supabase") {
    const secrets = secretsForBrowser(["SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY"]);
    phaseConfig = browserPhases.supabase(secrets);
  } else if (phase === "railway") {
    const secrets = secretsForBrowser([
      "ANTHROPIC_API_KEY",
      "SUPABASE_URL",
      "SUPABASE_SERVICE_KEY",
      "GMAIL_CLIENT_ID",
      "GMAIL_CLIENT_SECRET",
      "GMAIL_REFRESH_TOKEN",
      "GIT_USER_NAME",
      "GIT_USER_EMAIL",
      "GITHUB_TOKEN",
    ]);
    phaseConfig = browserPhases.railway(secrets);
  } else if (phase === "vercel") {
    const secrets = secretsForBrowser([
      "ANTHROPIC_API_KEY",
      "SUPABASE_URL",
      "SUPABASE_SERVICE_KEY",
    ]);
    phaseConfig = browserPhases.vercel(secrets);
  } else {
    console.error(`Unknown phase: ${phase}`);
    process.exit(1);
  }

  const messages = [{ role: "user", content: phaseConfig.prompt }];

  // Claude in Chrome MCP server
  const mcpServers = [
    {
      type: "url",
      url: "https://mcp.claude.ai/chrome",
      name: "claude-chrome",
    },
  ];

  let done = false;
  let iterations = 0;

  while (!done && iterations++ < 20) {
    const response = await client.messages.create({
      model: "claude-sonnet-4-20250514",
      max_tokens: 4096,
      system: BROWSER_SYSTEM,
      messages,
      mcp_servers: mcpServers,
      betas: ["mcp-client-2025-04-04"],
    });

    const textBlocks = response.content.filter((b) => b.type === "text");
    const toolBlocks = response.content.filter(
      (b) => b.type === "tool_use" || b.type === "mcp_tool_use"
    );
    const toolResults = response.content.filter(
      (b) => b.type === "tool_result" || b.type === "mcp_tool_result"
    );

    textBlocks.forEach((b) => {
      if (b.text?.trim()) console.log(`\n💬 ${b.text.trim()}`);
    });

    toolBlocks.forEach((b) => {
      console.log(`  🔧 ${b.name}(${JSON.stringify(b.input).slice(0, 80)}...)`);
    });

    if (response.stop_reason === "end_turn" && toolBlocks.length === 0) {
      console.log("\n✅ Browser agent phase complete.");
      done = true;
    }

    messages.push({ role: "assistant", content: response.content });

    // If there are tool results in the response (MCP handles tool execution)
    // we just continue the loop
  }
}

// ── CLI ───────────────────────────────────────────────────────────────────────
async function main() {
  const arg = process.argv[2] || "all";
  const order = ["supabase", "railway", "vercel"];
  const toRun = arg === "all" ? order : [arg];

  console.log("🌐 Cowork Browser Setup Agent");
  console.log("   Make sure Claude in Chrome extension is running.\n");

  for (const phase of toRun) {
    await runBrowserAgent(phase);
  }

  console.log("\n🎉 Browser agent complete.");
}

main().catch((err) => {
  console.error(`\n💥 Fatal: ${err.message}`);
  process.exit(1);
});
