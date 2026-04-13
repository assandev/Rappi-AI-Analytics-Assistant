import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function LoadingState() {
  return (
    <div className="mt-8 rounded-3xl bg-surfaceContainerLow p-6">
      <div className="flex items-center gap-3">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <p className="font-heading text-[20px] font-bold text-onSurface">Building executive insights report...</p>
      </div>
      <div className="mt-4 space-y-3">
        <div className="h-4 w-full animate-pulse rounded-lg bg-surfaceContainerHighest/70" />
        <div className="h-4 w-[92%] animate-pulse rounded-lg bg-surfaceContainerHighest/70" />
        <div className="h-4 w-[84%] animate-pulse rounded-lg bg-surfaceContainerHighest/70" />
      </div>
    </div>
  );
}

export function InsightsGeneratorPage({
  report,
  isGeneratingInsights,
  onGenerateInsights,
  onSendEmail,
  isSendingEmail,
  emailStatus,
  errorText,
  downloadUrl,
}) {
  const [recipientEmail, setRecipientEmail] = useState("");
  const [emailTouched, setEmailTouched] = useState(false);

  const normalizedEmail = recipientEmail.trim();
  const canSendEmail = EMAIL_REGEX.test(normalizedEmail) && !isSendingEmail;
  const showEmailError = emailTouched && !EMAIL_REGEX.test(normalizedEmail);

  const generatedMeta = useMemo(() => {
    if (!report) {
      return "No report generated yet.";
    }
    const cacheLabel = report.cached ? "cached" : "fresh";
    return `${report.insight_count} findings | generated at ${report.generated_at} | ${cacheLabel}`;
  }, [report]);

  return (
    <section className="mx-auto h-[calc(100vh-64px)] max-w-[1700px] overflow-y-auto px-8 py-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-heading text-[42px] font-extrabold leading-none text-onSurface">Insights Generator</h1>
          <p className="mt-2 text-[20px] text-onSurfaceVariant">
            Generate and review the weekly executive report.
          </p>
        </div>
        <button
          type="button"
          onClick={() => onGenerateInsights(false)}
          disabled={isGeneratingInsights}
          className="inline-flex h-11 items-center gap-2 rounded-xl bg-gradient-to-r from-primary to-primaryContainer px-5 font-heading text-[15px] font-bold text-white disabled:opacity-60"
        >
          {isGeneratingInsights ? "Generating..." : "Generate Report"}
          <span className="text-xs">{">"}</span>
        </button>
        <button
          type="button"
          onClick={() => onGenerateInsights(true)}
          disabled={isGeneratingInsights}
          className="inline-flex h-11 items-center rounded-xl bg-surfaceContainerHigh px-5 font-heading text-[14px] font-bold text-onSurface disabled:opacity-60"
        >
          Regenerate Anyway
        </button>
      </div>

      <div className="mt-6 rounded-3xl bg-surfaceContainerLowest p-6 shadow-ambient">
        <p className="text-sm text-onSurfaceVariant">{generatedMeta}</p>

        {errorText ? (
          <div className="mt-4 rounded-xl bg-[#fff2f0] px-4 py-3 text-[14px] text-primary">{errorText}</div>
        ) : null}

        {isGeneratingInsights ? <LoadingState /> : null}

        {!isGeneratingInsights && report ? (
          <>
            <div className="mt-5 flex flex-wrap items-center gap-3">
              <a
                href={downloadUrl}
                className="inline-flex h-10 items-center rounded-xl bg-surfaceContainerHigh px-4 font-heading text-[14px] font-bold text-onSurface"
              >
                Download .md
              </a>
              <input
                type="email"
                value={recipientEmail}
                onChange={(event) => setRecipientEmail(event.target.value)}
                onBlur={() => setEmailTouched(true)}
                placeholder="Recipient email"
                className={`h-10 min-w-[280px] rounded-xl bg-surfaceContainerLow px-3 text-sm text-onSurface outline-none ${
                  showEmailError ? "ring-2 ring-primary" : "ring-1 ring-transparent"
                }`}
              />
              <button
                type="button"
                onClick={() => {
                  setEmailTouched(true);
                  if (!canSendEmail) {
                    return;
                  }
                  onSendEmail(normalizedEmail);
                }}
                disabled={!canSendEmail}
                className="inline-flex h-10 items-center rounded-xl bg-surfaceContainerHigh px-4 font-heading text-[14px] font-bold text-onSurface disabled:opacity-60"
              >
                {isSendingEmail ? "Sending..." : "Send by Email"}
              </button>
            </div>
            {showEmailError ? (
              <p className="mt-2 text-sm text-primary">
                {normalizedEmail.length === 0
                  ? "Recipient email is required."
                  : "Please enter a valid email address."}
              </p>
            ) : null}
            {emailStatus ? (
              <div className="mt-3 rounded-xl bg-surfaceContainerHigh px-3 py-2 text-sm text-onSurface">
                {emailStatus}
              </div>
            ) : null}

            <article className="mt-6 space-y-3 text-[15px] leading-7 text-onSurface">
              <ReactMarkdown
                components={{
                  h1: ({ children }) => (
                    <h1 className="mt-4 font-heading text-[30px] font-extrabold text-onSurface">{children}</h1>
                  ),
                  h2: ({ children }) => (
                    <h2 className="mt-4 font-heading text-[24px] font-bold text-onSurface">{children}</h2>
                  ),
                  h3: ({ children }) => (
                    <h3 className="mt-3 font-heading text-[20px] font-bold text-onSurface">{children}</h3>
                  ),
                  p: ({ children }) => <p className="text-onSurface">{children}</p>,
                  ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
                  ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
                  li: ({ children }) => <li className="text-onSurface">{children}</li>,
                  code: ({ children }) => (
                    <code className="rounded-md bg-surfaceContainerHigh px-1.5 py-0.5 font-mono text-[13px]">
                      {children}
                    </code>
                  ),
                  pre: ({ children }) => (
                    <pre className="overflow-x-auto rounded-xl bg-surfaceContainerHigh p-3">{children}</pre>
                  ),
                }}
              >
                {report.markdown}
              </ReactMarkdown>
            </article>
          </>
        ) : null}
      </div>
    </section>
  );
}
