const REPOSITORY = "hemanthkavula/AI-Job-Search-Agent";
const PRODUCTION_WORKFLOW = "daily-discovery.yml";
const ENRICHMENT_WORKFLOW = "employer-universe-enrichment.yml";

async function dispatchWorkflow(env, workflow, inputs = {}) {
  const response = await fetch(
    `https://api.github.com/repos/${REPOSITORY}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ai-job-search-cloudflare-scheduler"
      },
      body: JSON.stringify({ ref: "main", inputs })
    }
  );
  if (!response.ok) {
    throw new Error(`${workflow} dispatch failed: ${response.status} ${await response.text()}`);
  }
}

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

    if (!weekdays.has(weekday)) return;

    // Employer/source enrichment is a separate workflow. It only expands and
    // verifies the employer/source universe; it does not discover application
    // candidates, generate resumes, or update the application dashboard.
    if (hour === 5 && minute === 30) {
      await dispatchWorkflow(env, ENRICHMENT_WORKFLOW, {
        domain_budget: "750",
        career_budget: "750",
        ats_tenant_budget: "250",
        deep_domain_search: "true"
      });
      return;
    }

    // Production discovery remains on the six requested ET slots. Repeated
    // Cloudflare heartbeats during each 55-minute recovery window are safe
    // because the GitHub/Python slot guard prevents a completed slot rerun.
    const dueSlots = [[7,30],[10,0],[12,30],[15,30],[18,30],[21,0]];
    const localMinutes = hour * 60 + minute;
    const inRecoveryWindow = dueSlots.some(([slotHour, slotMinute]) => {
      const slotMinutes = slotHour * 60 + slotMinute;
      return localMinutes >= slotMinutes && localMinutes < slotMinutes + 55;
    });

    if (!inRecoveryWindow) return;

    await dispatchWorkflow(env, PRODUCTION_WORKFLOW, { force: "false" });
  }
};
