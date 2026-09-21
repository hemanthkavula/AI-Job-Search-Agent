import fs from "node:fs";
import { Stagehand } from "@browserbasehq/stagehand";

function emit(value) {
  process.stdout.write(JSON.stringify(value) + "\n");
}

function modelConfig() {
  const rawModel = process.env.STAGEHAND_MODEL || "qwen3:8b";
  const modelName = rawModel.includes("/") ? rawModel : "openai/" + rawModel;
  const baseURL = process.env.OLLAMA_OPENAI_BASE_URL || "http://127.0.0.1:11434/v1";
  return {
    modelName,
    apiKey: process.env.STAGEHAND_MODEL_API_KEY || "ollama-local",
    baseURL,
    openaiEndpointFormat: "chat",
  };
}

async function uploadResume(page, resumePath) {
  if (!resumePath || !fs.existsSync(resumePath)) return false;
  const inputs = page.locator('input[type="file"]');
  const count = await inputs.count();
  if (!count) return false;
  for (let i = 0; i < count; i++) {
    const input = inputs.nth(i);
    try {
      await input.setInputFiles(resumePath);
      return true;
    } catch (_) {}
  }
  return false;
}

async function main() {
  const raw = fs.readFileSync(0, "utf8");
  const job = JSON.parse(raw);
  const stagehand = new Stagehand({
    env: "LOCAL",
    model: modelConfig(),
    selfHeal: true,
    verbose: Number(process.env.STAGEHAND_VERBOSE || "1"),
    localBrowserLaunchOptions: {
      headless: String(process.env.STAGEHAND_HEADLESS || "false").toLowerCase() === "true",
    },
  });

  let submissionAttempted = false;
  try {
    await stagehand.init();
    const page = stagehand.context.pages()[0];
    await page.goto(job.url, { waitUntil: "domcontentloaded", timeout: 120000 });

    const agent = stagehand.agent();
    const common = `
You are completing exactly one US job application using only the candidate facts supplied below.
Never invent facts, credentials, certifications, dates, compensation, demographic answers, or technical experience.
Never bypass CAPTCHA, MFA, identity verification, or security challenges.
Never fill honeypot or robot-only fields.
Use the existing resume only; never generate, rewrite, or replace it.
Candidate facts: ${JSON.stringify(job.profile || {})}
Known answers: ${JSON.stringify(job.known_answers || {})}
Job context: ${String(job.description || "").slice(0, 12000)}
`;

    const first = await agent.execute({
      instruction: common + `
Start from the current page. Navigate login/account creation and the application naturally.
Fill only answers supported by the supplied facts.
Proceed until either (a) a resume upload is required, (b) a security/manual blocker occurs, or
(c) you reach final review. Do NOT perform the final submission.`,
      maxSteps: Number(process.env.STAGEHAND_APPLICATION_MAX_STEPS || "45"),
    });

    let uploaded = await uploadResume(page, job.resume_path);
    if (!uploaded) {
      try {
        await stagehand.act("Navigate to the resume/CV upload step if it is part of this application. Do not submit the application.");
        uploaded = await uploadResume(page, job.resume_path);
      } catch (_) {}
    }

    const second = await agent.execute({
      instruction: common + `
Continue the current application from exactly where it is now.
The approved resume ${uploaded ? "has already been attached; do not replace it" : "could not be attached automatically; stop if it is required"}.
Complete supported required fields and advance to the final review boundary.
${job.allow_submit
  ? "You are authorized to click the final Submit/Send Application button only after reviewing all answers. After clicking it, verify a positive rendered confirmation that the application was received."
  : "You are NOT authorized to click the final Submit/Send Application button. Stop on the final review page before that irreversible action."}
If CAPTCHA, MFA, identity verification, an unknown required answer, or a required missing resume prevents progress, stop and report that blocker.`,
      maxSteps: Number(process.env.STAGEHAND_APPLICATION_MAX_STEPS || "45"),
    });

    submissionAttempted = Boolean(job.allow_submit && second?.success);
    const bodyText = (await page.locator("body").innerText().catch(() => "")).slice(-12000);
    const confirmation = /application (has been )?(submitted|received)|thank you for applying|successfully submitted|we received your application/i.test(bodyText);
    const review = /review (your )?application|submit application|review and submit/i.test(bodyText);
    const blocker = /captcha|verification code|two[- ]factor|multi[- ]factor|verify your identity/i.test(bodyText)
      ? "Security verification requires human action."
      : (!uploaded && /resume|curriculum vitae|cv/i.test(bodyText) ? "Required resume upload could not be completed." : "");

    emit({
      ok: true,
      submitted: Boolean(job.allow_submit && confirmation),
      submission_attempted: Boolean(job.allow_submit && (confirmation || submissionAttempted)),
      ready_for_review: Boolean(!job.allow_submit && review && !blocker),
      resume_uploaded: uploaded,
      blocker,
      reason: confirmation ? "Positive submission confirmation detected." : (blocker || second?.message || first?.message || "Stagehand stopped without submission confirmation."),
      final_url: page.url(),
    });
  } catch (error) {
    emit({
      ok: false,
      submitted: false,
      submission_attempted: submissionAttempted,
      ready_for_review: false,
      blocker: "",
      reason: `${error?.name || "Error"}: ${error?.message || String(error)}`,
    });
    process.exitCode = 1;
  } finally {
    await stagehand.close().catch(() => {});
  }
}

main();
