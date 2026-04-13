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

function InputBar({ onSubmitQuestion, isSubmitting }) {
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
}) {
  return (
    <section className="flex h-full flex-col bg-surface">
      <div className="flex-1 overflow-y-auto px-5 pb-4 pt-7 lg:px-8">
        <h1 className="font-heading text-[42px] font-extrabold leading-none text-onSurface">Workspace</h1>
        <p className="mt-2 text-[20px] text-onSurfaceVariant">Operational analytics assistant</p>

        <div className="mt-8 space-y-7">
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
      />

      <p className="pb-2 text-center text-[10px] tracking-[0.08em] text-onSurfaceVariant/65">
        POWERED BY RAPPI LLAMA-3 INFRASTRUCTURE
      </p>
    </section>
  );
}
