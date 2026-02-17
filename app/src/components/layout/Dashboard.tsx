import type { ReactNode } from "react";

interface DashboardProps {
  children: ReactNode;
}

export function Dashboard({ children }: DashboardProps) {
  return (
    <div className="min-h-screen flex flex-col bg-mc-bg text-mc-text-1 font-sans antialiased">
      {children}
    </div>
  );
}
