#!/usr/bin/env node
/**
 * Cowork Setup Agent
 * Reads .env.setup, writes config files, runs shell commands,
 * uses Claude to reason about next steps and errors.
 *
 * Security: secrets never sent to Claude API — only variable names + status.
 */

import Anthropic from "@anthropic-ai/sdk";
import dotenv from "dotenv";
import fs from "fs";
import path from "path";
import { execSync } from "child_process";
import readline from "readline";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const ENV_FILE = path.join(ROOT, ".env.setup");
const LOG_FILE = path.join(ROOT, "setup-agent.log");

// ── Load secrets ─────────────────────────────────────────────────────────────
if (!fs.existsSync(ENV_FILE)) {
  console.error(`\n❌  Missing .env.setup at ${ENV_FILE}`);
  console.error(
    `   Export your secrets from the setup widget and save them there.\n`
  );
  process.exit(1);
}
dotenv.config({ path: ENV_FILE });

const client = new Anthropic(); // reads ANTHROPIC_API_KEY from env automatically

// ── Logging ───────────────────────────────────────────────────────────────────
function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  fs.appendFileSync(LOG_FILE, line + "\n");
  console.log(msg);
}

// ── Shell runner ──────────────────────────────────────────────────────────────
function shell(cmd, opts = {}) {
  log(`  $ ${cmd}`);
  try {
    const out = execSync(cmd, {
      cwd: opts.cwd || ROOT,
      encoding: "utf8",
      stdio: ["pipe", "pipe", "pipe"],
    });
    return { ok: true, out: out.trim() };
  } catch (e) {
    return { ok: false, out: e.stderr?.trim() || e.message };
  }
}

// ── File helpers ──────────────────────────────────────────────────────────────
function fileExists(p) {
  return fs.existsSync(path.join(ROOT, p));
}
function readFile(p) {
  return fs.readFileSync(path.join(ROOT, p), "utf8");
}
function writeFile(p, content) {
  const full = path.join(ROOT, p);
  fs.mkdirSync(path.dirname(full), { recursive: true });
  fs.writeFileSync(full, content, "utf8");
  log(`  ✎ wrote ${p}`);
}
function appendFile(p, content) {
  const full = path.join(ROOT, p);
  fs.appendFileSync(full, content, "utf8");
  log(`  ✎ appended to ${p}`);
}

// ── Secret-safe env summary (names + presence only, never values) ─────────────
function envSummary() {
  const keys = [
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_KEY",
    "GMAIL_CLIENT_ID",
    "GMAIL_CLIENT_SECRET",
    "GMAIL_REFRESH_TOKEN",
    "ANTHROPIC_API_KEY",
    "GIT_USER_NAME",
    "GIT_USER_EMAIL",
    "GITHUB_TOKEN",
    "VERCEL_URL",
  ];
  return keys
    .map((k) => `${k}: ${process.env[k] ? "SET" : "MISSING"}`)
    .join("\n");
}

// ── File system snapshot (no secret values) ───────────────────────────────────
function fsSummary() {
  const checks = [
    ".gitignore",
    "dashboard.html",
    "workers/credentials.json",
    "workers/token.json",
    "config/supabase_schema.sql",
    "railway.toml",
  ];
  return checks.map((f) => `${f}: ${fileExists(f) ? "EXISTS" : "MISSING"}`).join("\n");
}

// ── Tools Claude can invoke ───────────────────────────────────────────────────
const tools = [
  {
    name: "run_shell",
    description:
      "Run a shell command on the local machine. Never include secret values in commands — use environment variable references like $VAR_NAME instead.",
    input_schema: {
      type: "object",
      properties: {
        command: { type: "string", description: "Shell command to run" },
        reason: {
          type: "string",
          description: "Why this command is needed",
        },
      },
      required: ["command", "reason"],
    },
  },
  {
    name: "write_file",
    description:
      "Write content to a file, using placeholder tokens like {{SUPABASE_URL}} which the agent replaces with real values before writing.",
    input_schema: {
      type: "object",
      properties: {
        path: {
          type: "string",
          description: "Relative path from repo root",
        },
        content: {
          type: "string",
          description:
            "File content. Use {{VAR_NAME}} for any secret values.",
        },
        reason: { type: "string" },
      },
      required: ["path", "content", "reason"],
    },
  },
  {
    name: "patch_file",
    description:
      "Replace a specific string in an existing file with new content. Use {{VAR_NAME}} placeholders for secrets.",
    input_schema: {
      type: "object",
      properties: {
        path: { type: "string" },
        find: { type: "string", description: "Exact string to find" },
        replace: {
          type: "string",
          description: "Replacement string. Use {{VAR_NAME}} for secrets.",
        },
        reason: { type: "string" },
      },
      required: ["path", "find", "replace", "reason"],
    },
  },
  {
    name: "read_file",
    description: "Read a local file to inspect its current state.",
    input_schema: {
      type: "object",
      properties: {
        path: { type: "string" },
      },
      required: ["path"],
    },
  },
  {
    name: "report_done",
    description: "Signal that this setup phase is complete.",
    input_schema: {
      type: "object",
      properties: {
        summary: {
          type: "string",
          description: "What was accomplished",
        },
        next_steps: {
          type: "array",
          items: { type: "string" },
          description: "Manual steps still needed (e.g. web console actions)",
        },
      },
      required: ["summary", "next_steps"],
    },
  },
];

// ── Interpolate {{VAR}} placeholders with real env values ─────────────────────
function interpolate(str) {
  return str.replace(/\{\{(\w+)\}\}/g, (_, k) => process.env[k] || `{{${k}}}`);
}

// ── Execute a tool call from Claude ──────────────────────────────────────────
function executeTool(name, input) {
  if (name === "run_shell") {
    log(`\n🔧 ${input.reason}`);
    const cmd = interpolate(input.command);
    const result = shell(cmd);
    if (!result.ok) log(`  ⚠ Error: ${result.out}`);
    return result.ok
      ? `Success:\n${result.out}`
      : `Error:\n${result.out}`;
  }

  if (name === "write_file") {
    log(`\n📝 ${input.reason}`);
    const content = interpolate(input.content);
    writeFile(input.path, content);
    return `Written: ${input.path}`;
  }

  if (name === "patch_file") {
    log(`\n✏️  ${input.reason}`);
    if (!fileExists(input.path)) return `File not found: ${input.path}`;
    let content = readFile(input.path);
    if (!content.includes(input.find)) {
      return `String not found in ${input.path}:\n${input.find}`;
    }
    content = content.replace(input.find, interpolate(input.replace));
    writeFile(input.path, content);
    return `Patched: ${input.path}`;
  }

  if (name === "read_file") {
    if (!fileExists(input.path)) return `File not found: ${input.path}`;
    // Redact any accidental secret leakage
    let content = readFile(input.path);
    Object.keys(process.env).forEach((k) => {
      if (process.env[k] && process.env[k].length > 8) {
        content = content.replaceAll(process.env[k], `[${k}]`);
      }
    });
    return content.slice(0, 3000); // cap to avoid huge context
  }

  if (name === "report_done") {
    return "__DONE__";
  }

  return `Unknown tool: ${name}`;
}

// ── Agentic loop ──────────────────────────────────────────────────────────────
async function runAgent(phase, systemPrompt) {
  log(`\n${"─".repeat(60)}`);
  log(`🤖 Starting agent phase: ${phase}`);
  log(`${"─".repeat(60)}\n`);

  const messages = [
    {
      role: "user",
      content: `
Environment variable status (SET/MISSING — no values):
${envSummary()}

Local file status:
${fsSummary()}

Begin the "${phase}" setup phase.
      `.trim(),
    },
  ];

  let iterations = 0;
  const MAX = 30;

  while (iterations++ < MAX) {
    const response = await client.messages.create({
      model: "claude-sonnet-4-20250514",
      max_tokens: 4096,
      system: systemPrompt,
      tools,
      messages,
    });

    // Collect text and tool calls
    const textBlocks = response.content.filter((b) => b.type === "text");
    const toolBlocks = response.content.filter((b) => b.type === "tool_use");

    textBlocks.forEach((b) => {
      if (b.text.trim()) log(`\n💬 ${b.text.trim()}`);
    });

    if (response.stop_reason === "end_turn" && toolBlocks.length === 0) {
      log("\n✅ Agent finished (no more tool calls).");
      break;
    }

    // Execute tool calls and collect results
    const toolResults = [];
    for (const tb of toolBlocks) {
      const result = executeTool(tb.name, tb.input);
      if (result === "__DONE__") {
        log(`\n✅ Phase complete: ${tb.input.summary}`);
        if (tb.input.next_steps?.length) {
          log("\n📋 Manual steps remaining:");
          tb.input.next_steps.forEach((s) => log(`  → ${s}`));
        }
        return;
      }
      toolResults.push({
        type: "tool_result",
        tool_use_id: tb.id,
        content: result,
      });
    }

    // Add assistant turn + tool results to history
    messages.push({ role: "assistant", content: response.content });
    if (toolResults.length) {
      messages.push({ role: "user", content: toolResults });
    }
  }
}

// ── Phase definitions ─────────────────────────────────────────────────────────
const SYSTEM_BASE = `
You are a local setup agent for the Cowork Dashboard project.
You help configure a developer's machine by writing files and running shell commands.

SECURITY RULES — strictly enforced:
1. Never include raw secret values in shell commands. Always reference them as $ENV_VAR.
2. Never log or echo secret values.
3. When writing files with secrets, use {{VAR_NAME}} placeholders — the runner interpolates them.
4. Only operate within the project directory.
5. Do not make network requests other than via the provided shell commands.

You have these tools: run_shell, write_file, patch_file, read_file, report_done.
Call report_done when the phase is complete.
`.trim();

const phases = {
  gitignore: {
    prompt: `${SYSTEM_BASE}

PHASE: Ensure .gitignore protects secrets.
- Read the existing .gitignore if it exists.
- Make sure these lines are present: .env, .env.setup, config/.env, workers/credentials.json, workers/token.json
- If missing, add them. Do not duplicate existing lines.
- Report done with a summary.`,
  },

  dashboard: {
    prompt: `${SYSTEM_BASE}

PHASE: Patch dashboard.html CONFIG block.
- Read dashboard.html to find the CONFIG block near the top.
- Replace the placeholder values with {{SUPABASE_URL}}, {{SUPABASE_ANON_KEY}}, {{VERCEL_URL}}.
- Use patch_file so you only change that block, not the whole file.
- Report done with a summary. List any manual steps if VERCEL_URL is missing.`,
  },

  git: {
    prompt: `${SYSTEM_BASE}

PHASE: Initialize git and push to GitHub.
- Check if .git exists (run: ls -la .git)
- If not, run: git init
- Set git user config using $GIT_USER_NAME and $GIT_USER_EMAIL
- Add remote origin using $GITHUB_REPO_URL if set, otherwise report it as a manual step.
- Stage all files: git add .
- Commit: git commit -m "initial: cowork dashboard" (skip if nothing to commit)
- Push: git push -u origin main using $GITHUB_TOKEN via https
- Report done.`,
  },

  gmail: {
    prompt: `${SYSTEM_BASE}

PHASE: Gmail OAuth local setup.
- Check if workers/credentials.json exists.
- If missing, report it as a manual step (user must download from Google Cloud Console).
- If present, check if workers/token.json exists (already authed).
- If token.json missing, run the auth script: python workers/setup_gmail_auth.py
- Report done with clear instructions for any manual steps.`,
  },
};

// ── CLI entry point ───────────────────────────────────────────────────────────
async function main() {
  const arg = process.argv[2] || "all";

  const order = ["gitignore", "dashboard", "git", "gmail"];
  const toRun = arg === "all" ? order : [arg];

  for (const phase of toRun) {
    if (!phases[phase]) {
      console.error(`Unknown phase: ${phase}. Available: ${order.join(", ")}`);
      process.exit(1);
    }
    await runAgent(phase, phases[phase].prompt);
  }

  log("\n🎉 Setup agent complete. Check setup-agent.log for full details.");
}

main().catch((err) => {
  log(`\n💥 Fatal error: ${err.message}`);
  process.exit(1);
});
