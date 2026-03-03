export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // GET /feedback/:digestId — render feedback page
    const getMatch = path.match(/^\/feedback\/([a-f0-9]+)$/);
    if (getMatch && request.method === "GET") {
      return handleGetFeedback(env, getMatch[1]);
    }

    // POST /feedback/:digestId/:urlHash — submit vote
    const postMatch = path.match(/^\/feedback\/([a-f0-9]+)\/([a-f0-9]+)$/);
    if (postMatch && request.method === "POST") {
      return handlePostFeedback(env, request, postMatch[1], postMatch[2]);
    }

    return new Response("Not found", { status: 404 });
  },
};

async function handleGetFeedback(env, digestId) {
  const digest = await env.FEEDBACK_KV.get(`digest:${digestId}`, "json");
  if (!digest) {
    return new Response("Digest not found", { status: 404 });
  }

  // Load existing feedback for this digest
  const existingFeedback = {};
  for (const article of digest.articles) {
    const fb = await env.FEEDBACK_KV.get(`feedback:${digestId}:${article.url_hash}`, "json");
    if (fb) {
      existingFeedback[article.url_hash] = fb.thumbs_up;
    }
  }

  const html = renderFeedbackPage(digest, digestId, existingFeedback);
  return new Response(html, { headers: { "Content-Type": "text/html;charset=utf-8" } });
}

async function handlePostFeedback(env, request, digestId, urlHash) {
  let body;
  try {
    body = await request.json();
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }

  const key = `feedback:${digestId}:${urlHash}`;
  await env.FEEDBACK_KV.put(key, JSON.stringify({
    url: body.url,
    title: body.title || "",
    source: body.source || "",
    thumbs_up: body.thumbs_up,
    digest_date: body.digest_date || "",
  }));

  return new Response(JSON.stringify({ ok: true }), {
    headers: { "Content-Type": "application/json" },
  });
}

function renderFeedbackPage(digest, digestId, existingFeedback) {
  const articleRows = digest.articles.map((a) => {
    const existing = existingFeedback[a.url_hash];
    const upActive = existing === true ? "active" : "";
    const downActive = existing === false ? "active" : "";

    return `
    <div class="article" data-url-hash="${a.url_hash}" data-url="${escapeAttr(a.url)}" data-title="${escapeAttr(a.title)}" data-source="${escapeAttr(a.source)}">
      <div class="article-header">
        <a href="${escapeAttr(a.url)}" target="_blank">${escapeHtml(a.title)}</a>
      </div>
      <div class="article-meta">${escapeHtml(a.source)} · ${a.score}/10</div>
      <div class="article-reason">${escapeHtml(a.reason)}</div>
      <div class="buttons">
        <button class="btn thumb-up ${upActive}" onclick="vote(this, true)">&#128077;</button>
        <button class="btn thumb-down ${downActive}" onclick="vote(this, false)">&#128078;</button>
      </div>
    </div>`;
  }).join("\n");

  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rate Recommendations</title>
<style>
  body { font-family: -apple-system, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 16px; background: #fafafa; }
  h2 { border-bottom: 2px solid #333; padding-bottom: 8px; }
  .article { background: #fff; border-radius: 8px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .article-header a { color: #2563eb; text-decoration: none; font-weight: 600; font-size: 16px; }
  .article-header a:hover { text-decoration: underline; }
  .article-meta { color: #666; font-size: 13px; margin: 4px 0; }
  .article-reason { color: #333; font-size: 14px; margin: 8px 0; }
  .buttons { display: flex; gap: 8px; margin-top: 8px; }
  .btn { font-size: 24px; padding: 8px 16px; border: 2px solid #ddd; border-radius: 8px; background: #fff; cursor: pointer; transition: all 0.15s; }
  .btn:hover { border-color: #999; }
  .btn.active.thumb-up { background: #d1fae5; border-color: #10b981; }
  .btn.active.thumb-down { background: #fee2e2; border-color: #ef4444; }
  .saved { color: #10b981; font-size: 13px; margin-left: 8px; opacity: 0; transition: opacity 0.3s; }
  .saved.show { opacity: 1; }
</style>
</head>
<body>
<h2>Rate These Recommendations</h2>
<p style="color:#666;font-size:14px;">Your feedback helps improve future recommendations.</p>
${articleRows}
<script>
const digestId = "${digestId}";

async function vote(btn, thumbsUp) {
  const article = btn.closest('.article');
  const urlHash = article.dataset.urlHash;

  // Toggle: if already active, deselect
  const wasActive = btn.classList.contains('active');

  // Clear both buttons
  article.querySelectorAll('.btn').forEach(b => b.classList.remove('active'));

  if (wasActive) return; // just deselected, don't send

  btn.classList.add('active');

  try {
    await fetch('/feedback/' + digestId + '/' + urlHash, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: article.dataset.url,
        title: article.dataset.title,
        source: article.dataset.source,
        thumbs_up: thumbsUp,
      }),
    });
  } catch (e) {
    console.error('Failed to save feedback:', e);
  }
}
</script>
</body>
</html>`;
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function escapeAttr(str) {
  return str.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
