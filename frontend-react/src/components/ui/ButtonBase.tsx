import React from "react";
import { useNavigate } from "react-router";
import type {
  Variant,
  ButtonSize,
  IconPosition,
  ButtonType,
} from "@/lib/types/components";

type ButtonBaseProps = {
  label?: string; // Optional if you're using children
  variant: Variant;
  size?: ButtonSize;
  ariaLabel: string;
  onClick?: () => void;
  navTo?: string;
  active?: boolean;
  wide?: boolean;
  soft?: boolean;
  outline?: boolean;
  disabled?: boolean;
  icon?: React.ReactNode;
  iconPosition?: IconPosition;
  loading?: boolean;
  children?: React.ReactNode;
  className?: string;
  type?: ButtonType;
  tooltip?: string;
};

const ButtonBase: React.FC<ButtonBaseProps> = ({
  label,
  variant,
  size = "md",
  ariaLabel,
  onClick,
  navTo,
  active = false,
  wide = false,
  soft = false,
  outline = false,
  disabled = false,
  icon,
  iconPosition = "left",
  loading = false,
  children,
  className = "",
  type = "button",
  tooltip,
}) => {
  const navigate = useNavigate();

  const handleClick = () => {
    if (onClick) {
      onClick();
    } else if (navTo && !disabled) {
      navigate(navTo);
    }
  };

  const sizeClass = {
    xs: "btn-xs",
    sm: "btn-sm",
    md: "btn-md",
    lg: "btn-lg",
  }[size];

  const variantClass = {
    neutral: "btn-neutral",
    primary: "btn-primary",
    secondary: "btn-secondary",
    accent: "btn-accent",
    info: "btn-info",
    success: "btn-success",
    warning: "btn-warning",
    error: "btn-error",
    ghost: "btn-ghost",
  }[variant];

  // Define the icon size based on the button size (in pixels for Lucide icons)
  const iconSize = {
    xs: 12,
    sm: 14,
    md: 16,
    lg: 20,
  }[size];

  // Define margin adjustment per size for better vertical alignment
  const iconMarginBottom = {
    xs: '1.25px',
    sm: '1px',
    md: '0.5px',
    lg: '0px',
  }[size];

  // Define the icon color based on the button variant
  const iconColorClass = variant === "ghost" ? "text-primary" : "";

  // Concatenate the class names
  const finalClassName = `btn inline-flex items-center justify-center gap-1.5 ${variantClass} ${sizeClass} ${
    active ? "btn-active" : ""
  } ${wide ? "btn-block" : ""} ${soft ? "btn-soft" : ""} ${
    outline ? "btn-outline" : ""
  } ${disabled ? "btn-disabled" : ""} ${className}`;

  const buttonElement = (
    <button
      className={finalClassName}
      aria-label={ariaLabel}
      onClick={handleClick}
      disabled={disabled || loading}
      type={type}
    >
      {loading && <span className="loading loading-spinner"></span>}
      {!loading && icon && iconPosition === "left" && (
        React.cloneElement(icon as React.ReactElement<{ size?: number; className?: string; style?: React.CSSProperties }>, { 
          size: iconSize,
          className: `${iconColorClass} flex-shrink-0`,
          style: { marginBottom: iconMarginBottom }
        })
      )}
      {children || label}
      {!loading && icon && iconPosition === "right" && (
        React.cloneElement(icon as React.ReactElement<{ size?: number; className?: string; style?: React.CSSProperties }>, { 
          size: iconSize,
          className: `${iconColorClass} flex-shrink-0`,
          style: { marginBottom: iconMarginBottom }
        })
      )}
    </button>
  );

  // Wrap with tooltip if provided
  if (tooltip) {
    return (
      <div className="tooltip" data-tip={tooltip}>
        {buttonElement}
      </div>
    );
  }

  return buttonElement;
};

export default ButtonBase;
