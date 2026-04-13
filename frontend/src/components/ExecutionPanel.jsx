import { useState } from "react";

function statusStyles(status) {
  if (status === "completed") {
    return {
      wrapper: "bg-surfaceContainerLowest",
      icon: "bg-secondary text-white",
      label: "text-onSurface",
      duration: "text-secondary",
      tone: "text-secondary",
    };
  }

  if (status === "running") {
    return {
      wrapper: "bg-[#fff9f4] ring-1 ring-tertiary/35",
      icon: "bg-tertiary text-white",
      label: "text-primary",
      duration: "text-tertiary font-semibold uppercase tracking-[0.05em]",
      tone: "text-tertiary",
    };
  }

  if (status === "failed") {
    return {
      wrapper: "bg-[#fff2f0] ring-1 ring-primary/35",
      icon: "bg-primary text-white",
      label: "text-primary",
      duration: "text-primary",
      tone: "text-primary",
    };
  }

  return {
    wrapper: "bg-surfaceContainerLow/50",
    icon: "bg-surfaceContainerHigh text-onSurfaceVariant/65",
    label: "text-onSurfaceVariant/70",
    duration: "text-onSurfaceVariant/45",
    tone: "text-onSurfaceVariant/60",
  };
}

function StepCard({ step, expanded, onToggle }) {
  const style = statusStyles(step.status);
  const interactive = (step.status === "completed" || step.status === "failed") && Boolean(step.detail);
  const duration = typeof step.duration_s === "number" ? `${step.duration_s.toFixed(1)}s` : "--";
  const detailText =
    step.detail && typeof step.detail === "object" ? JSON.stringify(step.detail, null, 2) : step.detail || "";

  return (
    <article className={`rounded-[28px] px-4 py-4 ${style.wrapper}`}>
      <button
        type="button"
        onClick={interactive ? () => onToggle(step.id) : undefined}
        className={`flex w-full items-center gap-3 text-left ${
          interactive ? "cursor-pointer" : "cursor-default"
        }`}
      >
        <span className={`grid h-5 w-5 place-items-center rounded-full text-[11px] ${style.icon}`}>
          {step.status === "completed"
            ? "v"
            : step.status === "running"
              ? "~"
              : step.status === "failed"
                ? "!"
                : "."}
        </span>
        <span className={`font-body text-[22px] font-semibold ${style.label}`}>{step.title}</span>
        <span className={`ml-auto text-sm ${style.duration}`}>
          {step.status === "running" ? "running" : duration}
        </span>
      </button>

      {expanded && detailText && (
        <pre className="mt-4 overflow-x-auto rounded-2xl bg-surfaceContainerHigh p-4 text-sm leading-6 text-onSurfaceVariant">
          <code>{detailText}</code>
        </pre>
      )}

      {step.status === "running" && (
        <div className="mt-4 px-1">
          <p className="text-xs text-onSurfaceVariant">Running deterministic pipeline...</p>
          <div className="mt-2 h-1.5 rounded-full bg-surfaceContainerHigh">
            <div className="h-full rounded-full bg-tertiary" style={{ width: `${step.progress ?? 66}%` }} />
          </div>
        </div>
      )}
    </article>
  );
}

function SystemStatus({ systemStatus }) {
  const workerId = systemStatus?.worker_id ?? "node-772-bog";
  const latency = systemStatus?.latency ?? "112ms";
  return (
    <section className="mt-auto rounded-[26px] bg-surfaceContainerLowest px-4 py-4 shadow-ambient">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-sm text-primary">[]</span>
        <h3 className="font-heading text-xs font-extrabold tracking-[0.1em] text-onSurface">
          SYSTEM STATUS
        </h3>
      </div>
      <div className="space-y-2 text-sm">
        <div className="flex justify-between text-onSurfaceVariant">
          <span>Worker ID</span>
          <span className="font-medium text-onSurface">{workerId}</span>
        </div>
        <div className="flex justify-between text-onSurfaceVariant">
          <span>Latency</span>
          <span className="font-medium text-onSurface">{latency}</span>
        </div>
      </div>
    </section>
  );
}

export function ExecutionPanel({ steps, isSubmitting, systemStatus }) {
  const [expandedSteps, setExpandedSteps] = useState(() => ({
    parse: true,
    normalize: false,
    validate: false,
  }));

  const toggleStep = (id) => {
    setExpandedSteps((previous) => ({
      ...previous,
      [id]: !previous[id],
    }));
  };

  return (
    <aside className="flex h-full flex-col bg-surfaceContainerLow px-4 pb-4 pt-6 lg:px-5">
      <header className="mb-4 flex items-center justify-between">
        <h2 className="font-heading text-[13px] font-extrabold tracking-[0.14em] text-onSurfaceVariant">
          EXECUTION PIPELINE
        </h2>
        <span className="rounded-full bg-[#f8d8a9] px-2 py-1 text-[10px] font-bold text-tertiary">
          {isSubmitting ? "LIVE" : "IDLE"}
        </span>
      </header>

      <div className="space-y-3">
        {steps.map((step) => (
          <StepCard
            key={step.id}
            step={step}
            expanded={Boolean(expandedSteps[step.id])}
            onToggle={toggleStep}
          />
        ))}
      </div>

      <SystemStatus systemStatus={systemStatus} />
    </aside>
  );
}
