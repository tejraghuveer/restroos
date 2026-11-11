import { AlertCircle, CheckCircle2, Info } from "lucide-react";
import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Tone = "error" | "success" | "info";

const tones: Record<Tone, { box: string; icon: typeof Info }> = {
  error: { box: "border-red-200 bg-red-50 text-red-800", icon: AlertCircle },
  success: { box: "border-emerald-200 bg-emerald-50 text-emerald-800", icon: CheckCircle2 },
  info: { box: "border-amber-200 bg-amber-50 text-amber-900", icon: Info },
};

export function Alert({
  tone = "info",
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement> & { tone?: Tone }) {
  const { box, icon: Icon } = tones[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn("flex gap-2 rounded-md border p-3 text-sm", box, className)}
      {...props}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="space-y-1">{children}</div>
    </div>
  );
}
