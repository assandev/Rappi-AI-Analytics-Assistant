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

export function TopBar() {
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
