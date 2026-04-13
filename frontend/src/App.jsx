import { useMemo, useState } from "react";
import { TopBar } from "./components/TopBar";
import { ChatWorkspace } from "./components/ChatWorkspace";
import { ExecutionPanel } from "./components/ExecutionPanel";
import { InsightsGeneratorPage } from "./components/InsightsGeneratorPage";
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
  const [activeView, setActiveView] = useState("assistant");
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
  const [insightsEmailStatus, setInsightsEmailStatus] = useState("");
  const [chatErrorText, setChatErrorText] = useState("");
  const [insightsErrorText, setInsightsErrorText] = useState("");

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

    setChatErrorText("");
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
          {
            id: crypto.randomUUID(),
            role: "assistant",
            text: response.answer,
            suggestions: Array.isArray(response.suggestions) ? response.suggestions : [],
          },
        ]);
      }
      if (response.error) {
        setChatErrorText(response.error);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to reach backend.";
      setChatErrorText(message);
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

  const handleGenerateInsights = async (forceRegenerate = false) => {
    setInsightsErrorText("");
    setInsightsEmailStatus("");
    setIsGeneratingInsights(true);
    try {
      const result = await generateInsightsReport({
        top_k_critical: 5,
        force_fallback: false,
        force_regenerate: forceRegenerate,
      });
      setInsightsReport(result);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to generate insights report.";
      setInsightsErrorText(message);
    } finally {
      setIsGeneratingInsights(false);
    }
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
          <TopBar activeView={activeView} onChangeView={setActiveView} />

          {activeView === "assistant" ? (
            <main className="mx-auto grid h-[calc(100vh-64px)] max-w-[1700px] grid-cols-1 lg:grid-cols-[1fr_348px]">
              <ChatWorkspace
                messages={messages}
                onSubmitQuestion={handleSubmitQuestion}
                isSubmitting={isSubmitting}
                errorText={chatErrorText}
              />
              <ExecutionPanel steps={pipelineSteps} isSubmitting={isSubmitting} systemStatus={systemStatus} />
            </main>
          ) : (
            <InsightsGeneratorPage
              report={insightsReport}
              isGeneratingInsights={isGeneratingInsights}
              onGenerateInsights={handleGenerateInsights}
              onSendEmail={handleSendInsightsEmail}
              isSendingEmail={isSendingInsightsEmail}
              emailStatus={insightsEmailStatus}
              errorText={insightsErrorText}
              downloadUrl={getInsightsReportDownloadUrl()}
            />
          )}
        </div>
      </div>
    </div>
  );
}
