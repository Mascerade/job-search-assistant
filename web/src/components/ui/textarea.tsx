import * as React from "react"
import { cn } from "cn"

// Auto-grows with its content (field-sizing-content). `rows` sets the minimum
// height, since field-sizing otherwise ignores it.
function Textarea({ className, rows, style, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      rows={rows}
      style={rows ? { minHeight: `calc(${rows} * 1.5em + 1rem)`, ...style } : style}
      className={cn(
        "flex field-sizing-content min-h-16 max-h-[70dvh] w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-base transition-colors outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:bg-input/50 disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 md:text-sm dark:bg-input/30 dark:disabled:bg-input/80 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
