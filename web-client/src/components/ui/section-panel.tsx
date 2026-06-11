import React from 'react';
import { cn } from '../../lib/cn';
import { AceternityCard } from './aceternity-card';
import { BackgroundGrid } from './background-grid';

type Props = Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> & {
  title?: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  bodyClassName?: string;
};

export function SectionPanel({ title, description, action, className, bodyClassName, children, ...props }: Props) {
  return (
    <AceternityCard className={cn('section-panel', className)} {...props}>
      <BackgroundGrid className="opacity-[.16]" />
      {(title || description || action) && (
        <div className="section-panel-head">
          <div className="min-w-0">
            {title && <div className="section-panel-title">{title}</div>}
            {description && <div className="section-panel-desc">{description}</div>}
          </div>
          {action && <div className="section-panel-action">{action}</div>}
        </div>
      )}
      <div className={cn('section-panel-body', bodyClassName)}>{children}</div>
    </AceternityCard>
  );
}
