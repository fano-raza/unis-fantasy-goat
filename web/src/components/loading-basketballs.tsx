// Reusable loading state: three basketballs bouncing in sequence, like a
// loading bar filling one ball at a time. Used anywhere a page previously
// rendered nothing at all while waiting on its first fetch (meta, initial
// data, etc.) -- that blank gap read as "the page is broken" on the
// droplet's slower/more variable response times, not just "still loading."
export function LoadingBasketballs({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16">
      <div className="flex items-center gap-2">
        <span className="loading-basketball text-3xl" style={{ animationDelay: "0s" }}>
          🏀
        </span>
        <span className="loading-basketball text-3xl" style={{ animationDelay: "0.2s" }}>
          🏀
        </span>
        <span className="loading-basketball text-3xl" style={{ animationDelay: "0.4s" }}>
          🏀
        </span>
      </div>
      {label && (
        <p className="text-[11px] font-bold tracking-wider text-muted-foreground uppercase">{label}</p>
      )}
      <style>{`
        .loading-basketball {
          display: inline-block;
          opacity: 0.25;
          animation: loading-basketball-bounce 1.2s ease-in-out infinite;
        }
        @keyframes loading-basketball-bounce {
          0%, 80%, 100% { opacity: 0.25; transform: translateY(0) scale(0.85); }
          40% { opacity: 1; transform: translateY(-8px) scale(1); }
        }
      `}</style>
    </div>
  );
}
