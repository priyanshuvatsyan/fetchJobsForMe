import './Button.css'

/** Renders an <a> when href is given, otherwise a <button>. */
const Button = ({
  variant = 'primary',
  size = 'md',
  href,
  children,
  className = '',
  ...rest
}) => {
  const classes = `btn btn-${variant} btn-${size} ${className}`.trim()

  if (href) {
    return (
      <a className={classes} href={href} target="_blank" rel="noreferrer noopener" {...rest}>
        {children}
      </a>
    )
  }

  return (
    <button className={classes} type="button" {...rest}>
      {children}
    </button>
  )
}

export default Button
