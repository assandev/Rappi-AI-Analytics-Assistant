import { useState } from "react";

function UserBubble({ text, className = "" }) {
  return (
    <div
      className={`max-w-[76%] rounded-chat-user bg-surfaceContainerHighest px-4 py-3 text-[14px] font-medium text-onSurface ${className}`}
    >
      {text}
    </div>
  );
}

function AssistantBubble({ text }) {
  return (
    <div className="max-w-[86%] rounded-chat-ai bg-surfaceContainerLowest px-5 py-4 text-[18px] leading-8 text-onSurface shadow-ambient">
      <div className="mb-3 flex items-center gap-2">
        <div className="grid h-5 w-5 place-items-center rounded-md bg-primary text-[10px] font-bold text-white">
          *
        </div>
        <span className="font-heading text-[12px] font-bold tracking-[0.11em] text-primary">
          RAPPI INTELLIGENCE
        </span>
      </div>
      <p>{text}</p>
    </div>
  );
}

function WelcomeCard() {
  const barSegments = [36, 52, 44, 60, 55, 78, 95];

  return (
    <article className="max-w-[860px] rounded-2xl bg-surfaceContainerLowest px-5 py-5 shadow-ambient">
      <header className="mb-4 flex items-center gap-2">
        <div className="grid h-5 w-5 place-items-center rounded-md bg-primary text-[10px] font-bold text-white">
          *
        </div>
        <span className="font-heading text-[12px] font-bold tracking-[0.11em] text-primary">
          RAPPI INTELLIGENCE
        </span>
      </header>

      <p className="max-w-[760px] text-[20px] leading-8 text-onSurface">
        I&apos;ve analyzed the &quot;Last Mile&quot; logistics data for the Bogota metropolitan area.
        The growth trends show a significant upward trajectory.
      </p>

      <section className="mt-5 grid gap-4 rounded-2xl bg-surface p-4 md:grid-cols-[auto_auto_1fr] md:items-center">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.09em] text-onSurfaceVariant/85">
            q3 growth
          </p>
          <p className="font-heading text-[36px] font-extrabold leading-none text-secondary">+14.2%</p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.09em] text-onSurfaceVariant/85">
            vs previous
          </p>
          <p className="font-heading text-[36px] font-extrabold leading-none text-primary">+3.8%</p>
        </div>
        <div className="flex h-14 items-end gap-1 rounded-xl bg-surfaceContainerLow p-2">
          {barSegments.map((height, index) => (
            <span
              // eslint-disable-next-line react/no-array-index-key
              key={index}
              className={`flex-1 rounded-sm ${
                index === barSegments.length - 1 ? "bg-secondary" : "bg-[#8bb9ad]"
              }`}
              style={{ height: `${height}%` }}
            />
          ))}
        </div>
      </section>

      <p className="mt-6 max-w-[760px] text-[20px] leading-8 text-onSurface">
        The acceleration is primarily driven by the &apos;Northern Cluster&apos; expansion. Would
        you like me to rank the top 5 performing zones within Bogota?
      </p>
    </article>
  );
}

function InputBar({ onSubmitQuestion, isSubmitting, onGenerateInsights, isGeneratingInsights }) {
  const [input, setInput] = useState("");

  const submit = () => {
    const text = input.trim();
    if (!text || isSubmitting) {
      return;
    }
    onSubmitQuestion(text);
    setInput("");
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="mx-5 mb-4 mt-6 rounded-2xl bg-surface/80 px-4 py-3 shadow-ambient backdrop-blur-[20px] lg:mx-8">
      <div className="flex items-center gap-3">
        <button
          type="button"
          className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-surfaceContainerLow text-lg font-semibold text-onSurfaceVariant"
        >
          +
        </button>
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about trends, comparisons, rankings..."
          className="h-8 w-full bg-transparent text-[15px] text-onSurface placeholder:text-onSurfaceVariant/65 focus:outline-none"
        />
        <button
          type="button"
          onClick={onGenerateInsights}
          disabled={isGeneratingInsights || isSubmitting}
          className="inline-flex h-10 shrink-0 items-center gap-2 rounded-xl bg-surfaceContainerHigh px-4 font-heading text-[14px] font-bold text-onSurface"
        >
          {isGeneratingInsights ? "Generating..." : "Generate Insights"}
        </button>
        <button
          type="button"
          onClick={submit}
          disabled={isSubmitting}
          className="inline-flex h-10 shrink-0 items-center gap-2 rounded-xl bg-gradient-to-r from-primary to-primaryContainer px-4 font-heading text-[15px] font-bold text-white"
        >
          {isSubmitting ? "Running..." : "Execute"}
          <span className="text-xs">{">"}</span>
        </button>
      </div>
    </div>
  );
}

export function ChatWorkspace({
  messages,
  onSubmitQuestion,
  isSubmitting,
  errorText,
  onGenerateInsights,
  isGeneratingInsights,
}) {
  return (
    <section className="flex h-full flex-col bg-surface">
      <div className="flex-1 overflow-y-auto px-5 pb-4 pt-7 lg:px-8">
        <h1 className="font-heading text-[42px] font-extrabold leading-none text-onSurface">Workspace</h1>
        <p className="mt-2 text-[20px] text-onSurfaceVariant">Operational analytics assistant</p>

        <div className="mt-8 space-y-7">
          <WelcomeCard />
          {messages.map((message) =>
            message.role === "user" ? (
              <UserBubble key={message.id} className="ml-auto" text={message.text} />
            ) : (
              <AssistantBubble key={message.id} text={message.text} />
            ),
          )}
          {errorText ? (
            <div className="max-w-[86%] rounded-xl bg-[#fff2f0] px-4 py-3 text-[14px] text-primary">
              {errorText}
            </div>
          ) : null}
        </div>
      </div>

      <InputBar
        onSubmitQuestion={onSubmitQuestion}
        isSubmitting={isSubmitting}
        onGenerateInsights={onGenerateInsights}
        isGeneratingInsights={isGeneratingInsights}
      />

      <p className="pb-2 text-center text-[10px] tracking-[0.08em] text-onSurfaceVariant/65">
        POWERED BY RAPPI LLAMA-3 INFRASTRUCTURE
      </p>
    </section>
  );
}
