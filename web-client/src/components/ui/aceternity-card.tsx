import React from 'react';
import { cn } from '@/lib/utils';
import { BackgroundGradient } from './background-gradient';

type Props = React.HTMLAttributes<HTMLDivElement> & {
  glow?: boolean;
};

// Wrapper around the official Aceternity BackgroundGradient source component.
// Kept as a project alias so existing pages can migrate without changing business JSX.
export function AceternityCard({ className, children, glow = true, ...props }: Props) {
  return (
    <BackgroundGradient
      containerClassName="rounded-[24px]"
      className={cn(
        'relative w-full overflow-hidden rounded-[22px] border border-white/70 bg-white/80 shadow-aceternity backdrop-blur-xl',
        glow && 'after:pointer-events-none after:absolute after:-right-20 after:-top-24 after:h-56 after:w-56 after:rounded-full after:bg-blue-400/20 after:blur-3xl',
        className,
      )}
      {...props}
    >
      <div className="relative z-10 w-full">{children}</div>
    </BackgroundGradient>
  );
}
