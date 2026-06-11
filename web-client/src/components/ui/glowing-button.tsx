import React from 'react';
import { cn } from '@/lib/utils';
import { Button as MovingBorderButton } from './moving-border';

type Props = Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'type'> & {
  loading?: boolean;
  block?: boolean;
  htmlType?: 'button' | 'submit' | 'reset';
  type?: 'primary' | 'default' | 'button' | 'submit' | 'reset';
};

// Native Aceternity moving-border button wrapper for app actions.
export function GlowingButton({ className, children, loading, disabled, block, htmlType, type, ...props }: Props) {
  const buttonType = htmlType || (type === 'submit' || type === 'reset' || type === 'button' ? type : 'button');
  return (
    <MovingBorderButton
      as="button"
      type={buttonType}
      disabled={disabled || loading}
      containerClassName={cn(block && 'w-full', 'h-12 text-sm')}
      borderRadius="14px"
      duration={4200}
      className={cn(
        'h-full w-full border border-slate-800/10 bg-gradient-to-br from-blue-600 to-cyan-500 px-5 text-sm font-black text-white shadow-glow transition-transform hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-65',
        className,
      )}
      {...props}
    >
      <span className="relative z-10 inline-flex items-center justify-center gap-2">
        {loading && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/45 border-t-white" />}
        {children}
      </span>
    </MovingBorderButton>
  );
}
