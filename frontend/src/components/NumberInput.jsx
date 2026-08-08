// A mm-value input that accepts any decimal (the database columns this
// feeds are all Numeric(10, 3)) while still incrementing by a fixed step
// via visible buttons and the arrow keys.
//
// Plain `<input type="number" step="0.1">` looks right but isn't: the
// step attribute also governs which values the browser accepts by hand,
// so typing 0.05 trips a "please enter a valid value" stepMismatch and
// the form silently refuses to submit. `step="any"` fixes that but also
// hands the native spinner arrows to the browser, which then jump by a
// whole 1mm instead of the intended 0.1mm. Hiding the native spinner
// (index.css) and driving the step ourselves keeps both properties: any
// decimal can be typed, and the steppers/arrow keys move by `step`.
function NumberInput({ value, onChange, onBlur, step = 0.1, min, max, placeholder, required, title }) {
  function nudge(direction) {
    const current = Number(value) || 0
    // Round to 3dp -- plain float arithmetic on 0.1 steps produces
    // drift (0.1 + 0.2 === 0.30000000000000004) that Numeric(10, 3)
    // would then silently truncate on save, so the displayed value and
    // the saved value could disagree without this.
    let next = Math.round((current + direction * step) * 1000) / 1000
    if (min !== undefined && next < Number(min)) {
      next = Number(min)
    }
    if (max !== undefined && next > Number(max)) {
      next = Number(max)
    }
    onChange(String(next))
  }

  function handleKeyDown(event) {
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      nudge(1)
    } else if (event.key === 'ArrowDown') {
      event.preventDefault()
      nudge(-1)
    }
  }

  return (
    <span className="number-input">
      <input
        type="number"
        step="any"
        min={min}
        max={max}
        placeholder={placeholder}
        title={title}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        onKeyDown={handleKeyDown}
        required={required}
      />
      {/* onMouseDown/preventDefault (same pattern as RichTextEditor.jsx's
          toolbar) stops the button from taking focus away from the
          input. Without it, clicking a stepper blurs the input *before*
          the click's onChange runs -- for callers like
          ToleranceMatrixPage that commit on blur, that fires the commit
          with the pre-nudge value, one step behind. */}
      <span className="number-input-steppers">
        <button
          type="button"
          tabIndex={-1}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => nudge(1)}
          aria-label="Increase"
        >
          &#9650;
        </button>
        <button
          type="button"
          tabIndex={-1}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => nudge(-1)}
          aria-label="Decrease"
        >
          &#9660;
        </button>
      </span>
    </span>
  )
}

export default NumberInput
