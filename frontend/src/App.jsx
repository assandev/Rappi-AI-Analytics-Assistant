import { useMemo, useState } from "react";
import { TopBar } from "./components/TopBar";
import { ChatWorkspace } from "./components/ChatWorkspace";
import { ExecutionPanel } from "./components/ExecutionPanel";
import { InsightsReportModal } from "./components/InsightsReportModal";
import {
  generateInsightsReport,
  getInsightsReportDownloadUrl,
  runChatQuery,
  sendInsightsReportEmail,
} from "./api";

const DEFAULT_PIPELINE = [
  { id: "parse", title: "Parse Question", status: "not_started", duration_s: null, detail: null },
  {
    id: "normalize",
    title: "Normalize Query",
    status: "not_started",
    duration_s: null,
    detail: null,
  },
  {
    id: "validate",
    title: "Validate Query",
    status: "not_started",
    duration_s: null,
    detail: null,
  },
  {
    id: "execute",
    title: "Execute Analytics",
    status: "not_started",
    duration_s: null,
    detail: null,
  },
  {
    id: "format",
    title: "Format Response",
    status: "not_started",
    duration_s: null,
    detail: null,
  },
];

export default function App() {
  const [messages, setMessages] = useState(() => [
    {
      id: "ai-welcome",
      role: "assistant",
      text: "Operational analytics assistant ready. Ask me for trends, rankings, comparisons, or growth signals.",
    },
  ]);
  const [pipelineSteps, setPipelineSteps] = useState(DEFAULT_PIPELINE);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isGeneratingInsights, setIsGeneratingInsights] = useState(false);
  const [isSendingInsightsEmail, setIsSendingInsightsEmail] = useState(false);
  const [insightsReport, setInsightsReport] = useState(null);
  const [isInsightsModalOpen, setIsInsightsModalOpen] = useState(false);
  const [insightsEmailStatus, setInsightsEmailStatus] = useState("");
  const [errorText, setErrorText] = useState("");

  const systemStatus = useMemo(
    () => ({
      worker_id: "node-772-bog",
      latency: isSubmitting ? "running..." : "ready",
    }),
    [isSubmitting],
  );

  const handleSubmitQuestion = async (question) => {
    if (!question.trim()) {
      return;
    }

    setErrorText("");
    setIsSubmitting(true);
    setMessages((previous) => [...previous, { id: crypto.randomUUID(), role: "user", text: question }]);
    setPipelineSteps((previous) =>
      previous.map((step) =>
        step.id === "parse" ? { ...step, status: "running", detail: "Sending question to parser..." } : step,
      ),
    );

    try {
      const response = await runChatQuery(question);
      const pipeline = Array.isArray(response.pipeline) && response.pipeline.length > 0 ? response.pipeline : DEFAULT_PIPELINE;

      setPipelineSteps(
        pipeline.map((step) => ({
          ...step,
          status: step.status || "completed",
        })),
      );
      if (response.answer) {
        setMessages((previous) => [
          ...previous,
          { id: crypto.randomUUID(), role: "assistant", text: response.answer },
        ]);
      }
      if (response.error) {
        setErrorText(response.error);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to reach backend.";
      setErrorText(message);
      setPipelineSteps((previous) =>
        previous.map((step) =>
          step.status === "running" || step.status === "not_started"
            ? { ...step, status: "failed", detail: message }
            : step,
        ),
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleGenerateInsights = async () => {
    setErrorText("");
    setInsightsEmailStatus("");
    setIsGeneratingInsights(true);
    try {
      const result = await generateInsightsReport({ top_k_critical: 5, force_fallback: false });
      setInsightsReport(result);
      setIsInsightsModalOpen(true);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to generate insights report.";
      setErrorText(message);
    } finally {
      setIsGeneratingInsights(false);
    }
  };

  const closeInsightsModal = () => {
    setIsInsightsModalOpen(false);
    setInsightsEmailStatus("");
  };

  const handleSendInsightsEmail = async (recipientEmail) => {
    if (!insightsReport) {
      return;
    }
    if (!recipientEmail || !recipientEmail.trim()) {
      setInsightsEmailStatus("Please enter a recipient email.");
      return;
    }

    setInsightsEmailStatus("");
    setIsSendingInsightsEmail(true);
    try {
      const result = await sendInsightsReportEmail(recipientEmail.trim());
      setInsightsEmailStatus(`Email sent to ${result.recipient_email}.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to send report email.";
      setInsightsEmailStatus(message);
    } finally {
      setIsSendingInsightsEmail(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface text-onSurface">
      <div className="h-screen w-screen overflow-auto">
        <div className="origin-top-left scale-[0.8]" style={{ width: "125%", minHeight: "125%" }}>
          <TopBar />

          <main className="mx-auto grid h-[calc(100vh-64px)] max-w-[1700px] grid-cols-1 lg:grid-cols-[1fr_348px]">
            <ChatWorkspace
              messages={messages}
              onSubmitQuestion={handleSubmitQuestion}
              isSubmitting={isSubmitting}
              onGenerateInsights={handleGenerateInsights}
              isGeneratingInsights={isGeneratingInsights}
              errorText={errorText}
            />
            <ExecutionPanel steps={pipelineSteps} isSubmitting={isSubmitting} systemStatus={systemStatus} />
          </main>
        </div>
      </div>
      <InsightsReportModal
        open={isInsightsModalOpen}
        report={insightsReport}
        onClose={closeInsightsModal}
        downloadUrl={getInsightsReportDownloadUrl()}
        onSendEmail={handleSendInsightsEmail}
        isSendingEmail={isSendingInsightsEmail}
        emailStatus={insightsEmailStatus}
      />
    </div>
  );
}
