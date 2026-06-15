import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const FEEDBACK_FORM_URL = Deno.env.get("FEEDBACK_FORM_URL") ?? "";

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

function text(body: string, status = 200): Response {
  return new Response(body, {
    status,
    headers: { ...corsHeaders, "Content-Type": "text/plain; charset=utf-8" },
  });
}

function json(body: Record<string, unknown>, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json; charset=utf-8" },
  });
}

function feedbackFormUrl(apiUrl: URL): string {
  const formUrl = new URL(FEEDBACK_FORM_URL);
  for (const key of ["post_id", "post_url", "title"]) {
    const value = apiUrl.searchParams.get(key);
    if (value) {
      formUrl.searchParams.set(key, value);
    }
  }
  formUrl.searchParams.set("api_url", `${apiUrl.origin}${apiUrl.pathname}`);
  return formUrl.toString();
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
  return json({ ok: false, error: "Could not save feedback" }, 500);
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
    return json({ ok: false, error: "Feedback is not configured" }, 500);
  }

  const url = new URL(req.url);

  if (req.method === "GET") {
    const action = url.searchParams.get("action");
    const post_id = url.searchParams.get("post_id") ?? "";
    const post_url = url.searchParams.get("post_url") ?? "";
    const title = url.searchParams.get("title") ?? "LinkedIn role";

    if (!post_id) {
      return text("Missing post ID", 400);
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
      return text("Saved: Good");
    }

    if (action === "add_feedback") {
      if (FEEDBACK_FORM_URL) {
        return Response.redirect(feedbackFormUrl(url), 303);
      }
      return text("Feedback form URL is not configured", 500);
    }
  }

  if (req.method === "POST") {
    const contentType = req.headers.get("content-type") ?? "";
    let post_id = "";
    let post_url = "";
    let title = "LinkedIn role";
    let note = "";

    if (contentType.includes("application/json")) {
      const body = await req.json();
      post_id = String(body.post_id ?? "");
      post_url = String(body.post_url ?? "");
      title = String(body.title ?? title);
      note = String(body.note ?? "").trim();
    } else {
      const form = await req.formData();
      post_id = String(form.get("post_id") ?? "");
      post_url = String(form.get("post_url") ?? "");
      title = String(form.get("title") ?? title);
      note = String(form.get("note") ?? "").trim();
    }

    if (!post_id || !note) {
      return json({ ok: false, error: "Missing feedback" }, 400);
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

    return json({ ok: true, message: "Feedback saved" });
  }

  return text("Not found", 404);
});
