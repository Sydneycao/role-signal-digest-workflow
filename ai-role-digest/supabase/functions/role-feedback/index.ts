import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function html(body: string, status = 200): Response {
  const headers = new Headers();
  headers.set("Content-Type", "application/xhtml+xml; charset=utf-8");

  return new Response(
    `<!doctype html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Role Feedback</title>
<style>
  body{font-family:system-ui,sans-serif;max-width:640px;margin:40px auto;padding:0 16px;color:#222}
  h1{font-size:1.25rem;margin-bottom:8px}
  .muted{color:#666;font-size:.9rem}
  textarea{box-sizing:border-box;width:100%;min-height:180px;margin:12px 0;padding:10px;
           font:inherit;border:1px solid #d0d7de;border-radius:6px}
  button{background:#1a73e8;color:#fff;border:0;border-radius:6px;padding:9px 14px;font:inherit}
  a{color:#1a73e8}
</style>
</head>
<body>${body}</body>
</html>`,
    { status, headers },
  );
}

async function saveFeedback(payload: {
  post_id: string;
  post_url: string;
  title: string;
  feedback_type: "good" | "not_good";
  note?: string;
}): Promise<Response | null> {
  const { error } = await supabase.from("role_feedback").insert(payload);
  if (!error) {
    return null;
  }

  console.error("Failed to save role feedback", error);
  return html(
    `<h1>Could not save feedback</h1>
<p class="muted">Please try again later.</p>`,
    500,
  );
}

Deno.serve(async (req: Request) => {
  if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
    return html(
      `<h1>Feedback is not configured</h1>
<p class="muted">Missing Supabase environment variables.</p>`,
      500,
    );
  }

  const url = new URL(req.url);

  if (req.method === "GET") {
    const action = url.searchParams.get("action");
    const post_id = url.searchParams.get("post_id") ?? "";
    const post_url = url.searchParams.get("post_url") ?? "";
    const title = url.searchParams.get("title") ?? "LinkedIn role";

    if (!post_id) {
      return html("<h1>Missing post ID</h1>", 400);
    }

    if (action === "good") {
      const errorResponse = await saveFeedback({
        post_id,
        post_url,
        title,
        feedback_type: "good",
      });
      if (errorResponse) {
        return errorResponse;
      }
      return html(
        `<h1>Saved: Good</h1>
<p class="muted">The workflow will treat this as a positive signal.</p>`,
      );
    }

    if (action === "add_feedback") {
      return html(
        `<h1>Add feedback</h1>
<p class="muted">${escapeHtml(title)}</p>
<form method="post">
  <input type="hidden" name="post_id" value="${escapeHtml(post_id)}" />
  <input type="hidden" name="post_url" value="${escapeHtml(post_url)}" />
  <input type="hidden" name="title" value="${escapeHtml(title)}" />
  <textarea name="note" required="required" autofocus="autofocus" placeholder="Why is this result not good?"></textarea>
  <button type="submit">Save feedback</button>
</form>`,
      );
    }
  }

  if (req.method === "POST") {
    const form = await req.formData();
    const post_id = String(form.get("post_id") ?? "");
    const post_url = String(form.get("post_url") ?? "");
    const title = String(form.get("title") ?? "LinkedIn role");
    const note = String(form.get("note") ?? "").trim();

    if (!post_id || !note) {
      return html("<h1>Missing feedback</h1>", 400);
    }

    const errorResponse = await saveFeedback({
      post_id,
      post_url,
      title,
      feedback_type: "not_good",
      note,
    });
    if (errorResponse) {
      return errorResponse;
    }

    return html(
      `<h1>Feedback saved</h1>
<p class="muted">Thanks. This note can be used to tune the scoring rubric.</p>`,
    );
  }

  return html("<h1>Not found</h1>", 404);
});
