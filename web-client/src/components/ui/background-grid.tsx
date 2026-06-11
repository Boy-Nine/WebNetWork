import React from 'react';
import { cn } from '../../lib/cn';

export function BackgroundGrid({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'pointer-events-none absolute inset-0 opacity-[.42]',
        '[background-image:linear-gradient(to_right,rgba(148,163,184,.22)_1px,transparent_1px),linear-gradient(to_bottom,rgba(148,163,184,.22)_1px,transparent_1px)] [background-size:32px_32px]',
        '[mask-image:radial-gradient(ellipse_at_center,black_40%,transparent_78%)]',
        className,
      )}
    />
  );
}
