import { useState } from "react";

import { brawlerInitials, brawlerPortraitUrl } from "../utils/brawlerImage";

interface BrawlerPortraitProps {
  brawlerId: number;
  name: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const sizeClasses = {
  sm: "h-10 w-10",
  md: "h-14 w-14",
  lg: "h-20 w-20",
} as const;

export function BrawlerPortrait({
  brawlerId,
  name,
  size = "md",
  className = "",
}: BrawlerPortraitProps) {
  const [failed, setFailed] = useState(false);
  const dim = sizeClasses[size];

  return (
    <div
      className={`relative shrink-0 overflow-hidden rounded-lg bg-slate-800 ring-1 ring-slate-700/80 ${dim} ${className}`}
    >
      {!failed ? (
        <img
          src={brawlerPortraitUrl(brawlerId)}
          alt=""
          loading="lazy"
          className="h-full w-full object-cover object-top"
          onError={() => setFailed(true)}
        />
      ) : (
        <span className="flex h-full w-full items-center justify-center text-xs font-bold text-slate-300">
          {brawlerInitials(name)}
        </span>
      )}
    </div>
  );
}
