import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function InsightsReportModal({
  open,
  report,
  onClose,
  downloadUrl,
  onSendEmail,
  isSendingEmail,
  emailStatus,
}) {
  const [recipientEmail, setRecipientEmail] = useState("");
  const [emailTouched, setEmailTouched] = useState(false);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) {
      return;
    }
    setRecipientEmail("");
    setEmailTouched(false);
  }, [open]);

  if (!open || !report) {
    return null;
  }

  const normalizedEmail = recipientEmail.trim();
  const isEmailValid = EMAIL_REGEX.test(normalizedEmail);
  const showEmailError = emailTouched && !isEmailValid;
  const canSendEmail = !isSendingEmail && isEmailValid;

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-[#191c1d]/35 p-6"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="max-h-[88vh] w-full max-w-4xl rounded-3xl bg-surfaceContainerLowest shadow-ambient"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Insights report"
      >
        <header className="flex items-center justify-between px-6 py-5">
          <div>
            <h3 className="font-heading text-[24px] font-extrabold text-onSurface">Insights Report</h3>
            <p className="mt-1 text-sm text-onSurfaceVariant">
              {report.insight_count} findings | generated at {report.generated_at}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <a
              href={downloadUrl}
              className="inline-flex h-10 items-center rounded-xl bg-gradient-to-r from-primary to-primaryContainer px-4 font-heading text-sm font-bold text-white"
            >
              Download .md
            </a>
            <button
              type="button"
              onClick={onClose}
              className="grid h-10 w-10 place-items-center rounded-full bg-surfaceContainerLow text-onSurfaceVariant"
            >
              x
            </button>
          </div>
        </header>

        <div className="max-h-[calc(88vh-92px)] overflow-y-auto px-6 pb-6">
          <div className="mb-4 grid grid-cols-1 gap-2 rounded-2xl bg-surfaceContainerLow p-3 md:grid-cols-[1fr_auto]">
            <input
              type="email"
              value={recipientEmail}
              onChange={(event) => setRecipientEmail(event.target.value)}
              onBlur={() => setEmailTouched(true)}
              placeholder="Recipient email"
              className={`h-10 rounded-xl bg-surfaceContainerLowest px-3 text-sm text-onSurface outline-none ${
                showEmailError ? "ring-2 ring-primary" : "ring-1 ring-transparent"
              }`}
            />
            <button
              type="button"
              onClick={() => {
                setEmailTouched(true);
                if (!isEmailValid) {
                  return;
                }
                onSendEmail(normalizedEmail);
              }}
              disabled={!canSendEmail}
              className="inline-flex h-10 items-center justify-center rounded-xl bg-surfaceContainerHigh px-4 font-heading text-sm font-bold text-onSurface disabled:opacity-60"
            >
              {isSendingEmail ? "Sending..." : "Send by Email"}
            </button>
          </div>
          {showEmailError ? (
            <p className="mb-4 text-sm text-primary">
              {normalizedEmail.length === 0
                ? "Recipient email is required."
                : "Please enter a valid email address."}
            </p>
          ) : null}

          {emailStatus ? (
            <div className="mb-4 rounded-xl bg-surfaceContainerHigh px-3 py-2 text-sm text-onSurface">
              {emailStatus}
            </div>
          ) : null}
          <article className="space-y-3 text-[15px] leading-7 text-onSurface">
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
        </div>
      </div>
    </div>
  );
}
