export default {
  async scheduled(controller, env, ctx) {
    const now = new Date(controller.scheduledTime);
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      weekday: "short", hour: "2-digit", minute: "2-digit",
      hour12: false
    }).formatToParts(now);
    const get = (t) => parts.find((p) => p.type === t)?.value;
    const weekday = get("weekday");
    const hour = Number(get("hour"));
    const minute = Number(get("minute"));
    const weekdays = new Set(["Mon","Tue","Wed","Thu","Fri"]);
    const dueHours = new Set([7,9,11,13,15,17,19]);

    if (!weekdays.has(weekday) || !dueHours.has(hour) || minute >= 55) return;

    const response = await fetch(
      "https://api.github.com/repos/hemanthkavula/AI-Job-Search-Agent/actions/workflows/daily-discovery.yml/dispatches",
      {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
          "Accept": "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "ai-job-search-cloudflare-scheduler"
        },
        body: JSON.stringify({ ref: "main", inputs: { force: "false" } })
      }
    );
    if (!response.ok) {
      throw new Error(`GitHub dispatch failed: ${response.status} ${await response.text()}`);
    }
  }
};
