#!/usr/bin/env node
/**
 * mcp-agent.js — Cowork Setup via MCP + REST APIs
 *
 * Replaces browser-agent.js entirely. Instead of driving a browser UI,
 * this agent calls real APIs:
 *
 *   GitHub REST API   → create repo, push files, set .gitignore
 *   Vercel REST API   → set env vars, trigger redeploy (MCP lacks env setter)
 *   Supabase REST API → run schema SQL, fetch project keys
 *   Notion MCP        → write a live setup progress page
 *
 * Claude acts as the orchestrator: it decides what to do next, calls tools,
 * inspects results, handles errors, and reports status — you don't touch
 * any web UI for these steps.
 *
 * Security model (same as setup-agent.js):
 *   - Secret VALUES never sent to Claude API as prompt text
 *   - Only SET/MISSING status goes to Claude for reasoning
 *   - Actual values injected by the runner at tool-call time
 *   - All API calls happen locally — no secrets leave your machine to
 *     intermediaries beyond the target service itself
 *
 * Usage:
 *   node mcp-agent/mcp-agent.js [phase]
 *   Phases: github | vercel | supabase | notion | all
 */

import Anthropic from "@anthropic-ai/sdk";
import dotenv from "dotenv";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const ENV_FILE = path.join(ROOT, ".env.setup");
const LOG_FILE = path.join(ROOT, "mcp-agent.log");

// ── Bootstrap ─────────────────────────────────────────────────────────────────
if (!fs.existsSync(ENV_FILE)) {
  console.error(`\n❌  Missing .env.setup at ${ENV_FILE}`);
  console.error(`   Export secrets from widget/index.html first.\n`);
  process.exit(1);
}
dotenv.config({ path: ENV_FILE });

const client = new Anthropic(); // ANTHROPIC_API_KEY from env

function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  fs.appendFileSync(LOG_FILE, line + "\n");
  console.log(msg);
}

// ── Secret safety ─────────────────────────────────────────────────────────────
// Claude only ever sees SET/MISSING — never values.
function envStatus(...keys) {
  return keys.map((k) => `${k}: ${process.env[k] ? "SET" : "MISSING"}`).join("\n");
}

// Get a secret value for direct API use (never sent to Claude)
function secret(key) {
  const v = process.env[key];
  if (!v) throw new Error(`Missing required secret: ${key}`);
  return v;
}

// ── REST helpers (all API calls happen here, not inside Claude) ───────────────

async function githubRequest(method, path, body) {
  const token = secret("GITHUB_TOKEN");
  const res = await fetch(`https://api.github.com${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(`GitHub ${method} ${path}: ${data.message}`);
  return data;
}

async function vercelRequest(method, path, body) {
  const token = secret("VERCEL_TOKEN");
  const res = await fetch(`https://api.vercel.com${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(`Vercel ${method} ${path}: ${JSON.stringify(data.error)}`);
  }
  return data;
}

async function supabaseRequest(method, path, body, useServiceKey = true) {
  const url = secret("SUPABASE_URL");
  const key = useServiceKey
    ? secret("SUPABASE_SERVICE_KEY")
    : secret("SUPABASE_ANON_KEY");
  const res = await fetch(`${url}${path}`, {
    method,
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
      Prefer: "return=representation",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Supabase ${method} ${path}: ${text}`);
  }
  return res.json().catch(() => null);
}

// ── Tool implementations (called by name from Claude's tool_use blocks) ────────

const toolImplementations = {

  // ── GitHub tools ─────────────────────────────────────────────────────────────

  async github_get_user() {
    const data = await githubRequest("GET", "/user");
    return { login: data.login, name: data.name, email: data.email };
  },

  async github_create_repo({ name, description, private: isPrivate }) {
    const data = await githubRequest("POST", "/user/repos", {
      name,
      description: description || "Cowork Dashboard",
      private: isPrivate ?? false,
      auto_init: false,
    });
    return { full_name: data.full_name, clone_url: data.clone_url, html_url: data.html_url };
  },

  async github_repo_exists({ owner, repo }) {
    try {
      const data = await githubRequest("GET", `/repos/${owner}/${repo}`);
      return { exists: true, full_name: data.full_name, clone_url: data.clone_url };
    } catch {
      return { exists: false };
    }
  },

  async github_push_file({ owner, repo, file_path, content, message, branch }) {
    // Get SHA of existing file (needed for updates)
    let sha;
    try {
      const existing = await githubRequest(
        "GET",
        `/repos/${owner}/${repo}/contents/${file_path}?ref=${branch || "main"}`
      );
      sha = existing.sha;
    } catch {
      // File doesn't exist yet — that's fine for creates
    }
    const data = await githubRequest(
      "PUT",
      `/repos/${owner}/${repo}/contents/${file_path}`,
      {
        message: message || `setup: add ${file_path}`,
        content: Buffer.from(content).toString("base64"),
        branch: branch || "main",
        ...(sha ? { sha } : {}),
      }
    );
    return { path: data.content?.path, sha: data.content?.sha };
  },

  async github_ensure_branch({ owner, repo, branch }) {
    try {
      // Get default branch SHA
      const ref = await githubRequest("GET", `/repos/${owner}/${repo}/git/ref/heads/main`);
      // Create new branch from main
      await githubRequest("POST", `/repos/${owner}/${repo}/git/refs`, {
        ref: `refs/heads/${branch}`,
        sha: ref.object.sha,
      });
      return { created: true };
    } catch (e) {
      if (e.message.includes("already exists")) return { created: false, existed: true };
      throw e;
    }
  },

  // ── Vercel tools ──────────────────────────────────────────────────────────────

  async vercel_list_projects() {
    const data = await vercelRequest("GET", "/v9/projects");
    return data.projects?.map((p) => ({ id: p.id, name: p.name })) || [];
  },

  async vercel_get_project({ name_or_id }) {
    try {
      const data = await vercelRequest("GET", `/v9/projects/${name_or_id}`);
      return { id: data.id, name: data.name, framework: data.framework };
    } catch {
      return { found: false };
    }
  },

  async vercel_set_env_vars({ project_id, vars }) {
    // vars: [{ key, value, target: ["production"], type: "encrypted" }]
    // Vercel requires upsert: delete existing then create, or use the upsert endpoint
    const results = [];
    for (const v of vars) {
      try {
        // Try to create; if 400 (already exists), update instead
        const res = await vercelRequest(
          "POST",
          `/v10/projects/${project_id}/env`,
          {
            key: v.key,
            value: v.value,
            target: v.target || ["production"],
            type: v.type || "encrypted",
          }
        );
        results.push({ key: v.key, status: "created", id: res.created?.[0]?.id });
      } catch (e) {
        if (e.message.includes("already exists") || e.message.includes("409")) {
          // Find and update the existing var
          try {
            const existing = await vercelRequest(
              "GET",
              `/v10/projects/${project_id}/env`
            );
            const found = existing.envs?.find((e) => e.key === v.key);
            if (found) {
              await vercelRequest(
                "PATCH",
                `/v10/projects/${project_id}/env/${found.id}`,
                { value: v.value, target: v.target || ["production"], type: "encrypted" }
              );
              results.push({ key: v.key, status: "updated" });
            }
          } catch (ue) {
            results.push({ key: v.key, status: "error", error: ue.message });
          }
        } else {
          results.push({ key: v.key, status: "error", error: e.message });
        }
      }
    }
    return results;
  },

  async vercel_trigger_redeploy({ project_id }) {
    // Get latest deployment and redeploy it
    const data = await vercelRequest(
      "GET",
      `/v6/deployments?projectId=${project_id}&limit=1&target=production`
    );
    const latest = data.deployments?.[0];
    if (!latest) return { error: "No existing deployments found" };
    const redeploy = await vercelRequest("POST", `/v13/deployments`, {
      deploymentId: latest.uid,
      name: latest.name,
      target: "production",
    });
    return { id: redeploy.id, url: redeploy.url, state: redeploy.readyState };
  },

  // ── Supabase tools ────────────────────────────────────────────────────────────

  async supabase_run_sql({ sql }) {
    // Uses Supabase's REST SQL execution via pg_jsonschema or direct REST
    // For schema setup we use the management API (requires service key)
    const url = secret("SUPABASE_URL");
    const key = secret("SUPABASE_SERVICE_KEY");

    // Extract project ref from URL: https://xxxx.supabase.co → xxxx
    const ref = new URL(url).hostname.split(".")[0];

    const res = await fetch(
      `https://api.supabase.com/v1/projects/${ref}/database/query`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${key}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query: sql }),
      }
    );
    const data = await res.json();
    if (!res.ok) return { error: data.message || JSON.stringify(data) };
    return { success: true, rows: data };
  },

  async supabase_list_tables() {
    const result = await toolImplementations.supabase_run_sql({
      sql: "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;",
    });
    return result;
  },

  async supabase_get_project_ref() {
    const url = secret("SUPABASE_URL");
    const ref = new URL(url).hostname.split(".")[0];
    return { ref, url };
  },

  // ── Notion tools (via Notion MCP URL) ────────────────────────────────────────
  // These run through a sub-agent call that uses the Notion MCP server,
  // rather than direct REST (Notion's API requires workspace/database IDs
  // that we discover dynamically). See runNotionSubagent().

  async notion_search_pages({ query }) {
    // Implemented via sub-agent — returns placeholder here
    return { _use_notion_subagent: true, query };
  },

  // ── Local file tools (needed for dashboard.html patch) ────────────────────────

  async local_read_file({ file_path }) {
    const full = path.join(ROOT, file_path);
    if (!fs.existsSync(full)) return { error: `File not found: ${file_path}` };
    let content = fs.readFileSync(full, "utf8");
    // Redact env values from file content before returning to Claude
    for (const [k, v] of Object.entries(process.env)) {
      if (v && v.length > 10) content = content.replaceAll(v, `[${k}]`);
    }
    return { content: content.slice(0, 4000) };
  },

  async local_patch_file({ file_path, find, replace }) {
    const full = path.join(ROOT, file_path);
    if (!fs.existsSync(full)) return { error: `File not found: ${file_path}` };
    let content = fs.readFileSync(full, "utf8");
    if (!content.includes(find)) return { error: `Pattern not found in ${file_path}` };
    // Interpolate {{VAR}} placeholders with real env values
    const interpolated = replace.replace(/\{\{(\w+)\}\}/g, (_, k) => process.env[k] || `{{${k}}}`);
    content = content.replace(find, interpolated);
    fs.writeFileSync(full, content, "utf8");
    log(`  ✎ patched ${file_path}`);
    return { success: true };
  },

  async local_report_done({ summary, remaining_manual_steps }) {
    return { __done__: true, summary, remaining_manual_steps };
  },
};

// ── Tool schemas for Claude ───────────────────────────────────────────────────

const tools = [
  // GitHub
  { name: "github_get_user", description: "Get the authenticated GitHub user's info.", input_schema: { type: "object", properties: {} } },
  { name: "github_repo_exists", description: "Check if a GitHub repo exists.", input_schema: { type: "object", properties: { owner: { type: "string" }, repo: { type: "string" } }, required: ["owner", "repo"] } },
  { name: "github_create_repo", description: "Create a new GitHub repo.", input_schema: { type: "object", properties: { name: { type: "string" }, description: { type: "string" }, private: { type: "boolean" } }, required: ["name"] } },
  { name: "github_push_file", description: "Create or update a single file in a GitHub repo via the API.", input_schema: { type: "object", properties: { owner: { type: "string" }, repo: { type: "string" }, file_path: { type: "string" }, content: { type: "string" }, message: { type: "string" }, branch: { type: "string" } }, required: ["owner", "repo", "file_path", "content"] } },
  { name: "github_ensure_branch", description: "Create a branch if it doesn't exist.", input_schema: { type: "object", properties: { owner: { type: "string" }, repo: { type: "string" }, branch: { type: "string" } }, required: ["owner", "repo", "branch"] } },

  // Vercel
  { name: "vercel_list_projects", description: "List all Vercel projects for this account.", input_schema: { type: "object", properties: {} } },
  { name: "vercel_get_project", description: "Get a specific Vercel project by name or ID.", input_schema: { type: "object", properties: { name_or_id: { type: "string" } }, required: ["name_or_id"] } },
  {
    name: "vercel_set_env_vars",
    description: "Set environment variables on a Vercel project. Pass key names only — the runner injects actual values from .env.setup securely.",
    input_schema: {
      type: "object",
      properties: {
        project_id: { type: "string" },
        vars: {
          type: "array",
          items: {
            type: "object",
            properties: {
              key: { type: "string", description: "The env var name, e.g. SUPABASE_URL" },
              target: { type: "array", items: { type: "string" }, description: "e.g. ['production']" },
            },
            required: ["key"],
          },
          description: "List of env vars to set. Values come from .env.setup automatically.",
        },
      },
      required: ["project_id", "vars"],
    },
  },
  { name: "vercel_trigger_redeploy", description: "Trigger a production redeploy of a Vercel project.", input_schema: { type: "object", properties: { project_id: { type: "string" } }, required: ["project_id"] } },

  // Supabase
  { name: "supabase_get_project_ref", description: "Get the Supabase project ref from the URL.", input_schema: { type: "object", properties: {} } },
  { name: "supabase_run_sql", description: "Run a SQL query against the Supabase project.", input_schema: { type: "object", properties: { sql: { type: "string" } }, required: ["sql"] } },
  { name: "supabase_list_tables", description: "List all tables in the public schema.", input_schema: { type: "object", properties: {} } },

  // Local file ops (for dashboard.html)
  { name: "local_read_file", description: "Read a local file (secrets are redacted in the output).", input_schema: { type: "object", properties: { file_path: { type: "string", description: "Relative to repo root" } }, required: ["file_path"] } },
  { name: "local_patch_file", description: "Patch a local file. Use {{VAR_NAME}} for secret values.", input_schema: { type: "object", properties: { file_path: { type: "string" }, find: { type: "string" }, replace: { type: "string", description: "Use {{VAR_NAME}} for secrets — they are interpolated before writing." } }, required: ["file_path", "find", "replace"] } },
  { name: "local_report_done", description: "Signal phase completion with a summary and any remaining manual steps.", input_schema: { type: "object", properties: { summary: { type: "string" }, remaining_manual_steps: { type: "array", items: { type: "string" } } }, required: ["summary"] } },
];

// ── Execute a tool call ───────────────────────────────────────────────────────

async function executeTool(name, input) {
  const fn = toolImplementations[name];
  if (!fn) return { error: `Unknown tool: ${name}` };

  // Special case: vercel_set_env_vars — Claude passes key names,
  // we inject actual values from process.env before calling the API.
  if (name === "vercel_set_env_vars") {
    const enriched = input.vars.map((v) => ({
      ...v,
      value: process.env[v.key] || "",
    }));
    // Warn Claude if any values are missing, without revealing the values themselves
    const missing = enriched.filter((v) => !v.value).map((v) => v.key);
    if (missing.length) {
      return { warning: `Missing values for: ${missing.join(", ")}`, set: [] };
    }
    return fn({ project_id: input.project_id, vars: enriched });
  }

  try {
    return await fn(input);
  } catch (err) {
    return { error: err.message };
  }
}

// ── Notion sub-agent (uses Notion MCP server) ─────────────────────────────────

async function runNotionSubagent(setupResults) {
  log("\n📓 Notion sub-agent: writing setup progress page...");

  const summary = Object.entries(setupResults)
    .map(([phase, result]) => `- ${phase}: ${result.success ? "✅ done" : "⚠️ " + (result.error || "partial")}`)
    .join("\n");

  const messages = [
    {
      role: "user",
      content: `Create a Notion page titled "Cowork Dashboard — Setup Log" with the following content:

# Cowork Dashboard — Setup Log
Generated: ${new Date().toISOString()}

## Results
${summary}

## Notes
- Gmail OAuth must be run manually (browser consent flow)
- Supabase schema SQL must be run manually if supabase_run_sql failed (paste config/supabase_schema.sql in Supabase SQL Editor)

Create the page in the root of the workspace. Report the page URL when done.`,
    },
  ];

  const response = await client.messages.create({
    model: "claude-sonnet-4-20250514",
    max_tokens: 2048,
    system: "You are a Notion assistant. Create pages using the available Notion MCP tools. Be concise.",
    messages,
    mcp_servers: [
      { type: "url", url: "https://mcp.notion.com/mcp", name: "notion" },
    ],
    betas: ["mcp-client-2025-04-04"],
  });

  const text = response.content
    .filter((b) => b.type === "text")
    .map((b) => b.text)
    .join("\n");

  log(`  Notion: ${text.slice(0, 200)}`);
  return { success: true, output: text };
}

// ── Core agentic loop ─────────────────────────────────────────────────────────

async function runPhase(phaseName, systemPrompt, userMessage) {
  log(`\n${"─".repeat(60)}`);
  log(`🤖 MCP Agent phase: ${phaseName}`);
  log(`${"─".repeat(60)}\n`);

  const messages = [{ role: "user", content: userMessage }];
  let iterations = 0;
  const MAX = 25;

  while (iterations++ < MAX) {
    const response = await client.messages.create({
      model: "claude-sonnet-4-20250514",
      max_tokens: 4096,
      system: systemPrompt,
      tools,
      messages,
    });

    const textBlocks = response.content.filter((b) => b.type === "text");
    const toolBlocks = response.content.filter((b) => b.type === "tool_use");

    textBlocks.forEach((b) => {
      if (b.text?.trim()) log(`\n💬 ${b.text.trim()}`);
    });

    if (response.stop_reason === "end_turn" && !toolBlocks.length) {
      log("\n✅ Phase ended naturally.");
      return { success: true };
    }

    const toolResults = [];
    for (const tb of toolBlocks) {
      log(`  🔧 ${tb.name}(${JSON.stringify(tb.input).slice(0, 100)})`);
      const result = await executeTool(tb.name, tb.input);

      if (result?.__done__) {
        log(`\n✅ ${result.summary}`);
        if (result.remaining_manual_steps?.length) {
          log("\n📋 Manual steps still needed:");
          result.remaining_manual_steps.forEach((s) => log(`  → ${s}`));
        }
        return { success: true, summary: result.summary };
      }

      if (result?.error) log(`  ⚠️  ${result.error}`);
      else log(`  ✓  ${JSON.stringify(result).slice(0, 120)}`);

      toolResults.push({
        type: "tool_result",
        tool_use_id: tb.id,
        content: JSON.stringify(result),
      });
    }

    messages.push({ role: "assistant", content: response.content });
    if (toolResults.length) {
      messages.push({ role: "user", content: toolResults });
    }
  }

  return { success: false, error: "Max iterations reached" };
}

// ── Phase definitions ─────────────────────────────────────────────────────────

const SYSTEM = `You are an automated setup agent for the Cowork Dashboard project.
You call tools to configure GitHub, Vercel, and Supabase via their APIs.

Rules:
- Never ask the user for input — work autonomously with the tools available.
- If a tool returns an error, try an alternative approach or report it in local_report_done.
- Secret values are injected automatically — never try to read or log them yourself.
- Call local_report_done when the phase is complete, listing any steps that failed or need manual follow-up.`;

const phases = {
  github: () =>
    runPhase(
      "GitHub",
      SYSTEM,
      `Set up the GitHub repository for the Cowork Dashboard.

Env status:
${envStatus("GITHUB_TOKEN", "GIT_USER_NAME", "GIT_USER_EMAIL", "GITHUB_REPO_URL")}

Steps:
1. Call github_get_user to get the authenticated user's login.
2. Determine the repo name from GITHUB_REPO_URL if set, else use "cowork-dashboard".
3. Check if the repo already exists with github_repo_exists.
4. If it doesn't exist, create it with github_create_repo.
5. Push a .gitignore file with these contents:
   .env
   .env.setup
   config/.env
   workers/credentials.json
   workers/token.json
   node_modules/
   *.log
6. Push a README.md placeholder if one doesn't already exist.
7. Report done with the repo URL.`
    ),

  vercel: () =>
    runPhase(
      "Vercel",
      SYSTEM,
      `Configure Vercel environment variables for the Cowork Dashboard.

Env status:
${envStatus("VERCEL_TOKEN", "ANTHROPIC_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_KEY")}

Steps:
1. List projects with vercel_list_projects to find the cowork project.
   Look for a project named "cowork" or "cowork-dashboard".
2. If found, get its project ID.
3. Set these environment variables on the project (values are injected automatically):
   - ANTHROPIC_API_KEY → target: production
   - SUPABASE_URL → target: production
   - SUPABASE_SERVICE_KEY → target: production
4. After setting vars, trigger a redeploy with vercel_trigger_redeploy.
5. Report done with the deployment URL, or list any vars that failed as manual steps.`
    ),

  supabase: () =>
    runPhase(
      "Supabase",
      SYSTEM,
      `Verify the Supabase schema for the Cowork Dashboard.

Env status:
${envStatus("SUPABASE_URL", "SUPABASE_SERVICE_KEY")}

Steps:
1. Get the project ref with supabase_get_project_ref.
2. List existing tables with supabase_list_tables.
3. Check if these 5 tables exist: emails, diy_log, weekly_plans, habits, habit_completions.
4. For any missing tables, run the CREATE TABLE SQL using supabase_run_sql.
   Use this schema for each missing table:

   emails:
   CREATE TABLE IF NOT EXISTS emails (
     id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
     date date NOT NULL,
     subject text,
     sender text,
     ai_summary text,
     priority text,
     created_at timestamptz DEFAULT now()
   );

   diy_log:
   CREATE TABLE IF NOT EXISTS diy_log (
     id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
     date date NOT NULL,
     entry text,
     created_at timestamptz DEFAULT now()
   );

   weekly_plans:
   CREATE TABLE IF NOT EXISTS weekly_plans (
     id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
     week_start date NOT NULL,
     plan text,
     created_at timestamptz DEFAULT now()
   );

   habits:
   CREATE TABLE IF NOT EXISTS habits (
     id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
     name text NOT NULL,
     created_at timestamptz DEFAULT now()
   );

   habit_completions:
   CREATE TABLE IF NOT EXISTS habit_completions (
     id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
     habit_id uuid REFERENCES habits(id),
     completed_date date NOT NULL,
     created_at timestamptz DEFAULT now()
   );

5. Verify tables exist after creation.
6. Report done with the table count, or list failures as manual steps.`
    ),

  dashboard: () =>
    runPhase(
      "Dashboard config",
      SYSTEM,
      `Patch the CONFIG block in dashboard.html with real values.

Env status:
${envStatus("SUPABASE_URL", "SUPABASE_ANON_KEY", "VERCEL_URL")}

Steps:
1. Read dashboard.html with local_read_file.
2. Find the CONFIG block — it looks like:
   const CONFIG = {
     supabase: {
       url:     'https://xxxxxxxxxxxxxxxxxxxx.supabase.co',
       anonKey: 'eyJ...',
     },
     vercel: {
       apiUrl: 'https://cowork-itay.vercel.app',
     },
   };
3. Use local_patch_file to replace the placeholder values:
   - url: '{{SUPABASE_URL}}'
   - anonKey: '{{SUPABASE_ANON_KEY}}'
   - apiUrl: '{{VERCEL_URL}}'
4. Read the file again to verify the patch applied.
5. Report done.`
    ),
};

// ── Entry point ───────────────────────────────────────────────────────────────

async function main() {
  const arg = process.argv[2] || "all";
  const order = ["github", "vercel", "supabase", "dashboard"];
  const toRun = arg === "all" ? order : arg.split(",").map((s) => s.trim());

  log("🚀 Cowork MCP Agent starting");
  log(`   Phases: ${toRun.join(" → ")}\n`);

  const results = {};

  for (const phase of toRun) {
    if (!phases[phase]) {
      log(`❌ Unknown phase: ${phase}. Available: ${order.join(", ")}, notion`);
      continue;
    }
    if (phase === "notion") {
      results.notion = await runNotionSubagent(results);
    } else {
      results[phase] = await phases[phase]();
    }
  }

  // Always write a Notion progress page if Notion isn't in the explicit run list
  // and the user has it connected — but only if at least one phase ran
  if (!toRun.includes("notion") && Object.keys(results).length > 0) {
    log("\n📓 Writing setup summary to Notion...");
    try {
      results.notion = await runNotionSubagent(results);
    } catch (e) {
      log(`  ⚠️  Notion update skipped: ${e.message}`);
    }
  }

  log("\n🎉 MCP Agent complete. See mcp-agent.log for details.");

  // Print summary
  log("\nSummary:");
  for (const [phase, result] of Object.entries(results)) {
    const icon = result?.success ? "✅" : "⚠️ ";
    log(`  ${icon} ${phase}: ${result?.summary || (result?.success ? "done" : result?.error || "partial")}`);
  }
}

main().catch((err) => {
  log(`\n💥 Fatal: ${err.message}`);
  console.error(err.stack);
  process.exit(1);
});
