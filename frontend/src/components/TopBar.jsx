import { useEffect, useRef, useState } from "react";

function SimpleIcon({ children }) {
  return (
    <button
      type="button"
      className="grid h-8 w-8 place-items-center rounded-full bg-surfaceContainerLow text-onSurfaceVariant transition hover:bg-surfaceContainerHigh"
      aria-label="toolbar action"
    >
      <span className="text-sm font-semibold">{children}</span>
    </button>
  );
}

function AtMenu({ activeView, onChangeView }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", handleClickOutside);
    return () => window.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const options = [
    { id: "assistant", label: "AI Assistant" },
    { id: "insights", label: "Insights Generator" },
  ];

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="inline-flex h-10 items-center gap-2 rounded-full bg-surface px-4 font-heading text-[14px] font-bold text-onSurface"
      >
        <span className="rounded-full bg-surfaceContainerHigh px-2 py-0.5 text-[12px]">@</span>
        Menu
      </button>
      {open ? (
        <div className="absolute right-0 z-40 mt-2 min-w-[220px] rounded-2xl bg-surfaceContainerLowest p-2 shadow-ambient">
          {options.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => {
                onChangeView(option.id);
                setOpen(false);
              }}
              className={`flex w-full items-center rounded-xl px-3 py-2 text-left font-heading text-[14px] font-semibold ${
                activeView === option.id
                  ? "bg-surfaceContainerHigh text-onSurface"
                  : "text-onSurfaceVariant hover:bg-surfaceContainerLow"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function TopBar({ activeView, onChangeView }) {
  return (
    <header className="h-16 bg-surfaceContainerLow/80 px-5 backdrop-blur-sm">
      <div className="mx-auto flex h-full max-w-[1700px] items-center gap-4">
        <div className="flex min-w-[210px] items-center gap-3">
          <div className="grid h-7 w-7 place-items-center rounded-full bg-primary text-[10px] font-bold text-white">
            R
          </div>
          <p className="font-heading text-[28px] font-semibold leading-none text-onSurface">
            Rappi Ops AI
          </p>
        </div>

        <div className="hidden flex-1 justify-center md:flex">
          <div className="flex h-10 w-full max-w-[520px] items-center gap-2 rounded-full bg-surface px-4 text-sm text-onSurfaceVariant">
            <span className="text-base">o</span>
            <span className="opacity-80">Search analytics...</span>
          </div>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <AtMenu activeView={activeView} onChangeView={onChangeView} />
          <SimpleIcon>?</SimpleIcon>
          <SimpleIcon>*</SimpleIcon>
          <div className="ml-1 grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-[#4b4f53] to-[#1f2224] text-[11px] font-semibold text-white">
            AD
          </div>
        </div>
      </div>
    </header>
  );
}
