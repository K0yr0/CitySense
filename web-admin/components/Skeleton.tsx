/** Grey placeholder block while data loads (pulses only when the user allows motion). */
export function Skeleton({ className = "" }: { className?: string }) {
  return <span aria-hidden="true" className={`block rounded-md bg-surface-2 motion-safe:animate-pulse ${className}`} />;
}

/** Screen-reader text for a loading region (the skeleton itself is hidden from assistive tech). */
export function LoadingLabel({ children }: { children: string }) {
  return (
    <span role="status" className="sr-only">
      {children}
    </span>
  );
}
